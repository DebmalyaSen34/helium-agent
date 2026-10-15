from core.prompts import build_system_prompt
from tools.registry import AVAILABLE_TOOLS, TOOLSETS, build_openai_tools, tools_for


def test_every_toolset_names_real_tools():
    for names in TOOLSETS.values():
        assert set(names) <= set(AVAILABLE_TOOLS)


def test_modes_send_fewer_tools_than_the_full_registry():
    for mode in TOOLSETS:
        assert len(build_openai_tools(tools_for(mode))) < len(AVAILABLE_TOOLS)


def test_only_code_mode_offers_subagents():
    assert "delegate_task" in tools_for("code")
    assert "delegate_task" not in tools_for("chat")
    assert "delegate_task" not in tools_for("subagent")


def test_subagent_guidance_follows_the_toolset():
    assert "<subagent_workflow>" in build_system_prompt("code", extra="rules")
    assert "<subagent_workflow>" not in build_system_prompt("chat")


def test_web_search_stack_is_not_imported_at_startup():
    import subprocess
    import sys

    code = "import sys, main; print(sorted(m for m in ('bs4', 'tools.search', 'tools.research') if m in sys.modules))"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout
    assert out.strip() == "[]"
