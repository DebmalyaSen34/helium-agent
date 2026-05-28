import os
import sys
import yaml
import time
import argparse
import subprocess
from datetime import datetime
from typing import List, Dict, Any, Tuple
from rich.console import Console
from rich.table import Table

from evals.schema import TaskConfig
from evals.graders import FileModifiedGrader, PytestRunGrader, ContentMatchGrader, LlmRubricGrader
from core.llm import generate_response

console = Console()

def execute_agent_loop(prompt: str) -> Tuple[str, str]:
    """Run Helium Agent's AgenticLoop on prompt and capture final output + trace."""
    transcript_logs = []
    
    def on_tool_result(name: str, result: str):
        transcript_logs.append(f"Tool {name} result:\n{result}")

    def on_state(state: str):
        transcript_logs.append(f"State transition: {state}")

    reply = ""
    for chunk in generate_response(
        prompt,
        on_state=on_state,
        on_tool_result=on_tool_result,
        print_metrics=False
    ):
        if chunk:
            reply += chunk

    full_transcript = "\n\n".join(transcript_logs)
    return reply, full_transcript

def run_single_task(task: TaskConfig) -> Dict[str, Any]:
    console.print(f"[bold cyan]Running task:[/bold cyan] {task.id} - {task.description}")
    
    # 1. Setup
    if task.setup:
        subprocess.run(task.setup, shell=True, capture_output=True)
        
    # Baseline hash grader initialization
    file_modified_graders = []
    for g_cfg in task.graders:
        if g_cfg.type == "file_modified":
            file_modified_graders.append(FileModifiedGrader(g_cfg.params["path"]))

    start_time = time.time()
    
    # 2. Execute Agent Loop
    response, transcript = execute_agent_loop(task.input_prompt)
    
    latency = time.time() - start_time
    
    # 3. Grade results
    grader_results = []
    all_passed = True
    
    for g_cfg in task.graders:
        passed = False
        reason = ""
        
        if g_cfg.type == "file_modified":
            grader = next((g for g in file_modified_graders if g.path == g_cfg.params["path"]), None)
            if grader:
                passed = grader.grade()
            reason = f"File {g_cfg.params['path']} modified: {passed}"
            
        elif g_cfg.type == "pytest_run":
            grader = PytestRunGrader(g_cfg.params["test_path"])
            passed = grader.grade(transcript)
            reason = f"Pytest {g_cfg.params['test_path']} passes: {passed}"
            
        elif g_cfg.type == "content_match":
            grader = ContentMatchGrader(g_cfg.params["keywords"], g_cfg.params.get("case_sensitive", False))
            passed = grader.grade(response)
            reason = f"Keywords match: {passed}"
            
        elif g_cfg.type == "llm_rubric":
            rubric_path = os.path.join("evals", "templates", g_cfg.params["rubric"])
            grader = LlmRubricGrader(rubric_path)
            res = grader.grade(task.input_prompt, response, transcript)
            passed = res.get("passed", False)
            reason = f"LLM Rubric Score ({res.get('score', 0.0)}): {res.get('reasoning', '')}"

        if not passed:
            all_passed = False
            
        grader_results.append({
            "type": g_cfg.type,
            "passed": passed,
            "reason": reason
        })

    # 4. Teardown
    if task.teardown:
        subprocess.run(task.teardown, shell=True, capture_output=True)

    return {
        "id": task.id,
        "description": task.description,
        "category": task.category,
        "success": all_passed,
        "latency_sec": latency,
        "response": response,
        "graders": grader_results
    }

def main():
    parser = argparse.ArgumentParser(description="Helium Agent Eval Harness")
    parser.add_argument("--suite", choices=["coding", "rag", "all"], default="all")
    args = parser.parse_args()

    # Load tasks
    cases_dir = os.path.join("evals", "cases")
    tasks: List[TaskConfig] = []
    
    if not os.path.exists(cases_dir):
        console.print(f"[red]Cases directory not found at {cases_dir}[/red]")
        sys.exit(1)
        
    for root, _, files in os.walk(cases_dir):
        for f in files:
            if not f.endswith(".yaml") and not f.endswith(".yml"):
                continue
            path = os.path.join(root, f)
            with open(path, "r") as stream:
                data = yaml.safe_load(stream)
                task = TaskConfig.from_dict(data)
                if args.suite == "all" or task.category == args.suite:
                    tasks.append(task)

    results = []
    success_count = 0

    table = Table(title="Helium Evaluation Run Results")
    table.add_column("Task ID", style="cyan")
    table.add_column("Category", style="magenta")
    table.add_column("Success", style="bold")
    table.add_column("Latency", style="dim")

    for task in tasks:
        res = run_single_task(task)
        results.append(res)
        
        status = "[green]PASS[/green]" if res["success"] else "[red]FAIL[/red]"
        if res["success"]:
            success_count += 1
            
        table.add_row(res["id"], res["category"], status, f"{res['latency_sec']:.2f}s")

    console.print("\n")
    console.print(table)

    # Compile Markdown Report
    reports_dir = os.path.join("evals", "reports")
    os.makedirs(reports_dir, exist_ok=True)
    report_path = os.path.join(reports_dir, "latest_report.md")
    
    pass_rate = (success_count / len(tasks)) * 100 if tasks else 0.0
    
    with open(report_path, "w") as f:
        f.write(f"# Helium Agent Evaluation Report\n\n")
        f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**Overall Pass Rate:** {pass_rate:.1f}% ({success_count}/{len(tasks)})\n\n")
        f.write(f"## Task Summaries\n\n")
        for res in results:
            status = "✅ PASS" if res["success"] else "❌ FAIL"
            f.write(f"### {res['id']} ({res['category']}) - {status}\n")
            f.write(f"- **Description:** {res['description']}\n")
            f.write(f"- **Latency:** {res['latency_sec']:.2f}s\n")
            f.write(f"- **Graders:**\n")
            for g in res["graders"]:
                g_status = "💚" if g["passed"] else "💔"
                f.write(f"  - {g_status} **{g['type']}**: {g['reason']}\n")
            f.write(f"\n")

    console.print(f"\n[bold green]Success![/bold green] Markdown report compiled at {report_path}")

if __name__ == "__main__":
    main()
