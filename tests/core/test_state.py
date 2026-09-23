from typing import Optional

from SublimeAgentOverview.core.event import (
    DONE,
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
from SublimeAgentOverview.core.state import Session, SessionStore
from SublimeAgentOverview.core.terminal import Terminal


def event(
    kind: str,
    session: str = "s1",
    cwd: str = "/p",
    tool: str = "",
    target: str = "",
    message: str = "",
    subagent: Optional[str] = None,
    unsupervised: Optional[bool] = None,
) -> AgentEvent:
    return AgentEvent(
        "claude",
        session,
        cwd,
        kind,
        tool or None,
        target or None,
        message or None,
        {},
        subagent,
        unsupervised,
    )


def apply_all(store: SessionStore, *events: AgentEvent, now: float = 0) -> Session:
    session = None
    for e in events:
        session = store.apply(e, "Claude", now)
    assert session is not None
    return session


def test_done_and_idle_sessions_stay_until_they_end() -> None:
    store = SessionStore()
    apply_all(store, event(DONE, session="a"), event(SESSION_START, session="b"))
    assert [s.kind for s in store.all()] == [DONE, SESSION_START]
    apply_all(store, event(SESSION_END, session="a"), event(PROMPT, session="b"))
    assert [s.key[1] for s in store.all()] == ["b"]


def test_sessions_from_any_project_are_all_kept() -> None:
    store = SessionStore()
    apply_all(store, event(PROMPT, session="a", cwd="/code/app"))
    apply_all(store, event(PROMPT, session="b", cwd="/elsewhere"))
    assert sorted(s.cwd for s in store.all()) == ["/code/app", "/elsewhere"]


def test_session_end_drops_the_session() -> None:
    store = SessionStore()
    apply_all(store, event(PROMPT))
    assert store.apply(event(SESSION_END), "Claude", 0) is None
    assert store.all() == []


def test_remove_drops_the_session() -> None:
    store = SessionStore()
    session = apply_all(store, event(PROMPT))
    store.remove(session.key)
    assert store.all() == []


def test_prompt_starts_a_turn_that_done_ends() -> None:
    store = SessionStore()
    session = apply_all(store, event(PROMPT, message="fix it"), now=10)
    assert (session.prompt, session.turn_started, session.since) == ("fix it", 10, 10)
    apply_all(store, event(TOOL_START, tool="Edit"), now=15)
    assert (session.turn_started, session.since) == (10, 15)
    apply_all(store, event(DONE), now=20)
    assert (session.turn_started, session.since, session.prompt) == (None, 20, "fix it")


def test_a_tool_call_starts_a_turn_whose_prompt_was_missed() -> None:
    session = apply_all(SessionStore(), event(TOOL_START, tool="Edit"), now=5)
    assert session.turn_started == 5


def test_permission_without_a_tool_keeps_the_call_it_asks_about() -> None:
    session = apply_all(
        SessionStore(),
        event(TOOL_START, tool="Bash", target="make"),
        event(PERMISSION, message="Claude needs your permission to use Bash"),
    )
    assert (session.kind, session.tool, session.target) == (PERMISSION, "Bash", "make")


def test_permission_prompt_for_a_plan_or_question_keeps_that_ask() -> None:
    for ask in (PLAN, NEEDS_INPUT):
        session = apply_all(SessionStore(), event(ask, message="the ask"), event(PERMISSION))
        assert (session.kind, session.message) == (ask, "the ask")


def test_unsupervised_is_kept_until_reported_otherwise() -> None:
    store = SessionStore()
    session = apply_all(store, event(PROMPT, unsupervised=True), event(TOOL_START))
    assert session.unsupervised
    apply_all(store, event(TOOL_END, unsupervised=False))
    assert not session.unsupervised


def test_announced_subagent_is_claimed_by_the_start_of_its_type() -> None:
    store = SessionStore()
    session = apply_all(
        store,
        event(PROMPT),
        event(SUBAGENT_START, tool="Explore", message="find callers"),
        event(SUBAGENT_START, tool="Plan", message="sketch"),
        event(SUBAGENT_START, tool="Plan", subagent="p1"),
        event(SUBAGENT_START, tool="Explore", subagent="e1"),
    )
    assert [(s.id, s.kind, s.task) for s in session.subagents] == [
        ("e1", "Explore", "find callers"),
        ("p1", "Plan", "sketch"),
    ]


def test_unannounced_subagent_start_adds_one_once() -> None:
    session = apply_all(
        SessionStore(),
        event(PROMPT),
        event(SUBAGENT_START, tool="Explore", subagent="e1"),
        event(SUBAGENT_START, tool="Explore", subagent="e1"),
    )
    assert [(s.id, s.task) for s in session.subagents] == [("e1", None)]


def test_subagent_tool_calls_update_the_subagent_not_the_parent() -> None:
    session = apply_all(
        SessionStore(),
        event(TOOL_START, tool="Agent"),
        event(SUBAGENT_START, tool="Explore", subagent="e1"),
        event(TOOL_START, tool="Grep", target="_state", subagent="e1"),
        event(TOOL_END, tool="Grep", target="_state", subagent="e1"),
    )
    assert (session.kind, session.tool) == (TOOL_START, "Agent")
    assert (session.subagents[0].tool, session.subagents[0].target) == ("Grep", "_state")


def test_subagent_end_removes_it_without_touching_the_parent() -> None:
    session = apply_all(
        SessionStore(),
        event(TOOL_START, tool="Edit"),
        event(SUBAGENT_START, tool="Explore", subagent="e1"),
        event(SUBAGENT_START, tool="Plan"),
        event(SUBAGENT_END, subagent="e1"),
        event(SUBAGENT_END, tool="Plan"),
    )
    assert session.subagents == []
    assert session.kind == TOOL_START


def test_linked_subagent_outlives_the_end_of_its_announcement() -> None:
    # A background subagent's spawning call returns while the subagent keeps running.
    session = apply_all(
        SessionStore(),
        event(SUBAGENT_START, tool="Explore", message="scan"),
        event(SUBAGENT_START, tool="Explore", subagent="e1"),
        event(SUBAGENT_END, tool="Explore"),
    )
    assert [s.id for s in session.subagents] == ["e1"]


def test_a_new_prompt_forgets_the_last_turns_subagents() -> None:
    session = apply_all(
        SessionStore(), event(SUBAGENT_START, tool="Explore", subagent="e1"), event(PROMPT)
    )
    assert session.subagents == []


def test_subagent_stragglers_do_not_revive_a_cleared_session() -> None:
    store = SessionStore()
    assert store.apply(event(SUBAGENT_END, subagent="e1"), "Claude", 0) is None
    assert store.apply(event(TOOL_END, tool="Read", subagent="e1"), "Claude", 0) is None
    assert store.all() == []


def test_terminal_is_kept_when_a_later_event_has_none() -> None:
    store = SessionStore()
    tab = Terminal("Apple_Terminal", "/dev/ttys010")
    session = apply_all(store, event(PROMPT)._replace(terminal=tab), event(DONE))
    assert session.terminal == tab
