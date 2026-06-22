from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

try:
    from platformdirs import user_config_dir
except ModuleNotFoundError:
    user_config_dir = None


APP_NAME = "helium-agent"
SKILL_FILENAME = "SKILL.md"
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)", re.DOTALL)


@dataclass
class Skill:
    name: str
    description: str
    trigger: str | None = None
    version: str | None = None
    argument_hint: str | None = None
    allowed_tools: list[str] = field(default_factory=list)
    model: str | None = None
    body: str = ""
    source_path: Path | None = None

    @property
    def is_slash_command(self) -> bool:
        return self.trigger is not None


def parse_skill_file(path: Path) -> Skill | None:
    """Parse a SKILL.md file. Returns None if invalid."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    match = FRONTMATTER_RE.match(text)
    if not match:
        return None

    raw_yaml, body = match.group(1), match.group(2).strip()

    try:
        meta: dict[str, Any] = yaml.safe_load(raw_yaml) or {}
    except yaml.YAMLError:
        return None

    if not isinstance(meta, dict):
        return None

    name = meta.get("name")
    if not name or not isinstance(name, str):
        return None

    description = meta.get("description", "")
    if not isinstance(description, str):
        description = str(description)

    trigger = meta.get("trigger")
    if trigger and isinstance(trigger, str):
        trigger = trigger.strip()
        if not trigger.startswith("/"):
            trigger = "/" + trigger
    else:
        trigger = None

    allowed_tools_raw = meta.get("allowed-tools", [])
    if isinstance(allowed_tools_raw, str):
        allowed_tools = [t.strip() for t in allowed_tools_raw.split(",") if t.strip()]
    elif isinstance(allowed_tools_raw, list):
        allowed_tools = [str(t).strip() for t in allowed_tools_raw if t]
    else:
        allowed_tools = []

    return Skill(
        name=name,
        description=description,
        trigger=trigger,
        version=meta.get("version"),
        argument_hint=meta.get("argument-hint"),
        allowed_tools=allowed_tools,
        model=meta.get("model"),
        body=body,
        source_path=path,
    )


def _skill_dirs(workspace: Path | None = None) -> list[Path]:
    """Return skill directories to scan, in priority order."""
    dirs: list[Path] = []

    # User-level skills
    if user_config_dir:
        dirs.append(Path(user_config_dir(APP_NAME)) / "skills")
    else:
        dirs.append(Path.home() / ".config" / APP_NAME / "skills")

    # Project-level skills
    if workspace:
        dirs.append(workspace / ".helium" / "skills")

    return dirs


def discover_skills(workspace: Path | None = None) -> list[Skill]:
    """Scan skill directories and return all valid skills."""
    skills: list[Skill] = []
    seen_names: set[str] = set()

    for skill_dir in _skill_dirs(workspace):
        if not skill_dir.is_dir():
            continue
        for entry in sorted(skill_dir.iterdir()):
            if not entry.is_dir():
                continue
            skill_file = entry / SKILL_FILENAME
            if not skill_file.is_file():
                continue
            skill = parse_skill_file(skill_file)
            if skill and skill.name not in seen_names:
                skills.append(skill)
                seen_names.add(skill.name)

    return skills


def match_skill_trigger(user_text: str, skills: list[Skill]) -> tuple[Skill, str] | None:
    """Match user input against skill triggers. Returns (skill, args) or None."""
    stripped = user_text.strip()
    for skill in skills:
        if not skill.trigger:
            continue
        if stripped == skill.trigger:
            return skill, ""
        if stripped.startswith(skill.trigger + " "):
            args = stripped[len(skill.trigger):].strip()
            return skill, args
    return None
