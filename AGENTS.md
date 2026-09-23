# AGENTS.md

Instructions for AI coding agents working in this repo. Humans: see [README.md](README.md).

**Keep this file under ~50 lines.** Anything longer lives in `docs/` and is linked from here.

## Stack

- **Language:** Python 3.8 (Sublime Text 4 plugin host), pinned in `.python-version`
- **Package manager:** uv (dev tools only — ruff, basedpyright strict, pytest)
- **Framework:** Sublime Text 4 plugin API
- **Test framework:** pytest
- **Layout:** repo root is the package; `core/` ← `agents/` ← `sublime_agent_overview.py`, tests in `tests/` — tiers and search recipes: [docs/map.md](docs/map.md)

## Commands

| Task | Command |
|---|---|
| Install / bootstrap | `./scripts/setup` |
| Run locally | `./scripts/dev` |
| Run tests | `./scripts/test` |
| **Full gate** | `./scripts/check` |

`./scripts/check` runs format + lint + typecheck + tests. It is the gate — see Definition of done.

## Principles

Non-negotiable, regardless of stack. Rationale: [docs/principles.md](docs/principles.md).

1. **Single source of truth.** Every fact — a constant, type, config value, copy string — is defined once and imported. Never re-declare, never re-derive. **Search before you create** — [docs/map.md](docs/map.md) has the recipes.
2. **Match the surrounding code.** Consistency beats personal preference. Read a neighboring file before writing a new one; map.md says which one is the neighbor.
3. **DRY on the third occurrence, not the second.** Premature abstraction costs more than duplication.
4. **Smallest change that solves the problem.** No drive-by refactors, renames, or reformatting outside the task.
5. **Fail loudly.** No empty catches, no silent fallbacks, no defaults that mask a missing value.
6. **Delete, don't comment out.** Git remembers.
7. **No new dependencies without asking first.** Say what it's for and what it replaces.
8. **Style is the formatter's job.** If a tool enforces it, it does not belong in this file or in review.

## Boundaries

- Runtime code is stdlib-only and must run on Python 3.8. Dev tools go in the `dev` group, nothing else.
- Never edit `uv.lock` by hand — `uv add --dev <pkg>` (after asking) or `uv lock`.
- Tests never read or write the real `~/.claude/settings.json` — pass a temp path.
- Never write or print a plaintext secret. There are none today; see `.env.example`.

## Definition of done

- `./scripts/check` passes clean.
- New behavior has a test that fails without the change.
- No new dependencies, no new files outside the agreed layout, no TODOs left behind.
- If a decision was non-obvious, record it in `docs/decisions/`.
