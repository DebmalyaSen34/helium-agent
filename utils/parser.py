import re
import json
import logging

logger = logging.getLogger(__name__)

def extract_json(text: str) -> dict | None:
    
    text = text.replace("<end_of_turn>", "").replace("</start_of_turn>", "").strip()

    try:
        # Avoid printing raw data here to keep output clean
        # print(f"This is the data:\n{text}")
        if text.strip().startswith('{'):
            return json.loads(text.strip(), strict=False)
    except json.JSONDecodeError:
        # Ignore and fallback to regex extraction instead of logging an error
        pass

    markdown_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if markdown_match:
        try:
            return json.loads(markdown_match.group(1), strict=False)
        except json.JSONDecodeError as e:
            logger.error(f"JSON decoding from markdown failed: {e}")
            pass

    brace_match = re.search(r"(\{.*?\})", text, re.DOTALL)
    
    # A more robust capture for nested JSON blocks without using complex regex
    start_idx = text.find('{')
    end_idx = text.rfind('}')
    
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        try:
            return json.loads(text[start_idx:end_idx+1], strict=False)
        except json.JSONDecodeError:
            pass

    if brace_match:
        try:
            return json.loads(brace_match.group(1), strict=False)
        except json.JSONDecodeError:
            tool_match = re.search(r'"tool"\s*:\s*"([^"]+)"', text)
            filename_match = re.search(r'"filename"\s*:\s*"([^"]+)"', text)

            content_match = re.search(r'"content"\s*:\s*"(.*)"[\s}]*$', text, re.DOTALL)

            if tool_match and filename_match and content_match:
                content = content_match.group(1)

                content = content.replace('\\n', '\n').replace('\\"', '"')
 
                return {
                    "tool": tool_match.group(1),
                    "args": {
                        "filename": filename_match.group(1),
                        "content": content
                    }
                }
                
            # Additional fallback for tool like search_web using regex
            if tool_match and '"query"' in text:
                query_match = re.search(r'"query"\s*:\s*"([^"]+)"', text)
                if query_match:
                    num_results_match = re.search(r'"num_results"\s*:\s*(\d+)', text)
                    args = {"query": query_match.group(1)}
                    if num_results_match:
                        args["num_results"] = int(num_results_match.group(1))
                    return {
                        "tool": tool_match.group(1),
                        "args": args
                    }

    return None

def extract_code_block(text: str) -> str | None:
    pattern = r"```[^\n]*\n(.*?)```"
    match = re.search(pattern, text, re.DOTALL)
    return match.group(1).strip() if match else None


THINK_OPEN = "<think>"
THINK_CLOSE = "</think>"


def strip_reasoning(text: str) -> str:
    """Remove a model's leading <think>...</think> block.

    Reasoning models emit thinking at the start of a reply, so only a leading
    block is removed; `<think>` mentioned later in an answer is ordinary text.
    An unterminated leading block means the reply is still all reasoning.
    """
    stripped = text.lstrip()
    if stripped.startswith(THINK_OPEN):
        end = stripped.find(THINK_CLOSE)
        return "" if end == -1 else stripped[end + len(THINK_CLOSE):].strip()

    # Some chat templates drop the opening tag: "reasoning...</think>answer".
    end = text.find(THINK_CLOSE)
    if end != -1 and THINK_OPEN not in text[:end] and text[:end].count("`") % 2 == 0:
        return text[end + len(THINK_CLOSE):].strip()
    return text.strip()
