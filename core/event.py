"""The agent-neutral event model every adapter maps into."""

from typing import Any, Dict, NamedTuple, Optional

from .terminal import Terminal

SESSION_START = "session_start"
SESSION_END = "session_end"
PROMPT = "prompt"
TOOL_START = "tool_start"
TOOL_END = "tool_end"
NEEDS_INPUT = "needs_input"  # the agent asked you something
PERMISSION = "permission"  # a tool call is waiting on your approval
PLAN = "plan"  # a plan is waiting on your approval
ERROR = "error"  # the turn stopped on a failure (rate limit, overload, ...)
DONE = "done"
SUBAGENT_START = "subagent_start"
SUBAGENT_END = "subagent_end"

KINDS = (
    SESSION_START,
    SESSION_END,
    PROMPT,
    TOOL_START,
    TOOL_END,
    NEEDS_INPUT,
    PERMISSION,
    PLAN,
    ERROR,
    DONE,
    SUBAGENT_START,
    SUBAGENT_END,
)

# Kinds that mean the agent is blocked on you.
ASKS = (PERMISSION, PLAN, NEEDS_INPUT)


class AgentEvent(NamedTuple):
    agent: str
    session_id: str
    cwd: str
    kind: str
    # For SUBAGENT_START / SUBAGENT_END, `tool` is the subagent's type and `message` its task.
    tool: Optional[str]
    target: Optional[str]
    message: Optional[str]
    raw: Dict[str, Any]
    # The subagent this event came from or is about. A SUBAGENT_START without one announces a
    # subagent the agent has not yet started; the next start of that type claims it.
    subagent: Optional[str] = None
    # Whether the session runs without asking permission; None when the payload doesn't say.
    unsupervised: Optional[bool] = None
    # The terminal tab the agent runs in, from the hook's headers rather than its payload.
    terminal: Optional[Terminal] = None

    @property
    def from_subagent(self) -> bool:
        """A subagent's own tool call, which leaves its parent session unchanged."""
        return self.subagent is not None and self.kind in (TOOL_START, TOOL_END)


def shorten(text: str, limit: int = 40) -> str:
    """First line of `text`, cut to `limit` characters with an ellipsis."""
    line = text.strip().splitlines()[0] if text.strip() else ""
    return line if len(line) <= limit else line[: limit - 1] + "…"
