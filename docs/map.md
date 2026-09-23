# Code map

Where things live, and how to find one before you build a second. Read this before creating any
new file.

This file describes **shape, not contents** — conventions and search commands, never an inventory.
An inventory would be a second copy of facts the code already holds, it would rot within a week,
and it would have no error message when it diverged. If you catch yourself listing what exists
here, stop: the grep is the list.

## Find before you create

The single rule that matters. AGENTS.md principles 1–3 (single source of truth, match the
surrounding code, DRY on the third occurrence) all depend on it — none of them can be followed
against a codebase you haven't searched.

| Before adding… | Run |
|---|---|
| any named thing | `rg -i '<name>' --type py` |
| a core module | `ls core/` |
| an agent adapter | `ls agents/` |
| a helper / function | `rg '^def ' core/` |
| a setting | `rg '<key>' SublimeAgentOverview.sublime-settings` — read in `sublime_agent_overview.py` only |
| a type / class | `rg '^class <Name>'` |

If a search turns up something close but not identical, that's the second occurrence. Use it or
duplicate it — do not abstract yet (principle 3).

## Tiers

The repo root is the Sublime package. Tests live in `tests/` and may import any tier.

| Tier | Path | What belongs here | May import from |
|---|---|---|---|
| **core** | `core` | Agent-neutral logic: event model, session state, view/log formatting, the HTTP server. Pure Python stdlib — never imports `sublime`. Unit-testable outside the editor. | nothing in this table |
| **agents** | `agents` | One adapter module per agent, plus the registry in `agents/__init__.py`. Maps raw payloads to `core`'s event model; may edit that agent's own config for hook install. | core |
| **plugin** | `sublime_agent_overview.py` | The Sublime entry point: lifecycle, commands, settings, all `sublime` API calls. The only module that imports `sublime` / `sublime_plugin`. | core, agents |

**Dependency direction is one-way: plugin → agents → core.** Never upward. Nothing outside
`agents/` names a specific agent — adding one means adding a module and registering it.

Enforced by `scripts/arch` (run by `./scripts/check`): it holds the table above as a map and fails
on any import edge it forbids, including `sublime` outside the plugin tier.

## Naming

- One thing per file; the filename is the thing's name.
- Directory names plural, file names singular: `agents/claude.py`, not `.../claudes.py`.
- Tests mirror the tree under `tests/`: `core/status.py` → `tests/core/test_status.py`.
- Imports inside the package are relative (`from ..core import event`) — Sublime loads it as
  `SublimeAgentOverview`, so absolute `core.` imports break in the editor.
- Runtime code is stdlib only and runs on Python 3.8: no `match`, no `X | Y` types at runtime.
- Stubs for the `sublime` API live in `typings/` and cover only what the plugin calls.

## Promotion

Things move up a tier deliberately, never by accident:

- **Third occurrence** → extract to the lowest tier that all three callers can reach (principle 3).
- **Component loses its project knowledge** → it's a primitive now; move it down.
- **Primitive grows a config read or a domain type** → it was never a primitive; move it up.

A promotion is its own commit, separate from whatever work revealed it (principle 4).

<!-- paths: core agents sublime_agent_overview.py -->
<!-- ↑ scripts/check verifies every path above exists. Keep it in sync with the Tiers table;
     a rename that misses this line fails the gate, which is the point. -->
