from __future__ import annotations

import json
import logging

import core.llm
import tools.registry

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """<system_identity>
You are Jarvis, an advanced AI companion designed to compute highly factual, grounded answers using browser search evidence.
You run locally and operate strictly in a sequential loop of Thought, Action, PAUSE, Observation.
</system_identity>

<loop_architecture>
For each turn, you MUST reason inside <thought> tags and then output EXACTLY ONE tool execution JSON inside <action> tags.
Do not output any introductory or concluding text outside these tags.

Format:
<thought>
Reason about what information is missing, what rules apply, and what tool is appropriate.
</thought>
<action>
{"tool_name": {"arg_key": "arg_value"}}
</action>
</loop_architecture>

<available_tools>
1. {"search_web": {"query": "short keyword search query"}}
   - Use for quick, simple one-hop factual lookups, current events, scores, or names.
2. {"research_query": {"query": "analytical question", "max_sources": 8}}
   - Use for complex comparisons, detailed reports, market trends, or why/how questions.
3. {"fetch_url": {"url": "https://example.com"}}
   - Use when search snippets are insufficient and you need to read the full page text.
4. {"finish": {"answer": "final synthesized answer with citations to source URLs"}}
   - Use when you have gathered all necessary hard facts to fully answer the query.
</available_tools>

<instruction_rules>
- Proactive Searching: If a query is broad or ambiguous, formulate a smart query and search immediately. NEVER ask the user to clarify broad requests.
- Guardrails on Unknowns: If you lack information or feel the urge to say "as of my last update", STOP. Execute a web search immediately.
- Hard Facts Only: Extract exact metrics, dates, and names. Do NOT summarize articles or write "This article discusses...".
- Deep Reading: If search snippets hint at the answer but lack the specific facts needed, you MUST execute a fetch_url action to read the full article before using the finish action.
- Negative Constraint: DO NOT write any conversational text before or after the <thought> and <action> blocks.
</instruction_rules>

<examples>
<example>
Question: compare India and China GDP in 2025
<thought>
The user is asking for a complex macroeconomic comparison that requires multiple sources and careful metric handling.
</thought>
<action>
{"research_query": {"query": "compare India and China GDP in 2025", "max_sources": 8}}
</action>
</example>

<example>
Question: Why is Indian Rupee falling recently?
<thought>
The user is asking for recent causal analysis of financial markets, requiring a multi-source report.
</thought>
<action>
{"research_query": {"query": "Why is Indian Rupee falling recently?", "max_sources": 8}}
</action>
</example>

<example>
Question: barcelona total goals
<thought>
I need to search for the current FC Barcelona goal statistics.
</thought>
<action>
{"search_web": {"query": "barcelona total goals"}}
</action>
</example>
</examples>"""


def extract_action(llm_output: str) -> dict:
    try:
        json_text = llm_output
        if "<action>" in llm_output and "</action>" in llm_output:
            json_text = llm_output.split("<action>", 1)[1].split("</action>", 1)[0].strip()
        elif "Action:" in llm_output:
            json_text = llm_output.split("Action:", 1)[1].strip()

        start = json_text.find("{")
        end = json_text.rfind("}") + 1
        if start == -1 or end == 0:
            return {}
        return json.loads(json_text[start:end])
    except Exception as exc:
        logger.debug("Failed to extract action: %s", exc)
        return {}


def _generate_text(prompt: str) -> str:
    response = core.llm.generate_response(prompt, print_metrics=False)
    if isinstance(response, str):
        return response
    return "".join(response)


def run_react_loop(query: str, max_iterations: int = 5) -> str:
    context = f"{SYSTEM_PROMPT}\n\nQuestion: {query}\n"
    last_observation: str | None = None

    for _ in range(max_iterations):
        response = _generate_text(context)
        context += f"{response}\n"

        action_dict = extract_action(response)
        if not action_dict:
            context += "Observation: Error: Invalid JSON Action format. Try again using exactly one tool in JSON.\n"
            continue

        if "finish" in action_dict:
            return tools.registry.execute_react_tool(action_dict)

        observation = tools.registry.execute_react_tool(action_dict)
        if last_observation:
            context = context.replace(
                f"Observation: {last_observation}\n",
                "Observation: [Observation dropped to save memory. Model already processed this.]\n",
            )
        context += f"Observation: {observation}\n"
        last_observation = observation

    return "Error: Maximum thinking iterations reached without final answer."
