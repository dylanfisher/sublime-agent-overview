from typing import Optional, Tuple

import pytest

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
from SublimeAgentOverview.core.state import SessionStore
from SublimeAgentOverview.core.status import (
    HEADING,
    HELP,
    NO_AGENTS,
    STATE_WIDTH,
    AgentsView,
    agents_view,
    duration,
    log_line,
    step,
    view_title,
)

SERVER = "127.0.0.1:47823"


@pytest.fixture(autouse=True)
def home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", "/home/me")


def event(
    kind: str,
    session: str = "s1",
    agent: str = "claude",
    tool: str = "",
    target: str = "",
    message: str = "",
    cwd: str = "/home/me/app",
    subagent: Optional[str] = None,
    unsupervised: Optional[bool] = None,
) -> AgentEvent:
    return AgentEvent(
        agent,
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


def render(*events: Tuple[float, AgentEvent], now: float = 50) -> AgentsView:
    store = SessionStore()
    for at, e in events:
        store.apply(e, e.agent.capitalize(), at)
    return agents_view(store.all(), now, SERVER)


def body(view: AgentsView) -> str:
    """The view between the header and the help block."""
    assert view.text.endswith(HELP)
    return view.text[: -len(HELP)].split("\n", 5)[5]


def row(*events: AgentEvent) -> str:
    """The one session row the events leave."""
    view = render(*((0, e) for e in events))
    assert len(view.rows) == 1
    return view.text.splitlines()[view.rows[0]]


def test_each_state_has_its_glyph_label_and_detail() -> None:
    assert row(event(SESSION_START)) == "  ○ idle        50s"
    assert row(event(PROMPT, message="fix the bug")) == (
        '  ◐ thinking    50s         "fix the bug"'
    )
    assert row(event(TOOL_START, tool="Edit", target="foo.py")) == (
        "  ▶ working     50s         Edit foo.py"
    )
    assert row(event(TOOL_START, tool="Edit"), event(TOOL_END)) == "  ◐ thinking    50s"
    assert row(event(TOOL_START, tool="Bash", target="make"), event(PERMISSION)) == (
        "  ■ permission  50s         Bash make"
    )
    assert row(event(PLAN, message="Plan ready")) == "  ◆ plan        50s"
    assert row(event(NEEDS_INPUT, message="zsh or fish?")) == (
        '  ● waiting     50s         "zsh or fish?"'
    )
    assert row(event(ERROR, message="rate_limit")) == ("  ✗ error       50s         rate_limit")
    assert row(event(PROMPT, message="fix it"), event(DONE)) == (
        '  ✓ done        50s ago     "fix it"'
    )


def test_permission_without_a_known_call_shows_the_message() -> None:
    assert row(event(PERMISSION, message="Claude needs your permission")) == (
        "  ■ permission  50s         Claude needs your permission"
    )


def test_unsupervised_sessions_are_tagged() -> None:
    assert row(event(PROMPT, message="go", unsupervised=True)) == (
        '  ◐ thinking    50s         "go"  bypass'
    )
    assert row(event(SESSION_START, unsupervised=True)) == ("  ○ idle        50s         bypass")


def test_elapsed_stays_in_one_column_whatever_the_detail() -> None:
    view = render(
        (0, event(TOOL_START, session="a", tool="Bash", target="make test")),
        (0, event(PROMPT, session="b", message="x")),
        (0, event(SUBAGENT_START, session="b", tool="Explore", subagent="e1")),
    )
    lines = view.text.splitlines()
    columns = {lines[n].index("50s") for n in [*view.rows, view.rows[1] + 1]}
    assert columns == {STATE_WIDTH + 2}


def test_working_shows_turn_length_and_asks_show_time_waiting() -> None:
    view = render(
        (10, event(PROMPT, session="a")),
        (40, event(TOOL_START, session="a", tool="Read")),
        (70, event(TOOL_START, session="b", tool="Bash")),
        (90, event(PERMISSION, session="b")),
        now=100,
    )
    lines = view.text.splitlines()
    assert [lines[n].split()[2] for n in view.rows] == ["1m30s", "10s"]


def test_no_sessions_says_so() -> None:
    for view in (render(), render((0, event(PROMPT)), (0, event(SESSION_END)))):
        assert (
            view.text == f"{HEADING}\nServer:   {SERVER}\nSessions: none\n\n\n{NO_AGENTS}\n{HELP}"
        )
        assert (view.owners, view.rows, view.projects) == ({}, [], [])


def test_every_session_is_listed_under_its_project_in_first_seen_order() -> None:
    view = render(
        (0, event(TOOL_START, session="a", tool="Edit", target="status.py", cwd="/home/me/agent")),
        (0, event(TOOL_START, session="c", tool="Bash", target="make", cwd="/work/mulch")),
        (0, event(PROMPT, session="b", message="write tests", cwd="/home/me/agent/")),
        (0, event(PERMISSION, session="c", cwd="/work/mulch")),
        (0, event(PROMPT, session="e", message="fix stash", cwd="/home/me/git")),
        (40, event(DONE, session="e", cwd="/home/me/git")),
        (0, event(SESSION_START, session="f", cwd="/home/me")),
    )
    assert body(view) == (
        "agent  ~/agent  ·  2 sessions\n"
        "  ▶ working     50s         Edit status.py\n"
        '  ◐ thinking    50s         "write tests"\n'
        "\n"
        "mulch  /work/mulch\n"
        "  ■ permission  50s         Bash make\n"
        "\n"
        "git  ~/git\n"
        '  ✓ done        10s ago     "fix stash"\n'
        "\n"
        "me  ~\n"
        "  ○ idle        50s\n"
        "\n"
    )


def test_header_counts_states_projects_and_subagents() -> None:
    view = render(
        (0, event(PROMPT, session="a")),
        (0, event(SUBAGENT_START, session="a", tool="Explore", subagent="e1")),
        (0, event(TOOL_START, session="b", tool="Read", cwd="/x")),
        (0, event(PROMPT, session="c", cwd="/x")),
    )
    assert view.text.splitlines()[:3] == [
        HEADING,
        f"Server:   {SERVER}",
        "Sessions: 3 sessions in 2 projects  ·  ▶ 1  ◐ 2  ·  ◦ 1 subagent",
    ]
    assert render((0, event(PROMPT))).text.splitlines()[2] == (
        "Sessions: 1 session in 1 project  ·  ◐ 1"
    )


def test_subagents_are_a_tree_under_their_parent() -> None:
    view = render(
        (0, event(TOOL_START, tool="Agent")),
        (10, event(SUBAGENT_START, tool="Explore", message="find callers")),
        (20, event(SUBAGENT_START, tool="Plan", message="sketch layouts")),
        (30, event(SUBAGENT_START, tool="Explore", subagent="e1")),
        (40, event(TOOL_START, tool="Grep", target="_state", subagent="e1")),
        (50, event(SUBAGENT_START, tool="general-purpose", subagent="g1")),
        (60, event(SUBAGENT_END, tool="Plan")),
    )
    lines = view.text.splitlines()
    parent = view.rows[0]
    assert lines[parent + 1 : parent + 3] == [
        '    ├ ◦         40s         Explore          "find callers"  Grep _state',
        "    └ ◦         0s          general-purpose                  starting",
    ]
    assert view.owners[parent + 1] == view.owners[parent + 2] == ("claude", "s1")


def test_owners_rows_and_projects_index_the_text() -> None:
    view = render(
        (0, event(PERMISSION, session="a", cwd="/x")),
        (0, event(PROMPT, session="b")),
        (0, event(PROMPT, session="c")),
    )
    lines = view.text.splitlines()
    assert [lines[line] for line in view.projects] == ["x  /x", "app  ~/app  ·  2 sessions"]
    assert [view.owners[line][1] for line in view.rows] == ["a", "b", "c"]
    assert view.owners[view.projects[1]] == ("claude", "b")  # a project line belongs to its first


def test_step_moves_between_lines() -> None:
    assert step([3, 5, 9], 5, True) == 9
    assert step([3, 5, 9], 4, True) == 5
    assert step([3, 5, 9], 9, True) is None
    assert step([3, 5, 9], 5, False) == 3
    assert step([3, 5, 9], 3, False) is None


def test_duration() -> None:
    assert [duration(s) for s in (-1, 0, 59, 60, 252, 3599, 3600, 3780)] == [
        "0s",
        "0s",
        "59s",
        "1m00s",
        "4m12s",
        "59m59s",
        "1h00m",
        "1h03m",
    ]


def test_log_line_names_agent_and_short_session() -> None:
    e = event(TOOL_START, session="0123456789abcdef", tool="Edit", target="foo.py")
    line = log_line(e, "Claude", 0)
    assert line.endswith(" Claude [01234567] Edit foo.py\n")
    assert line[2] == ":" and line[5] == ":"  # HH:MM:SS prefix


def test_log_line_per_kind() -> None:
    def text(e: AgentEvent) -> str:
        return log_line(e, "Claude", 0).split("] ", 1)[1].rstrip("\n")

    assert text(event(TOOL_END, tool="Read", target="a.py")) == "Read a.py ✓"
    assert text(event(TOOL_START, tool="Grep", subagent="e1")) == "↳ Grep"
    assert text(event(PROMPT, message="fix the bug\nplease")) == "prompt: fix the bug"
    assert text(event(NEEDS_INPUT, message="Allow Bash?")) == "needs input: Allow Bash?"
    assert text(event(PERMISSION, message="Needs Bash")) == "permission: Needs Bash"
    assert text(event(PLAN)) == "plan ready"
    assert text(event(ERROR, message="rate_limit")) == "error: rate_limit"
    assert text(event(SUBAGENT_START, tool="Explore", message="scan")) == (
        "subagent Explore started: scan"
    )
    assert text(event(SUBAGENT_END, subagent="e1")) == "subagent e1 finished"
    assert text(event(SESSION_START)) == "session started in /home/me/app"
    assert text(event(SESSION_END)) == "session ended"
    assert text(event(DONE)) == "done"


def test_title_flags_sessions_waiting_on_you() -> None:
    store = SessionStore()
    assert view_title(store.all()) == "Agent Overview"
    store.apply(event(TOOL_START, session="a"), "Claude", 0)
    assert view_title(store.all()) == "Agent Overview"
    for kind in (PERMISSION, PLAN, NEEDS_INPUT):
        store.apply(event(kind, session="b"), "Claude", 0)
        assert view_title(store.all()) == "🔴 Agent Overview — needs input"
    store.apply(event(PROMPT, session="b"), "Claude", 0)
    assert view_title(store.all()) == "Agent Overview"
