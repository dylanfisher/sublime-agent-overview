"""Agents view and log text. Pure formatting, no state."""

import os
import time
from typing import Dict, Iterable, List, NamedTuple, Optional, Tuple

from .event import (
    ASKS,
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
from .state import Key, Session, Subagent

VIEW_NAME = "Agent Overview"
HEADING = "Agent Overview"  # the first line of the Agents view
NEEDS_YOU_MARK = "🔴"  # prefixes the tab title while a session waits on you
NO_AGENTS = "No active agents\n"
THINKING = ("◐", "thinking")
SUBAGENT_GLYPH = "◦"
UNSUPERVISED_TAG = "bypass"

# kind -> (glyph, label). The syntax in Agents.sublime-syntax colors rows by these glyphs.
STATES: Dict[str, Tuple[str, str]] = {
    PERMISSION: ("■", "permission"),
    PLAN: ("◆", "plan"),
    NEEDS_INPUT: ("●", "waiting"),
    ERROR: ("✗", "error"),
    TOOL_START: ("▶", "working"),
    PROMPT: THINKING,
    TOOL_END: THINKING,
    DONE: ("✓", "done"),
    SESSION_START: ("○", "idle"),
}

# Kinds mid-turn, which time the whole turn. A kind not in STATES (a session first seen mid-turn
# has none yet) shows as thinking, so it counts too.
WORKING = (TOOL_START, PROMPT, TOOL_END)

HELP = """\
# Movement:
#    r = refresh
#    1-4 = jump to project
#    n = next session, N = next project
#    p = previous session, P = previous project
#
# Sessions:
#    enter = focus terminal tab
#    cmd+enter = open project folder
#    x = dismiss session
#    l = show log
"""

LABEL_WIDTH = max(len(label) for _, label in STATES.values())
# Fixed columns come first so the elapsed time never moves; free text follows it.
STATE_WIDTH = len("  ") + len("● ") + LABEL_WIDTH  # "  ● permission"
ELAPSED_WIDTH = len("99h59m ago")
DETAIL_LIMIT = 60
QUOTE_LIMIT = 50
LOG_LIMIT = 60


class AgentsView(NamedTuple):
    text: str
    owners: Dict[int, Key]  # line -> the session that line belongs to
    rows: List[int]  # the line of each session's own row, top to bottom
    projects: List[int]  # the line of each project's header, top to bottom


def _tool_label(tool: Optional[str], target: Optional[str]) -> str:
    return " ".join(part for part in (tool, target) if part)


def _quote(text: Optional[str]) -> str:
    return f'"{shorten(text, QUOTE_LIMIT)}"' if text and text.strip() else ""


def duration(seconds: float) -> str:
    """Compact elapsed time: "42s", "4m12s", "1h03m"."""
    total = max(0, int(seconds))
    if total < 60:
        return f"{total}s"
    if total < 3600:
        return f"{total // 60}m{total % 60:02d}s"
    return f"{total // 3600}h{total % 3600 // 60:02d}m"


def _state(session: Session) -> Tuple[str, str]:
    return STATES.get(session.kind, THINKING)


def _working(session: Session) -> bool:
    return session.kind in WORKING or session.kind not in STATES


def _detail(session: Session) -> str:
    kind = session.kind
    if kind in (PERMISSION, TOOL_START):
        text = _tool_label(session.tool, session.target) or shorten(
            session.message or "", DETAIL_LIMIT
        )
    elif kind == NEEDS_INPUT:
        text = _quote(session.message)
    elif kind == ERROR:
        text = shorten(session.message or "", DETAIL_LIMIT)
    elif kind == SESSION_START:
        text = ""
    else:
        text = _quote(session.prompt)
    if session.unsupervised:
        text = f"{text}  {UNSUPERVISED_TAG}" if text else UNSUPERVISED_TAG
    return text


def _elapsed(session: Session, now: float) -> str:
    if session.kind == DONE:
        return duration(now - session.since) + " ago"
    if _working(session) and session.turn_started is not None:
        return duration(now - session.turn_started)
    return duration(now - session.since)


def _project(cwd: str) -> str:
    return os.path.basename(os.path.normpath(cwd))


def _home_relative(cwd: str) -> str:
    path = os.path.normpath(cwd)
    home = os.path.expanduser("~")
    return "~" + path[len(home) :] if path == home or path.startswith(home + os.sep) else path


def _row(state: str, elapsed: str, detail: str) -> str:
    return f"{state:<{STATE_WIDTH}}  {elapsed:<{ELAPSED_WIDTH}}  {detail}".rstrip()


def _subagent_lines(subagents: List[Subagent], now: float) -> List[str]:
    kind_width = max(len(s.kind) for s in subagents)
    tasks = [_quote(s.task) for s in subagents]
    task_width = max(len(t) for t in tasks)
    lines: List[str] = []
    for index, (subagent, task) in enumerate(zip(subagents, tasks)):
        branch = "└" if index == len(subagents) - 1 else "├"
        activity = _tool_label(subagent.tool, subagent.target) or "starting"
        lines.append(
            _row(
                f"    {branch} {SUBAGENT_GLYPH}",
                duration(now - subagent.started),
                f"{subagent.kind:<{kind_width}}  {task:<{task_width}}  {activity}",
            )
        )
    return lines


def _summary(sessions: List[Session]) -> str:
    if not sessions:
        return "none"
    projects = len({os.path.normpath(s.cwd) for s in sessions})
    counts = {glyph: 0 for glyph, _ in STATES.values()}  # in STATES order
    for session in sessions:
        counts[_state(session)[0]] += 1
    parts = [
        "{} session{} in {} project{}".format(
            len(sessions), "" if len(sessions) == 1 else "s", projects, "" if projects == 1 else "s"
        ),
        "  ".join(f"{glyph} {n}" for glyph, n in counts.items() if n),
    ]
    subagents = sum(len(s.subagents) for s in sessions)
    if subagents:
        parts.append(
            "{} {} subagent{}".format(SUBAGENT_GLYPH, subagents, "" if subagents == 1 else "s")
        )
    return "  ·  ".join(parts)


def agents_view(sessions: Iterable[Session], now: float, server: str) -> AgentsView:
    """The Agents view: a header, then every session grouped by project, in first-seen order."""
    ordered = sorted(sessions, key=lambda s: s.order)
    lines = [HEADING, f"Server:   {server}", f"Sessions: {_summary(ordered)}", "", ""]
    owners: Dict[int, Key] = {}
    rows: List[int] = []
    headers: List[int] = []
    if not ordered:
        lines += [NO_AGENTS.rstrip("\n"), ""]

    projects: Dict[str, List[Session]] = {}
    for session in ordered:
        projects.setdefault(os.path.normpath(session.cwd), []).append(session)
    for cwd, group in projects.items():
        headers.append(len(lines))
        owners[len(lines)] = group[0].key
        count = f"  ·  {len(group)} sessions" if len(group) > 1 else ""
        lines.append(f"{_project(cwd)}  {_home_relative(cwd)}{count}")
        for session in group:
            glyph, label = _state(session)
            owners[len(lines)] = session.key
            rows.append(len(lines))
            lines.append(_row(f"  {glyph} {label}", _elapsed(session, now), _detail(session)))
            if session.subagents:
                for line in _subagent_lines(session.subagents, now):
                    owners[len(lines)] = session.key
                    lines.append(line)
        lines.append("")

    return AgentsView("\n".join(lines) + "\n" + HELP, owners, rows, headers)


def view_title(sessions: Iterable[Session]) -> str:
    """The Agents tab's title, flagged while any session waits on you."""
    if any(session.kind in ASKS for session in sessions):
        return f"{NEEDS_YOU_MARK} {VIEW_NAME} — needs input"
    return VIEW_NAME


def step(lines: List[int], line: int, forward: bool) -> Optional[int]:
    """The next entry of `lines` after `line` (or before it, going back); None past the end."""
    if forward:
        return next((n for n in lines if n > line), None)
    return next((n for n in reversed(lines) if n < line), None)


def _log_text(event: AgentEvent) -> str:
    kind = event.kind
    if kind == TOOL_START:
        return _tool_label(event.tool, event.target)
    if kind == TOOL_END:
        return f"{_tool_label(event.tool, event.target)} ✓"
    if kind == PROMPT:
        return "prompt: {}".format(shorten(event.message or "", LOG_LIMIT))
    if kind == NEEDS_INPUT:
        return "needs input: {}".format(event.message or "")
    if kind == PERMISSION:
        return f"permission: {event.message or _tool_label(event.tool, event.target)}"
    if kind == PLAN:
        return "plan ready"
    if kind == ERROR:
        return "error: {}".format(event.message or "")
    if kind == SUBAGENT_START:
        return "subagent {} started: {}".format(
            event.tool or "", shorten(event.message or "", LOG_LIMIT)
        )
    if kind == SUBAGENT_END:
        return "subagent {} finished".format(event.tool or event.subagent or "")
    if kind == SESSION_START:
        return f"session started in {event.cwd}"
    if kind == SESSION_END:
        return "session ended"
    return "done"


def log_line(event: AgentEvent, display_name: str, now: float) -> str:
    """One output panel line, e.g. "14:03:22 Claude [a1b2c3d4] Edit foo.py"."""
    stamp = time.strftime("%H:%M:%S", time.localtime(now))
    source = "↳ " if event.from_subagent else ""
    return f"{stamp} {display_name} [{event.session_id[:8]}] {source}{_log_text(event)}\n"
