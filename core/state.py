"""Live session state, keyed by (agent, session_id) so concurrent sessions never collide."""

from typing import Dict, List, Optional, Tuple

from .event import (
    DONE,
    NEEDS_INPUT,
    PERMISSION,
    PLAN,
    PROMPT,
    SESSION_END,
    SUBAGENT_END,
    SUBAGENT_START,
    TOOL_END,
    TOOL_START,
    AgentEvent,
)

Key = Tuple[str, str]


class Subagent:
    def __init__(
        self, subagent_id: Optional[str], kind: str, task: Optional[str], started: float
    ) -> None:
        self.id = subagent_id  # None until the agent reports the subagent started
        self.kind = kind
        self.task = task
        self.started = started
        self.tool: Optional[str] = None
        self.target: Optional[str] = None


class Session:
    def __init__(self, key: Key, display_name: str, order: int, now: float) -> None:
        self.key = key
        self.display_name = display_name
        self.order = order  # first-seen order, for a stable Agents view layout
        self.cwd = ""
        self.kind = ""
        self.tool: Optional[str] = None
        self.target: Optional[str] = None
        self.message: Optional[str] = None
        self.prompt: Optional[str] = None  # the prompt that started the current turn
        self.unsupervised = False
        self.since = now  # when `kind` last changed
        self.turn_started: Optional[float] = None
        self.subagents: List[Subagent] = []


def _find(session: Session, subagent_id: Optional[str], kind: str = "") -> Optional[Subagent]:
    """The subagent with `subagent_id`; for None, the first announced subagent of `kind`."""
    return next(
        (
            s
            for s in session.subagents
            if s.id == subagent_id and (subagent_id is not None or s.kind == kind)
        ),
        None,
    )


def _start_subagent(session: Session, event: AgentEvent, now: float) -> None:
    kind = event.tool or ""
    if event.subagent is not None:
        if _find(session, event.subagent) is not None:
            return
        announced = _find(session, None, kind)
        if announced is not None:
            announced.id = event.subagent
            return
    session.subagents.append(Subagent(event.subagent, kind, event.message, now))


def _end_subagent(session: Session, event: AgentEvent) -> None:
    # Without an id, an announced subagent that never reported starting.
    subagent = _find(session, event.subagent, event.tool or "")
    if subagent is not None:
        session.subagents.remove(subagent)


class SessionStore:
    def __init__(self) -> None:
        self._sessions: Dict[Key, Session] = {}
        self._next_order = 0

    def apply(self, event: AgentEvent, display_name: str, now: float) -> Optional[Session]:
        """Record `event`. Returns the session, or None once it has ended or isn't tracked."""
        key = (event.agent, event.session_id)
        session = self._sessions.get(key)
        if event.kind == SESSION_END:
            self._sessions.pop(key, None)
            return None
        if session is None:
            if event.kind == SUBAGENT_END or event.from_subagent:
                return None  # a straggler from a session already cleared
            session = Session(key, display_name, self._next_order, now)
            self._next_order += 1
            self._sessions[key] = session
        session.cwd = event.cwd
        if event.unsupervised is not None:
            session.unsupervised = event.unsupervised

        if event.kind == SUBAGENT_START:
            _start_subagent(session, event, now)
            return session
        if event.kind == SUBAGENT_END:
            _end_subagent(session, event)
            return session
        if event.from_subagent:
            subagent = _find(session, event.subagent)
            if subagent is not None and event.kind == TOOL_START:
                subagent.tool, subagent.target = event.tool, event.target
            return session
        if event.kind == PERMISSION and event.tool is None:
            if session.kind in (PLAN, NEEDS_INPUT):
                return session  # the prompt for the ask already showing
            tool, target = session.tool, session.target  # the call it's asking about
        else:
            tool, target = event.tool, event.target

        if event.kind == PROMPT:
            session.prompt = event.message
            session.subagents = []
            session.turn_started = now
        elif event.kind in (TOOL_START, TOOL_END) and session.turn_started is None:
            session.turn_started = now
        elif event.kind == DONE:
            session.turn_started = None
        if event.kind != session.kind:
            session.since = now
        session.kind, session.tool, session.target = event.kind, tool, target
        session.message = event.message
        return session

    def remove(self, key: Key) -> None:
        self._sessions.pop(key, None)

    def get(self, key: Key) -> Optional[Session]:
        return self._sessions.get(key)

    def all(self) -> List[Session]:
        return list(self._sessions.values())
