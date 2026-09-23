import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from SublimeAgentOverview.agents import REGISTRY, installable
from SublimeAgentOverview.agents.claude import ClaudeAdapter
from SublimeAgentOverview.core.event import (
    DONE,
    ERROR,
    NEEDS_INPUT,
    PERMISSION,
    PLAN,
    PROMPT,
    SESSION_END,
    SESSION_START,
    SUBAGENT_END,
    SUBAGENT_START,
    TOOL_END,
    TOOL_START,
    AgentEvent,
)

BASE = {"session_id": "abc123", "cwd": "/code/app", "transcript_path": "/t.jsonl"}
COMMAND = (
    "curl -s --max-time 1 -X POST --data-binary @- "
    '-H "X-Term-Program: $TERM_PROGRAM" -H "X-Term-TTY: $(ps -o tty= -p $PPID)" '
    "http://127.0.0.1:{}/event/claude || true"
)


def payload(hook: str, **fields: Any) -> Dict[str, Any]:
    return {**BASE, "hook_event_name": hook, **fields}


def parse(p: Dict[str, Any]) -> Optional[AgentEvent]:
    return ClaudeAdapter().parse(p)


@pytest.mark.parametrize(
    "hook,kind",
    [
        ("SessionStart", SESSION_START),
        ("SessionEnd", SESSION_END),
        ("UserPromptSubmit", PROMPT),
        ("PreToolUse", TOOL_START),
        ("PostToolUse", TOOL_END),
        ("Notification", NEEDS_INPUT),
        ("Stop", DONE),
        ("StopFailure", ERROR),
        ("SubagentStart", SUBAGENT_START),
    ],
)
def test_hook_events_map_to_kinds(hook: str, kind: str) -> None:
    event = parse(payload(hook))
    assert event is not None
    assert (event.agent, event.session_id, event.cwd, event.kind) == (
        "claude",
        "abc123",
        "/code/app",
        kind,
    )


def test_tool_event_targets_file_basename() -> None:
    event = parse(
        payload("PreToolUse", tool_name="Edit", tool_input={"file_path": "/code/app/src/foo.py"})
    )
    assert event is not None
    assert (event.tool, event.target) == ("Edit", "foo.py")


def test_tool_event_targets_shortened_command() -> None:
    command = "npm run test -- --watch=false --coverage --reporter=verbose\nsecond line"
    event = parse(payload("PostToolUse", tool_name="Bash", tool_input={"command": command}))
    assert event is not None
    assert event.target == "npm run test -- --watch=false --coverag…"
    assert event.target is not None and len(event.target) == 40


def test_tool_without_a_known_input_has_no_target() -> None:
    event = parse(payload("PreToolUse", tool_name="TodoWrite", tool_input={"todos": []}))
    assert event is not None
    assert (event.tool, event.target) == ("TodoWrite", None)


def test_prompt_and_notification_carry_their_text() -> None:
    prompt = parse(payload("UserPromptSubmit", prompt="fix the bug"))
    note = parse(payload("Notification", message="Claude needs your permission to use Bash"))
    assert prompt is not None and prompt.message == "fix the bug"
    assert note is not None and note.message == "Claude needs your permission to use Bash"


def kinds_of(*payloads: Dict[str, Any]) -> List[Optional[str]]:
    return [e.kind if e else None for e in map(parse, payloads)]


def test_notifications_split_into_permission_plan_and_question() -> None:
    assert kinds_of(
        payload("Notification", notification_type="permission_prompt", message="Needs Bash"),
        payload("Notification", notification_type="elicitation_dialog", message="Pick one"),
        payload("Notification", notification_type="agent_needs_input", message="Which shell?"),
        payload("Notification", message="Claude needs your permission to use Bash"),
        payload("Notification", message="Claude is waiting for your input"),
        payload("Notification", notification_type="permission_prompt", message="Exit plan mode?"),
    ) == [PERMISSION, PERMISSION, NEEDS_INPUT, PERMISSION, NEEDS_INPUT, PLAN]


def test_a_background_task_notification_shows_its_summary() -> None:
    notification = (
        "<task-notification>\n<task-id>t1</task-id>\n<status>completed</status>\n"
        '<summary>Agent "find callers" finished</summary>\n</task-notification>'
    )
    with_summary = parse(payload("UserPromptSubmit", prompt=notification))
    without = parse(payload("UserPromptSubmit", prompt="<task-notification>\n</task-notification>"))
    assert with_summary is not None and with_summary.message == "Agent 'find callers' finished"
    assert without is not None and without.message == "Background task finished"


def test_idle_and_completed_notifications_are_ignored() -> None:
    assert kinds_of(
        payload("Notification", notification_type="idle_prompt", message="Claude is idle"),
        payload("Notification", notification_type="agent_completed", message="Done"),
    ) == [None, None]


def test_plan_and_question_tools_are_asks() -> None:
    plan = parse(payload("PreToolUse", tool_name="ExitPlanMode", tool_input={"plan": "..."}))
    question = parse(
        payload(
            "PreToolUse",
            tool_name="AskUserQuestion",
            tool_input={"questions": [{"question": "zsh or fish?", "options": []}]},
        )
    )
    answered = parse(payload("PostToolUse", tool_name="AskUserQuestion", tool_input={}))
    assert plan is not None and (plan.kind, plan.message) == (PLAN, "Plan ready for review")
    assert question is not None and (question.kind, question.message) == (
        NEEDS_INPUT,
        "zsh or fish?",
    )
    assert answered is not None and answered.kind == TOOL_END


def test_a_subagents_plan_or_question_is_just_its_tool_call() -> None:
    event = parse(payload("PreToolUse", tool_name="ExitPlanMode", agent_id="a1", tool_input={}))
    assert event is not None and (event.kind, event.subagent) == (TOOL_START, "a1")


def test_stop_failure_carries_the_reason() -> None:
    event = parse(payload("StopFailure", error_type="rate_limit"))
    assert event is not None and (event.kind, event.message) == (ERROR, "rate_limit")


def test_spawning_call_announces_and_ends_a_subagent() -> None:
    fields = {"subagent_type": "Explore", "description": "find callers", "prompt": "..."}
    start = parse(payload("PreToolUse", tool_name="Agent", tool_input=fields))
    end = parse(payload("PostToolUse", tool_name="Task", tool_input=fields))
    untyped = parse(payload("PreToolUse", tool_name="Task", tool_input={"description": "x"}))
    assert start is not None and (start.kind, start.tool, start.message, start.subagent) == (
        SUBAGENT_START,
        "Explore",
        "find callers",
        None,
    )
    assert end is not None and (end.kind, end.tool, end.subagent) == (SUBAGENT_END, "Explore", None)
    assert untyped is not None and untyped.tool == "general-purpose"


def test_background_launch_links_the_subagent_instead_of_ending_it() -> None:
    fields = {"subagent_type": "Explore", "description": "find callers"}
    response = {"isAsync": True, "status": "async_launched", "agentId": "a1"}
    launched = parse(
        payload("PostToolUse", tool_name="Agent", tool_input=fields, tool_response=response)
    )
    assert launched is not None and (launched.kind, launched.tool, launched.subagent) == (
        SUBAGENT_START,
        "Explore",
        "a1",
    )


def test_subagent_events_carry_its_id_and_type() -> None:
    start = parse(payload("SubagentStart", agent_id="a1", agent_type="Explore"))
    stop = parse(payload("SubagentStop", agent_id="a1", agent_type="Explore"))
    tool = parse(payload("PreToolUse", agent_id="a1", tool_name="Grep", tool_input={}))
    assert start is not None and (start.kind, start.subagent, start.tool) == (
        SUBAGENT_START,
        "a1",
        "Explore",
    )
    assert stop is not None and (stop.kind, stop.subagent) == (SUBAGENT_END, "a1")
    assert tool is not None and (tool.kind, tool.subagent) == (TOOL_START, "a1")


def test_subagent_stop_without_an_id_is_rejected() -> None:
    with pytest.raises(ValueError):
        parse(payload("SubagentStop"))


def test_permission_mode_sets_unsupervised() -> None:
    events = [
        parse(payload("UserPromptSubmit", permission_mode=mode))
        for mode in ("bypassPermissions", "dontAsk", "default", "plan")
    ]
    assert [e.unsupervised for e in events if e] == [True, True, False, False]
    plain = parse(payload("Stop"))
    assert plain is not None and plain.unsupervised is None


def test_raw_payload_is_kept() -> None:
    p = payload("Stop", stop_hook_active=False)
    event = parse(p)
    assert event is not None and event.raw == p


def test_unknown_hook_event_is_ignored() -> None:
    assert parse(payload("PreCompact")) is None


def test_missing_session_id_is_rejected() -> None:
    with pytest.raises(ValueError):
        parse({"hook_event_name": "Stop", "cwd": "/code/app"})


def test_registered_and_installable() -> None:
    assert isinstance(REGISTRY["claude"], ClaudeAdapter)
    assert REGISTRY["claude"] in installable()


# --- hook installer (always against a temp file, never ~/.claude) ---


def read(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text())


def our_commands(settings: Dict[str, Any], event: str) -> List[str]:
    return [
        h["command"]
        for g in settings.get("hooks", {}).get(event, [])
        for h in g["hooks"]
        if "/event/claude" in h["command"]
    ]


def test_install_into_missing_file_adds_every_event(tmp_path: Path) -> None:
    path = tmp_path / ".claude" / "settings.json"
    ClaudeAdapter(str(path)).install_hooks(47823)
    settings = read(path)
    assert sorted(settings["hooks"]) == sorted(
        [
            "SessionStart",
            "SessionEnd",
            "UserPromptSubmit",
            "PreToolUse",
            "PostToolUse",
            "Notification",
            "Stop",
            "StopFailure",
            "SubagentStart",
            "SubagentStop",
        ]
    )
    assert our_commands(settings, "Stop") == [COMMAND.format(47823)]


def test_install_keeps_existing_hooks_and_settings_and_backs_up(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    guard = {"matcher": "Bash", "hooks": [{"type": "command", "command": "./guard.sh"}]}
    existing: Dict[str, Any] = {"model": "opus", "hooks": {"PreToolUse": [guard]}}
    path.write_text(json.dumps(existing))
    ClaudeAdapter(str(path)).install_hooks(47823)
    settings = read(path)
    assert settings["model"] == "opus"
    assert settings["hooks"]["PreToolUse"][0] == guard
    assert our_commands(settings, "PreToolUse") == [COMMAND.format(47823)]
    assert read(tmp_path / "settings.json.bak") == existing


def test_install_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    adapter = ClaudeAdapter(str(path))
    adapter.install_hooks(47823)
    first = path.read_text()
    summary = adapter.install_hooks(47823)
    assert path.read_text() == first
    assert summary == "Claude hooks: 0 added, 10 already present"


def test_install_on_a_new_port_replaces_our_entry(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    adapter = ClaudeAdapter(str(path))
    adapter.install_hooks(47823)
    adapter.install_hooks(50000)
    assert our_commands(read(path), "Stop") == [COMMAND.format(50000)]


def test_uninstall_removes_only_our_entries(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    theirs = {"matcher": "Bash", "hooks": [{"type": "command", "command": "./guard.sh"}]}
    path.write_text(json.dumps({"model": "opus", "hooks": {"PreToolUse": [theirs]}}))
    adapter = ClaudeAdapter(str(path))
    adapter.install_hooks(47823)
    assert adapter.uninstall_hooks() == "Claude hooks: 10 removed"
    assert read(path) == {"model": "opus", "hooks": {"PreToolUse": [theirs]}}


def test_uninstall_drops_the_hooks_key_it_emptied(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"model": "opus"}))
    adapter = ClaudeAdapter(str(path))
    adapter.install_hooks(47823)
    adapter.uninstall_hooks()
    assert read(path) == {"model": "opus"}


def test_uninstall_with_nothing_installed_does_not_write(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text('{"model": "opus"}')
    assert ClaudeAdapter(str(path)).uninstall_hooks() == "Claude hooks: 0 removed"
    assert path.read_text() == '{"model": "opus"}'
    assert not (tmp_path / "settings.json.bak").exists()


def test_settings_that_are_not_an_object_fail_loudly(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("[]")
    with pytest.raises(ValueError):
        ClaudeAdapter(str(path)).install_hooks(47823)
