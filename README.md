# SublimeAgent

Live activity from AI coding agents, shown inside Sublime Text 4: status bar, an **Agents** log
panel, and a popup when an agent needs input. Built for several agents; the first adapter is
Claude Code, fed by Claude Code hooks.

## Develop

```sh
./scripts/setup   # uv installs Python 3.8 and the dev tools
./scripts/dev     # links this checkout into Sublime's Packages/ as SublimeAgent
./scripts/check   # the gate: format, lint, strict typecheck, tier boundaries, tests
```

| Path | Purpose |
|---|---|
| `sublime_agent.py` | Plugin entry point — the only module that talks to the `sublime` API. |
| `core/` | Agent-neutral logic, pure stdlib, tested outside the editor. |
| `agents/` | One adapter per agent, plus the registry. |
| `AGENTS.md` | Instructions for AI coding agents working in this repo. |
| `docs/map.md` | Where things live and how to find one before building a second. |
| `docs/decisions/` | Why things are the way they are. |

## License

MIT — see [LICENSE](LICENSE).
