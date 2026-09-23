"""Localhost HTTP endpoint: POST /event/<agent> with the agent's JSON payload.

GET /status returns the plugin's own report as JSON, for checking what is running.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Mapping, Optional, cast

from .adapter import Adapter
from .event import AgentEvent
from .terminal import PROGRAM_HEADER, TTY_HEADER, Terminal, parse

HOST = "127.0.0.1"
# How often serve_forever checks for shutdown; stop() (run on plugin reload) waits up to this.
POLL_SECONDS = 0.2
PREFIX = "/event/"
STATUS_PATH = "/status"

# (agent name, parsed JSON body, terminal from the headers) -> HTTP status code
PayloadHandler = Callable[[str, Any, Optional[Terminal]], int]
StatusReport = Callable[[], Dict[str, Any]]


def handle_payload(
    registry: Mapping[str, Adapter],
    agent: str,
    payload: Any,
    terminal: Optional[Terminal],
    deliver: Callable[[AgentEvent], None],
    log: Callable[[str], None],
) -> int:
    """Parse one payload with its agent's adapter and hand the event to `deliver`."""
    adapter = registry.get(agent)
    if adapter is None:
        log(f"unknown agent {agent!r}")
        return 404
    if not isinstance(payload, dict):
        log(f"{agent}: payload is not a JSON object")
        return 400
    try:
        event = adapter.parse(cast(Dict[str, Any], payload))
    except ValueError as e:
        log(f"{agent}: bad payload: {e}")
        return 400
    if event is not None:
        deliver(event._replace(terminal=terminal))
    return 204


class Inbox:
    """Events handed from server threads to the main thread, drained a burst at a time.

    Hooks fire on every tool call, often several at once; draining together means one redraw
    per burst instead of one per event.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: List[AgentEvent] = []

    def put(self, event: AgentEvent) -> bool:
        """Queue `event`. True when the inbox was empty, so the caller must schedule a drain."""
        with self._lock:
            self._events.append(event)
            return len(self._events) == 1

    def drain(self) -> List[AgentEvent]:
        """Every queued event, oldest first, leaving the inbox empty."""
        with self._lock:
            events, self._events = self._events, []
        return events


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != STATUS_PATH:
            self.send_error(404)
            return
        body = json.dumps(cast(_Server, self.server).status(), indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if not self.path.startswith(PREFIX) or "/" in self.path[len(PREFIX) :]:
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload: Any = json.loads(self.rfile.read(length).decode("utf-8"))
        except ValueError:
            self.send_error(400, "body is not JSON")
            return
        terminal = parse(self.headers.get(PROGRAM_HEADER), self.headers.get(TTY_HEADER))
        status = cast(_Server, self.server).on_payload(self.path[len(PREFIX) :], payload, terminal)
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        pass  # hooks fire on every tool call; per-request access logs would flood the console


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port: int, on_payload: PayloadHandler, status: StatusReport) -> None:
        self.on_payload = on_payload
        self.status = status
        super().__init__((HOST, port), _Handler)


class EventServer:
    """Serves on a background thread. `start` raises OSError if the port can't be bound."""

    def __init__(self, port: int, on_payload: PayloadHandler, status: StatusReport) -> None:
        self._port = port
        self._on_payload = on_payload
        self._status = status
        self._server: Optional[_Server] = None

    @property
    def port(self) -> int:
        """The bound port — differs from the requested one when that was 0."""
        if self._server is None:
            raise RuntimeError("server is not running")
        return self._server.server_address[1]

    def start(self) -> None:
        self._server = _Server(self._port, self._on_payload, self._status)
        threading.Thread(
            target=self._server.serve_forever, args=(POLL_SECONDS,), daemon=True
        ).start()

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
