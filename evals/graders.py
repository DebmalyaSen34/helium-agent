import subprocess
import hashlib
import os
import json
import re
from typing import List, Dict, Any
from core.llm import call_llm_once

class FileModifiedGrader:
    def __init__(self, path: str):
        self.path = path
        self.baseline_hash = self._get_hash()

    def _get_hash(self) -> str:
        if not os.path.exists(self.path):
            return ""
        try:
            with open(self.path, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()
        except Exception:
            return ""

    def grade(self) -> bool:
        current_hash = self._get_hash()
        # Verify it has changed, and it actually exists now
        return current_hash != self.baseline_hash and current_hash != ""

class PytestRunGrader:
    def __init__(self, test_path: str):
        self.test_path = test_path

    def grade(self, transcript: str = "") -> bool:
        try:
            res = subprocess.run(["pytest", self.test_path], capture_output=True, text=True, timeout=30)
            return res.returncode == 0
        except Exception:
            return False

class ContentMatchGrader:
    def __init__(self, keywords: List[str], case_sensitive: bool = False):
        self.keywords = keywords
        self.case_sensitive = case_sensitive

    def grade(self, response_text: str) -> bool:
        text = response_text if self.case_sensitive else response_text.lower()
        for kw in self.keywords:
            target = kw if self.case_sensitive else kw.lower()
            if target not in text:
                return False
        return True

class LlmRubricGrader:
    def __init__(self, rubric_path: str):
        self.rubric_path = rubric_path

    def grade(self, prompt: str, response: str, transcript: str) -> Dict[str, Any]:
        # Read the rubric template
        if not os.path.exists(self.rubric_path):
            return {"score": 0.0, "passed": False, "reasoning": f"Rubric file not found at {self.rubric_path}"}
            
        with open(self.rubric_path, "r") as f:
            rubric = f.read()

        system_msg = (
            "You are an expert AI evaluator. Grade the agent's performance against the provided rubric.\n"
            "Respond strictly with a JSON object containing keys: 'score' (float 0.0-1.0), 'passed' (bool), and 'reasoning' (str)."
        )
        user_msg = (
            f"=== RUBRIC ===\n{rubric}\n\n"
            f"=== USER PROMPT ===\n{prompt}\n\n"
            f"=== AGENT TEXT RESPONSE ===\n{response}\n\n"
            f"=== AGENT TRAJECTORY/TRANSCRIPT ===\n{transcript}\n"
        )
        
        try:
            messages = [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg}
            ]
            reply_text, _ = call_llm_once(messages)
            
            # Simple JSON extraction
            match = re.search(r"\{.*\}", reply_text, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            return {"score": 0.0, "passed": False, "reasoning": f"Failed to parse model JSON: {reply_text}"}
        except Exception as e:
            return {"score": 0.0, "passed": False, "reasoning": f"Error during model-based grading: {e}"}
