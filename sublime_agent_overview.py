"""SublimeAgentOverview plugin entry point — the only module that talks to the Sublime API."""

import os
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import sublime
import sublime_plugin

from .agents import REGISTRY, installable
from .core.adapter import Adapter
from .core.event import AgentEvent
from .core.fingerprint import changed, digests
from .core.server import HOST, EventServer, handle_payload
from .core.state import Key, Session, SessionStore
from .core.status import VIEW_NAME, AgentsView, agents_view, log_line, step, view_title

SETTINGS = "SublimeAgentOverview.sublime-settings"
PANEL = "Agents"
VIEW_SETTING = "sublime_agent_overview_view"  # marks a window's Agents view
SYNTAX = f"Packages/{__package__}/Agents.sublime-syntax"
TICK_MS = 1000  # elapsed times in the Agents view count in seconds
VIEW_SETTINGS = {
    "line_numbers": True,
    "gutter": True,
    "draw_indent_guides": False,
    "word_wrap": False,
    "spell_check": False,
}

_store = SessionStore()
_server: Optional[EventServer] = None
_server_status = "not started"  # the Agents view's Server: line
_rendered: Optional[AgentsView] = None  # what the Agents view shows now
_tick_generation = 0  # bumped on unload so the old timer stops
_loaded_at = ""
_loaded_code: Dict[str, str] = {}  # source path -> digest, for every module of this package


def _console(message: str) -> None:
    print("SublimeAgentOverview: " + message)


def _port() -> int:
    port = sublime.load_settings(SETTINGS).get("port")
    if not isinstance(port, int):
        raise ValueError(f'"port" in {SETTINGS} must be an integer, got {port!r}')
    return port


def _agents_views(windows: List[sublime.Window]) -> List[sublime.View]:
    return [v for w in windows for v in w.views() if v.settings().get(VIEW_SETTING)]


def _caret_line(view: sublime.View) -> int:
    selection = view.sel()
    return view.rowcol(selection[0].begin())[0] if len(selection) else 0


def _row_of(rendered: AgentsView, key: Key) -> Optional[int]:
    return next((line for line in rendered.rows if rendered.owners[line] == key), None)


def _refresh() -> None:
    global _rendered
    views = _agents_views(sublime.windows())
    if not views:
        return
    sessions = _store.all()
    rendered = agents_view(sessions, time.time(), _server_status)
    title = view_title(sessions)
    for view in views:
        line = _caret_line(view)
        # Keep the caret on the session it was on, wherever that session's row moved to.
        on_row = _rendered is not None and line in _rendered.rows
        key = _rendered.owners.get(line) if _rendered is not None and on_row else None
        moved = _row_of(rendered, key) if key is not None else None
        if view.settings().get("syntax") != SYNTAX:
            view.assign_syntax(SYNTAX)
        if view.name() != title:
            view.set_name(title)
        view.run_command(
            "sublime_agent_overview_write",
            {"content": rendered.text, "line": moved if moved is not None else line},
        )
    _rendered = rendered


def _tick(generation: int) -> None:
    if generation != _tick_generation:
        return
    _refresh()
    sublime.set_timeout(lambda: _tick(generation), TICK_MS)


def _log(window: sublime.Window, line: str) -> None:
    panel = window.find_output_panel(PANEL) or window.create_output_panel(PANEL)
    panel.run_command("append", {"characters": line, "force": True, "scroll_to_end": True})


def _on_event(event: AgentEvent) -> None:
    """Main thread: record the event and update the Agents views and log."""
    display_name = REGISTRY[event.agent].display_name
    now = time.time()
    _store.apply(event, display_name, now)
    _refresh()
    _log(sublime.active_window(), log_line(event, display_name, now))


def _on_payload(agent: str, payload: Any) -> int:
    """Server thread: parse here, hand the event to the main thread."""

    def deliver(event: AgentEvent) -> None:
        sublime.set_timeout(lambda: _on_event(event), 0)

    return handle_payload(REGISTRY, agent, payload, deliver, _console)


def _package_modules() -> List[str]:
    """Names of this package's modules that are loaded, this one included."""
    return [name for name in sys.modules if name.split(".")[0] == __package__]


def _source(path: str) -> str:
    return os.path.relpath(path, os.path.dirname(__file__))


def _status() -> Dict[str, Any]:
    """Server thread: GET /status. Reads only values the main thread replaces whole."""
    return {
        "server": _server_status,
        "loaded_at": _loaded_at,
        "modules": {_source(path): code for path, code in sorted(_loaded_code.items())},
        "changed_since_load": [_source(path) for path in changed(_loaded_code)],
        "view": _rendered.text.splitlines() if _rendered is not None else None,
    }


def plugin_loaded() -> None:
    global _server, _server_status, _loaded_at, _loaded_code
    _loaded_at = time.strftime("%Y-%m-%d %H:%M:%S")
    files = [getattr(sys.modules[name], "__file__", None) for name in _package_modules()]
    _loaded_code = digests(path for path in files if isinstance(path, str))
    port = _port()
    server = EventServer(port, _on_payload, _status)
    try:
        server.start()
    except OSError as e:
        _console(f"could not listen on {HOST}:{port} ({e}); set another port in {SETTINGS}")
        sublime.status_message(f"SublimeAgentOverview: port {port} unavailable — see console")
        _server_status = f"port {port} unavailable — see console"
    else:
        _server = server
        _server_status = f"{HOST}:{port}"
        _console(f"listening on {HOST}:{port}")
    _tick(_tick_generation)  # also redraws an Agents view restored from the last session


def plugin_unloaded() -> None:
    global _server, _tick_generation
    _tick_generation += 1
    if _server is not None:
        _server.stop()
        _server = None
    # Sublime re-imports only this file on reload; drop the rest of the package so the reload
    # imports core/ and agents/ afresh instead of running the copies cached before the edit.
    # The package itself stays: reloading this module needs its parent in sys.modules.
    for name in _package_modules():
        if name not in (__package__, __name__):
            del sys.modules[name]


class SublimeAgentOverviewShowCommand(sublime_plugin.WindowCommand):
    """Focus this window's Agents view, opening one if it has none."""

    def run(self) -> None:
        views = _agents_views([self.window])
        view = views[0] if views else None
        if view is None:
            view = self.window.new_file()
            view.set_name(VIEW_NAME)
            view.set_scratch(True)
            view.set_read_only(True)
            settings = view.settings()
            settings.set(VIEW_SETTING, True)
            for key, value in VIEW_SETTINGS.items():
                settings.set(key, value)
            _refresh()
        self.window.focus_view(view)


class SublimeAgentOverviewWriteCommand(sublime_plugin.TextCommand):
    """Replace the Agents view's text and put the caret on `line`. Internal; run by `_refresh`."""

    def is_visible(self) -> bool:
        return False

    def run(self, edit: sublime.Edit, content: str, line: int) -> None:
        view = self.view
        whole = sublime.Region(0, view.size())
        if view.substr(whole) == content:
            return
        viewport = view.viewport_position()
        view.set_read_only(False)
        view.replace(edit, whole, content)
        view.set_read_only(True)
        _place_caret(view, line)
        view.set_viewport_position(viewport, False)


def _place_caret(view: sublime.View, line: int) -> None:
    point = view.text_point(line, 0)
    view.sel().clear()
    view.sel().add(sublime.Region(point))


def _go_to(view: sublime.View, line: int) -> None:
    _place_caret(view, line)
    view.show(view.text_point(line, 0))


def _session_at_caret(view: sublime.View) -> Optional[Session]:
    key = _rendered.owners.get(_caret_line(view)) if _rendered is not None else None
    return _store.get(key) if key is not None else None


class SublimeAgentOverviewMoveCommand(sublime_plugin.TextCommand):
    """Agents view: caret to the next/previous session, or the first session of a project."""

    def is_visible(self) -> bool:
        return False

    def run(self, edit: sublime.Edit, by: str, forward: bool) -> None:
        if _rendered is None:
            return
        rows = _rendered.rows
        if by == "session":
            lines = rows
        else:
            firsts = (step(rows, header, True) for header in _rendered.projects)
            lines = [line for line in firsts if line is not None]
        target = step(lines, _caret_line(self.view), forward)
        if target is not None:
            _go_to(self.view, target)


class SublimeAgentOverviewJumpCommand(sublime_plugin.TextCommand):
    """Agents view: caret to the first session of project `project` (1-based)."""

    def is_visible(self) -> bool:
        return False

    def run(self, edit: sublime.Edit, project: int) -> None:
        if _rendered is None:
            return
        headers = _rendered.projects
        header = headers[project - 1] if project <= len(headers) else None
        target = step(_rendered.rows, header, True) if header is not None else None
        if target is not None:
            _go_to(self.view, target)


def _window_for(path: str) -> Optional[sublime.Window]:
    """The window whose open folder most closely contains `path`."""
    matches: List[Tuple[int, sublime.Window]] = [
        (len(folder), window)
        for window in sublime.windows()
        for folder in window.folders()
        if path == folder or path.startswith(folder.rstrip(os.sep) + os.sep)
    ]
    return max(matches, key=lambda m: m[0])[1] if matches else None


class SublimeAgentOverviewOpenCommand(sublime_plugin.TextCommand):
    """Agents view: bring up the session's project folder, in a new window if none has it."""

    def is_visible(self) -> bool:
        return False

    def run(self, edit: sublime.Edit) -> None:
        session = _session_at_caret(self.view)
        if session is None:
            return
        cwd = os.path.normpath(session.cwd)
        window = _window_for(cwd)
        if window is None:
            sublime.run_command("new_window")
            window = sublime.active_window()
            window.set_project_data({"folders": [{"path": cwd}]})
        window.bring_to_front()


class SublimeAgentOverviewDismissCommand(sublime_plugin.TextCommand):
    """Agents view: drop a session that ended without telling us."""

    def is_visible(self) -> bool:
        return False

    def run(self, edit: sublime.Edit) -> None:
        session = _session_at_caret(self.view)
        if session is not None:
            _store.remove(session.key)
            _refresh()


class SublimeAgentOverviewRefreshCommand(sublime_plugin.TextCommand):
    """Agents view: redraw, then caret to the first session, like SublimeGit's refresh."""

    def is_visible(self) -> bool:
        return False

    def run(self, edit: sublime.Edit) -> None:
        _refresh()
        if _rendered is not None and _rendered.rows:
            _go_to(self.view, _rendered.rows[0])


class SublimeAgentOverviewShowLogCommand(sublime_plugin.WindowCommand):
    def run(self) -> None:
        if self.window.find_output_panel(PANEL) is None:
            self.window.create_output_panel(PANEL)
        self.window.run_command("show_panel", {"panel": "output." + PANEL})


def _pick_adapter(window: sublime.Window, action: str, apply: Callable[[Adapter], str]) -> None:
    adapters = installable()

    def on_select(index: int) -> None:
        if index < 0:
            return
        adapter = adapters[index]
        try:
            summary = apply(adapter)
        except (OSError, ValueError) as e:
            _console(f"{action} {adapter.display_name} hooks failed: {e}")
            window.status_message(f"SublimeAgentOverview: {action} failed — see console")
            return
        _console(summary)
        window.status_message(summary)

    window.show_quick_panel([f"{action} {a.display_name} hooks" for a in adapters], on_select)


class SublimeAgentOverviewInstallHooksCommand(sublime_plugin.WindowCommand):
    def run(self) -> None:
        port = _port()
        _pick_adapter(self.window, "Install", lambda a: a.install_hooks(port))


class SublimeAgentOverviewUninstallHooksCommand(sublime_plugin.WindowCommand):
    def run(self) -> None:
        _pick_adapter(self.window, "Uninstall", lambda a: a.uninstall_hooks())
