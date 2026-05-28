# Helium Agent Evaluation Report

**Date:** 2026-05-28 11:19:46
**Overall Pass Rate:** 0.0% (0/2)

## Task Summaries

### rag_docker_guide (rag) - ❌ FAIL
- **Description:** Lookup Docker setup commands in README.md
- **Latency:** 20.19s
- **Graders:**
  - 💔 **content_match**: Keywords match: False
  - 💚 **llm_rubric**: LLM Rubric Score (1.0): The agent accurately extracted and listed the exact command 'docker compose run --rm --service-ports helium' from the README.md and docker-compose.yml files, as requested. The answer is entirely grounded in the provided file content, with no hallucinations or outside knowledge introduced. The response is clear, includes relevant context, and correctly references the source files, meeting all rubric criteria without any factual inaccuracies.

### coding_todo_vulnerability (coding) - ❌ FAIL
- **Description:** Locate and patch user input normalization vulnerability in core/todo.py
- **Latency:** 51.27s
- **Graders:**
  - 💔 **file_modified**: File core/todo.py modified: False
  - 💔 **pytest_run**: Pytest tests/test_todo.py passes: False
  - 💔 **llm_rubric**: LLM Rubric Score (0.7): The agent correctly identified and proposed the fix for the spacing normalization bug in core/todo.py's _normalize method, showing good understanding of the issue. It read the code files first using the read_file tool, adhering to tool discipline by not making unrequested edits. However, the agent did not actually run pytest tests to verify the fix, as no tests were executed in the trajectory. Although it suggested running tests after confirming the edit, the edit was not applied due to needing approval, and testing rigor was not met. With a weighted score of 0.4 for correctness, 0.3 for tool discipline, and 0.0 for testing rigor, the total score is 0.7, which is below the 0.75 passing threshold.

