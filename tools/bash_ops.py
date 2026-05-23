import subprocess
import logging

logger = logging.getLogger(__name__)

def execute_bash(command: str) -> str:
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30.0
        )
        
        output_parts = []
        if result.stdout:
            output_parts.append(result.stdout)
        if result.stderr:
            output_parts.append(f"[stderr]\n{result.stderr}")

        if not output_parts:
            return f"Command executed sucessfully with exit code {result.returncode} (no output)."

        return "\n".join(output_parts)

    except subprocess.TimeoutExpired as e:
        stdout_captured = e.stdout if isinstance(e.stdout, str) else (e.stdout.decode() if e.stdout else "")

        stderr_captured = e.stderr if isinstance(e.stderr, str) else (e.stderr.decode() if e.stderr else "")

        err_msg = "Error: Command timed out after 30 seconds."
        if stdout_captured:
            err_msg += f"\nStdout captured so far:\n{stdout_captured}"
        if stderr_captured:
            err_msg += f"\nStderr captured so far:\n{stderr_captured}"

        return err_msg

    except Exception as e:
        logger.error(f"Error executing command: {e}", exc_info=True)
        return f"Error executing command: {str(e)}"

def is_command_safe(command: str) -> bool:
    """Classifies a bash command as safe (read-only) or risky (modifying)."""
    # List of known safe read-only commands
    SAFE_COMMANDS = {
        "ls", "pwd", "git status", "git diff", "git log", 
        "cat", "grep", "find", "du", "df", "head", "tail", 
        "file", "which", "echo", "printenv", "uname"
    }
    
    # Any command containing modifying keywords, write redirections, or execution binaries is risky
    if ">" in command:
        return False
        
    # Risky keywords that shouldn't appear anywhere in a "safe" command
    RISKY_KEYWORDS = {
        "rm ", "mv ", "cp ", "touch ", "mkdir ", "chmod ", "chown ", 
        "git commit", "git push", "git checkout", "git reset", "git merge",
        "curl ", "wget ", "ssh ", "python ", "python3 ", "node ", "npm ", 
        "pip ", "pip3 ", "yarn ", "docker ", "sudo ", "make ", "gcc "
    }
    
    for keyword in RISKY_KEYWORDS:
        if keyword in command:
            return False
            
    # Normalize command and check parts
    # Split the command by shell separators
    import re
    parts = re.split(r'[;&|]+', command)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # Get the first word (the command binary/alias)
        words = part.split()
        if not words:
            continue
        first_word = words[0]
        # Handle simple git commands
        if first_word == "git":
            if len(words) > 1:
                git_subcommand = words[1]
                if git_subcommand not in {"status", "diff", "log", "show", "branch"}:
                    return False
            else:
                return False
        elif first_word not in SAFE_COMMANDS:
            return False
            
    return True

