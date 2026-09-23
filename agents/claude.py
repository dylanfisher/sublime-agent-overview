"""Claude Code adapter, fed by Claude Code hooks that POST their JSON input to us."""

import json
import os
import re
import shutil
from typing import Any, Callable, Dict, List, Optional, cast

from ..core.adapter import Adapter
from ..core.event import (
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
    shorten,
)

NAME = "claude"

# Every hook we install. PermissionRequest is left out on purpose: a hook there sits between
# Claude Code and its own permission prompt, and this plugin only watches. `Notification`
# reports the same prompt after the fact.
HOOKS = (
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
)
SIMPLE_KINDS = {
    "SessionStart": SESSION_START,
    "SessionEnd": SESSION_END,
    "UserPromptSubmit": PROMPT,
    "Stop": DONE,
}

SUBAGENT_TOOLS = ("Task", "Agent")  # a call to one of these spawns a subagent
DEFAULT_SUBAGENT_TYPE = "general-purpose"
# A background subagent's spawning call returns this status at launch, with the subagent's id;
# the subagent keeps running until its SubagentStop.
ASYNC_LAUNCHED = "async_launched"
PLAN_TOOL = "ExitPlanMode"  # calling it puts the plan up for approval
QUESTION_TOOL = "AskUserQuestion"
PLAN_READY = "Plan ready for review"
UNSUPERVISED_MODES = ("bypassPermissions", "dontAsk")

# A background task finishing reaches the agent as a prompt of this XML; its summary says which.
TASK_NOTIFICATION = "<task-notification>"
TASK_SUMMARY_RE = re.compile(r"<summary>(.*?)</summary>", re.DOTALL)
TASK_FINISHED = "Background task finished"

# Notification types: the permission prompt, the question/elicitation, and ones we drop.
# `idle_prompt` fires a minute after every finished turn, whether or not anything is wrong.
PERMISSION_NOTIFICATIONS = ("permission_prompt", "elicitation_dialog")
IGNORED_NOTIFICATIONS = ("idle_prompt", "agent_completed")
# Older payloads have no notification_type; these phrases in the message mean a plan.
PLAN_PHRASES = ("plan is ready", "approve this plan", "exit plan mode", "ready to execute")

# tool_input keys that make a good label, most specific first. Paths show as basenames.
TARGET_KEYS = ("file_path", "notebook_path", "command", "pattern", "url", "query", "description")
PATH_KEYS = ("file_path", "notebook_path")

COMMAND = (
    "curl -s --max-time 1 -X POST --data-binary @- http://127.0.0.1:{port}/event/"
    + NAME
    + " || true"
)
COMMAND_RE = re.compile(r"http://127\.0\.0\.1:\d+/event/" + NAME + r"(\s|$)")

JsonObject = Dict[str, Any]


def _object(value: Any) -> JsonObject:
    """`value` as a JSON object; empty when it is anything else, so every key reads as absent."""
    return cast(JsonObject, value) if isinstance(value, dict) else {}


def _target(tool_input: Any) -> Optional[str]:
    fields = _object(tool_input)
    for key in TARGET_KEYS:
        value = fields.get(key)
        if isinstance(value, str) and value.strip():
            return shorten(os.path.basename(value) if key in PATH_KEYS else value)
    return None


def _string(payload: JsonObject, key: str) -> Optional[str]:
    value = payload.get(key)
    return value if isinstance(value, str) else None


def _prompt(payload: JsonObject) -> Optional[str]:
    """The prompt text, or a background task's summary in place of its notification XML."""
    prompt = _string(payload, "prompt")
    if prompt is None or not prompt.lstrip().startswith(TASK_NOTIFICATION):
        return prompt
    summary = TASK_SUMMARY_RE.search(prompt)
    # The view quotes prompts, so the summary's own double quotes become single.
    return summary.group(1).strip().replace('"', "'") if summary else TASK_FINISHED


def _is_ours(hook: Any) -> bool:
    command = _object(hook).get("command")
    return isinstance(command, str) and COMMAND_RE.search(command) is not None


def _strip_ours(groups: List[Any]) -> int:
    """Remove our hook entries from an event's matcher groups, in place. Returns count removed."""
    removed = 0
    for group in list(groups):
        hooks = _object(group).get("hooks")
        if not isinstance(hooks, list):
            continue
        entries = cast(List[Any], hooks)
        kept = [h for h in entries if not _is_ours(h)]
        removed += len(entries) - len(kept)
        if not kept and len(entries) > 0:
            groups.remove(group)
        else:
            entries[:] = kept
    return removed


def _commands(group: Any) -> List[str]:
    hooks = _object(group).get("hooks")
    if not isinstance(hooks, list):
        return []
    commands = (_object(h).get("command") for h in cast(List[Any], hooks))
    return [c for c in commands if isinstance(c, str)]


EventMaker = Callable[..., AgentEvent]


def _notification(payload: JsonObject, event: EventMaker) -> Optional[AgentEvent]:
    kind_name = _string(payload, "notification_type")
    message = _string(payload, "message")
    if kind_name in IGNORED_NOTIFICATIONS:
        return None
    text = (message or "").lower()
    if any(phrase in text for phrase in PLAN_PHRASES):
        return event(PLAN, message=message)
    if kind_name in PERMISSION_NOTIFICATIONS or (kind_name is None and "permission" in text):
        return event(PERMISSION, message=message)
    return event(NEEDS_INPUT, message=message)


def _question(tool_input: Any) -> Optional[str]:
    questions = _object(tool_input).get("questions")
    if not isinstance(questions, list) or not questions:
        return None
    text = _object(cast(List[Any], questions)[0]).get("question")
    return text if isinstance(text, str) else None


def _tool_event(name: str, payload: JsonObject, is_main: bool, event: EventMaker) -> AgentEvent:
    """PreToolUse / PostToolUse: a tool call, or one of the calls that mean more than that."""
    tool = _string(payload, "tool_name")
    tool_input = payload.get("tool_input")
    fields = _object(tool_input)
    starting = name == "PreToolUse"
    if tool in SUBAGENT_TOOLS:
        kind = fields.get("subagent_type")
        task = fields.get("description")
        result = _object(payload.get("tool_response"))
        launched = result.get("agentId") if result.get("status") == ASYNC_LAUNCHED else None
        return event(
            SUBAGENT_START if starting or launched else SUBAGENT_END,
            tool=kind if isinstance(kind, str) else DEFAULT_SUBAGENT_TYPE,
            message=task if isinstance(task, str) else None,
            of=launched if isinstance(launched, str) else None,
        )
    if starting and is_main and tool == PLAN_TOOL:
        return event(PLAN, message=PLAN_READY)
    if starting and is_main and tool == QUESTION_TOOL:
        return event(NEEDS_INPUT, message=_question(tool_input))
    kind = TOOL_START if starting else TOOL_END
    return event(kind, tool=tool, target=_target(tool_input) if tool else None)


class ClaudeAdapter(Adapter):
    name = NAME
    display_name = "Claude"
    can_install = True

    def __init__(self, settings_path: str = "~/.claude/settings.json") -> None:
        self.settings_path = os.path.expanduser(settings_path)

    def parse(self, payload: JsonObject) -> Optional[AgentEvent]:
        name = _string(payload, "hook_event_name") or ""
        if name not in HOOKS:
            return None
        session_id = _string(payload, "session_id")
        cwd = _string(payload, "cwd")
        if not session_id or not cwd:
            raise ValueError("missing session_id or cwd")
        mode = _string(payload, "permission_mode")
        unsupervised = None if mode is None else mode in UNSUPERVISED_MODES
        subagent = _string(payload, "agent_id")

        def event(
            kind: str,
            tool: Optional[str] = None,
            target: Optional[str] = None,
            message: Optional[str] = None,
            of: Optional[str] = subagent,
        ) -> AgentEvent:
            return AgentEvent(
                NAME, session_id, cwd, kind, tool, target, message, payload, of, unsupervised
            )

        if name in SIMPLE_KINDS:
            return event(SIMPLE_KINDS[name], message=_prompt(payload))
        if name == "Notification":
            return _notification(payload, event)
        if name == "StopFailure":
            reason = _string(payload, "error_type") or _string(payload, "message")
            return event(ERROR, message=reason)
        if name == "SubagentStart":
            return event(SUBAGENT_START, tool=_string(payload, "agent_type"))
        if name == "SubagentStop":
            if subagent is None:
                raise ValueError("SubagentStop without agent_id")
            return event(SUBAGENT_END, tool=_string(payload, "agent_type"))
        return _tool_event(name, payload, subagent is None, event)

    def install_hooks(self, port: int) -> str:
        settings = self._load()
        hooks = self._hooks(settings)
        command = COMMAND.format(port=port)
        added = 0
        for event_name in HOOKS:
            groups = cast(List[Any], hooks.setdefault(event_name, []))
            if any(command in _commands(g) for g in groups):
                continue
            _strip_ours(groups)  # an entry for a different port
            groups.append({"hooks": [{"type": "command", "command": command}]})
            added += 1
        if added:
            self._save(settings)
        return f"Claude hooks: {added} added, {len(HOOKS) - added} already present"

    def uninstall_hooks(self) -> str:
        settings = self._load()
        hooks = self._hooks(settings)
        removed = 0
        for event_name in list(hooks):
            groups = hooks[event_name]
            if not isinstance(groups, list):
                continue
            count = _strip_ours(cast(List[Any], groups))
            removed += count
            if count and not groups:
                del hooks[event_name]
        if removed:
            if not hooks:
                del settings["hooks"]
            self._save(settings)
        return f"Claude hooks: {removed} removed"

    def _load(self) -> JsonObject:
        if not os.path.exists(self.settings_path):
            return {}
        with open(self.settings_path, encoding="utf-8") as f:
            settings: Any = json.load(f)
        if not isinstance(settings, dict):
            raise ValueError(f"{self.settings_path} is not a JSON object")
        return cast(JsonObject, settings)

    def _hooks(self, settings: JsonObject) -> JsonObject:
        hooks = settings.setdefault("hooks", {})
        if not isinstance(hooks, dict):
            raise ValueError(f'"hooks" in {self.settings_path} is not a JSON object')
        return cast(JsonObject, hooks)

    def _save(self, settings: JsonObject) -> None:
        if os.path.exists(self.settings_path):
            shutil.copy2(self.settings_path, self.settings_path + ".bak")
        os.makedirs(os.path.dirname(self.settings_path), exist_ok=True)
        with open(self.settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
            f.write("\n")
