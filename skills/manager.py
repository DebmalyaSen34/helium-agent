from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.table import Table

from skills.loader import SKILL_FILENAME, Skill, _skill_dirs

console = Console()


SKILL_TEMPLATE = """\
---
name: {name}
description: "Describe when to use this skill"
trigger: /{name}
version: "1.0"
argument-hint: "[optional-arg]"
allowed-tools: []
---

# {name}

Instructions for the LLM go here.
Explain what this skill does and how to handle it.
"""


def list_skills(skills: list[Skill]) -> str:
    """Format all skills as a rich table string."""
    if not skills:
        return "[dim]No skills installed. Use /skills create <name> to make one.[/dim]"

    table = Table(title="Installed Skills", show_lines=True)
    table.add_column("Name", style="cyan bold")
    table.add_column("Trigger", style="green")
    table.add_column("Description", max_width=50)
    table.add_column("Source", style="dim")

    for skill in skills:
        path_str = str(skill.source_path) if skill.source_path else ""
        source = "project" if ".helium" in path_str else "user"
        table.add_row(
            skill.name,
            skill.trigger or "[dim](contextual)[/dim]",
            skill.description[:80] if skill.description else "[dim]—[/dim]",
            source,
        )

    console.print(table)
    return ""


def create_skill(name: str, workspace: Path | None = None) -> Path:
    """Scaffold a new skill in the user skills directory. Returns the path."""
    skill_dir = _skill_dirs(workspace)[0] / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / SKILL_FILENAME
    skill_file.write_text(SKILL_TEMPLATE.format(name=name), encoding="utf-8")
    return skill_file


def remove_skill(name: str, workspace: Path | None = None) -> tuple[bool, str]:
    """Remove a skill by name from user skills dir. Returns (success, message)."""
    for skill_dir in _skill_dirs(workspace):
        target = skill_dir / name
        if target.is_dir():
            skill_file = target / SKILL_FILENAME
            if skill_file.is_file():
                import shutil
                shutil.rmtree(target)
                return True, f"Removed skill '{name}' from {skill_dir}"
    return False, f"Skill '{name}' not found"
