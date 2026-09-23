# SublimeAgentOverview

Live activity from AI coding agents, shown inside Sublime Text 4:

- **Agents view** — a read-only tab listing every active agent session, whatever project it's
  in (**SublimeAgentOverview: Show Agents** in the Command Palette, or `cmd+k` `cmd+j` —
  `ctrl+k` `ctrl+j` off macOS). It opens in the current window; each window can keep its own,
  and all show the same sessions. Laid out like SublimeGit's `*git-status*`: sessions are grouped
  by project, in the order they were first seen, with running subagents in a tree under their
  parent. A session stays listed, idle or done, until it ends:

  ```
  Agent Overview
  Server:   127.0.0.1:47823
  Sessions: 4 sessions in 3 projects  ·  ■ 1  ▶ 1  ◐ 1  ✓ 1  ·  ◦ 2 subagents


  sublime-agent  ~/projects/sublime-agent  ·  2 sessions
    ▶ working     4m12s       Edit status.py
      ├ ◦         40s         Explore  "find agents view callers"  Grep _state
      └ ◦         9s          Plan     "sketch layout options"     starting
    ◐ thinking    48s         "write hook install tests"  bypass

  mulch  ~/projects/mulch
    ■ permission  42s         Bash rm -rf build && make

  sublimegit  ~/projects/sublimegit
    ✓ done        12s ago     "fix stash ordering"
  ```

  States are colored by text only: red for a permission prompt or error, orange for a plan,
  a question or a tool call (yellow in Monokai), cyan for thinking, green for done, violet for
  subagents, and pink for `bypass` (the session runs without asking permission). Times are how
  long it has waited on you, or how long the turn has run; they sit in one column so rows don't
shift as their text changes. A background task finishing shows its summary (`"Agent 'find
callers' finished"`) in place of a prompt. Keys: `n`/`p` next/previous session,
  `N`/`P` next/previous project, `1`–`4` jump to a project, `enter` open the project folder,
  `x` dismiss a session that ended without saying so, `l` show the log, `r` refresh and go to the first session.
- **Agents output panel** — a timestamped log, one line per event
  (**SublimeAgentOverview: Show Log** in the Command Palette).
- **Open Terminal** — **SublimeAgentOverview: Open Terminal** in the Command Palette focuses the
  terminal tab of this project's latest agent. If no agent tab is known, it opens a new window of
  the `terminal_app` setting (default `"Terminal"`) in the project folder.
- **A flagged tab title** — `🔴 Agents — needs input` while any agent waits on a permission
  prompt, a plan approval, or an answer.

Built for several agents; the first adapter is [Claude Code](https://code.claude.com), fed by its hooks.

## Install

1. Clone this repo and run `./scripts/dev` — it links the checkout into Sublime's `Packages/` as
   `SublimeAgentOverview`. (Or clone straight into `Packages/SublimeAgentOverview`.)
2. Sublime loads it and starts listening on `127.0.0.1:47823`. To change the port, run
   **Preferences: SublimeAgentOverview Settings**; if it's taken, the console says so.

## Hook setup

Run **SublimeAgentOverview: Install Hooks…** and pick **Claude**. It adds one entry to each hook event in
`~/.claude/settings.json` (`SessionStart`, `SessionEnd`, `UserPromptSubmit`, `PreToolUse`,
`PostToolUse`, `Notification`, `Stop`, `StopFailure`, `SubagentStart`, `SubagentStop`), each
running:

```sh
curl -s --max-time 1 -X POST --data-binary @- http://127.0.0.1:47823/event/claude || true
```

Your existing hooks are left alone, running it twice changes nothing, and the previous file is
saved as `settings.json.bak`. **SublimeAgentOverview: Uninstall Hooks…** removes only these entries.
Re-run install after changing the port, and after updating the plugin, which may add hooks. If Sublime isn't running, the hook fails silently and
Claude Code carries on.

## Adding a new agent

Everything outside `agents/` is agent-neutral. An adapter subclasses `core.adapter.Adapter`:

```python
# agents/codex.py
from typing import Any, Dict, Optional

from ..core.adapter import Adapter
from ..core.event import DONE, PROMPT, AgentEvent


class CodexAdapter(Adapter):
    name = "codex"  # events arrive at POST /event/codex
    display_name = "Codex"  # shown in the Agents view and log

    def parse(self, payload: Dict[str, Any]) -> Optional[AgentEvent]:
        # Return None to ignore a payload; raise ValueError if it's malformed (HTTP 400).
        kind = {"turn_started": PROMPT, "turn_finished": DONE}.get(payload.get("type", ""))
        if kind is None:
            return None
        return AgentEvent(
            self.name,
            payload["session"],
            payload["cwd"],
            kind,
            tool=None,
            target=None,
            message=None,
            raw=payload,
        )
```

Then register it in `agents/__init__.py`:

```python
REGISTRY: Dict[str, Adapter] = {a.name: a for a in (ClaudeAdapter(), CodexAdapter())}
```

Event kinds are `session_start`, `session_end`, `prompt`, `tool_start`, `tool_end`,
`needs_input`, `permission`, `plan`, `error`, `done`, `subagent_start` and `subagent_end`
(see `core/event.py`). Set `subagent` on an event that came from a subagent, and `unsupervised`
when the payload says whether the session asks permission. If the agent is configured through a file, set `can_install = True` and
implement `install_hooks(port)` / `uninstall_hooks()` — both return a one-line summary — and it
appears in the install commands.

## Develop

```sh
./scripts/setup   # uv installs Python 3.8 and the dev tools
./scripts/dev     # links this checkout into Sublime's Packages/
./scripts/check   # the gate: format, lint, strict typecheck, tier boundaries, tests
```

Sublime reloads a plugin only when its top-level file changes. Saving
`sublime_agent_overview.py` reloads everything, `core/` and `agents/` included; an edit to one of
those alone takes effect on that next save or a restart. To see what the running plugin loaded:

```sh
curl -s http://127.0.0.1:47823/status
```

It returns the load time, a digest per module, `changed_since_load` (files edited on disk since —
non-empty means the running code is stale), and the Agents view's current lines. Why reloads
work this way: [docs/decisions/0006](docs/decisions/0006-reload-and-status-endpoint.md).

| Path | Purpose |
|---|---|
| `sublime_agent_overview.py` | Plugin entry point — the only module that talks to the `sublime` API. |
| `core/` | Event model, session state, formatting, HTTP server. Pure stdlib, tested outside the editor. |
| `agents/` | One adapter per agent, plus the registry. |
| `typings/` | Stubs for the parts of the Sublime API the plugin uses. |
| `AGENTS.md` | Instructions for AI coding agents working in this repo. |
| `docs/map.md` | Where things live and how to find one before building a second. |
| `docs/decisions/` | Why things are the way they are. |

## License

MIT — see [LICENSE](LICENSE).
