"""Stands in for `helium -p` in benchmark-runner tests.

Copies $FAKE_HELIUM_OVERLAY (a task's solution/ folder) into the workspace when set,
then prints the JSON report that `helium -p --json` would print.
"""

import json
import os
import shutil
import sys

workspace = sys.argv[1]
overlay = os.environ.get("FAKE_HELIUM_OVERLAY")
if overlay:
    shutil.copytree(overlay, workspace, dirs_exist_ok=True)
print("● write_file(...)", file=sys.stderr)
print(json.dumps({
    "result": "done",
    "stop_reason": "final",
    "is_error": False,
    "duration_s": 0.1,
    "model": "fake",
    "num_requests": 2,
    "num_tool_calls": 1,
    "usage": {"prompt_tokens": 1000, "completion_tokens": 50},
    "tools_used": {"write_file": 1},
    "denied_tools": [],
}))
