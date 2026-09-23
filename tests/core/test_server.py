import json
import socket
import urllib.error
import urllib.request
from typing import Any, Dict, Iterator, List, Optional, Tuple

import pytest

from SublimeAgentOverview.core.adapter import Adapter
from SublimeAgentOverview.core.event import PROMPT, AgentEvent
from SublimeAgentOverview.core.server import EventServer, Inbox, handle_payload


class FakeAdapter(Adapter):
    name = "fake"
    display_name = "Fake"

    def parse(self, payload: Dict[str, Any]) -> Optional[AgentEvent]:
        if "bad" in payload:
            raise ValueError("bad")
        if "ignore" in payload:
            return None
        return AgentEvent("fake", "s", "/p", PROMPT, None, None, None, payload)


REGISTRY: Dict[str, Adapter] = {"fake": FakeAdapter()}


class Harness:
    def __init__(self) -> None:
        self.delivered: List[AgentEvent] = []
        self.server = EventServer(0, self.on_payload, lambda: {"loaded": "now"})

    def on_payload(self, agent: str, payload: Any) -> int:
        return handle_payload(REGISTRY, agent, payload, self.delivered.append, lambda _: None)

    def get(self, path: str) -> Tuple[int, bytes]:
        url = f"http://127.0.0.1:{self.server.port}{path}"
        try:
            with urllib.request.urlopen(url) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, b""

    def post(self, path: str, body: bytes) -> int:
        url = f"http://127.0.0.1:{self.server.port}{path}"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, body, method="POST")) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code


@pytest.fixture
def h() -> Iterator[Harness]:
    harness = Harness()
    harness.server.start()
    yield harness
    harness.server.stop()


def test_known_agent_is_delivered(h: Harness) -> None:
    assert h.post("/event/fake", json.dumps({"x": 1}).encode()) == 204
    assert [e.raw for e in h.delivered] == [{"x": 1}]


def test_unknown_agent_is_404(h: Harness) -> None:
    assert h.post("/event/nope", b"{}") == 404


def test_other_paths_are_404(h: Harness) -> None:
    assert h.post("/", b"{}") == 404
    assert h.post("/event/fake/extra", b"{}") == 404


def test_status_returns_the_report_as_json(h: Harness) -> None:
    status, body = h.get("/status")
    assert (status, json.loads(body)) == (200, {"loaded": "now"})
    assert h.get("/")[0] == h.get("/status/x")[0] == 404


def test_invalid_json_is_400(h: Harness) -> None:
    assert h.post("/event/fake", b"not json") == 400


def test_non_object_and_malformed_payloads_are_400(h: Harness) -> None:
    assert h.post("/event/fake", b"[1]") == 400
    assert h.post("/event/fake", b'{"bad": 1}') == 400


def test_ignored_payload_is_accepted_but_not_delivered(h: Harness) -> None:
    assert h.post("/event/fake", b'{"ignore": 1}') == 204
    assert h.delivered == []


def test_port_in_use_raises_oserror(h: Harness) -> None:
    with pytest.raises(OSError):
        EventServer(h.server.port, lambda agent, payload: 204, dict).start()


def test_stop_releases_the_port() -> None:
    srv = EventServer(0, lambda agent, payload: 204, dict)
    srv.start()
    port = srv.port
    srv.stop()
    with socket.socket() as s:
        s.bind(("127.0.0.1", port))


def _event(session_id: str) -> AgentEvent:
    return AgentEvent("fake", session_id, "/p", PROMPT, None, None, None, {})


def test_inbox_asks_for_one_drain_per_burst() -> None:
    inbox = Inbox()
    assert [inbox.put(_event(s)) for s in "abc"] == [True, False, False]
    assert [e.session_id for e in inbox.drain()] == ["a", "b", "c"]
    assert inbox.drain() == []
    assert inbox.put(_event("d")) is True  # the next burst schedules its own drain
