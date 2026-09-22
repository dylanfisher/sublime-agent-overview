# 0001. Python 3.8 stdlib-only Sublime plugin, uv-managed dev tooling

- **Date:** 2026-09-22
- **Status:** accepted

## Context

SublimeAgent shows live AI-agent activity inside Sublime Text 4. It runs in Sublime's plugin
host, which ships its own Python and has no package installer: anything the plugin imports must be
in the package itself. The first agent is Claude Code, fed by hook commands that `curl` a
localhost endpoint; more agents are expected.

## Decision

Target the ST4 **Python 3.8** plugin host with **stdlib only** at runtime (`http.server` for the
event endpoint). Dev tooling — ruff (format + lint), basedpyright (strict), pytest — is managed by
**uv** and pinned to 3.8 via the same `.python-version` file Sublime uses to select its host.
The repo root is the package; logic that doesn't touch the `sublime` API lives in `core/` and
`agents/` so it is testable outside the editor, with `scripts/arch` enforcing that split.

## Alternatives considered

- **Python 3.13 plugin host** — rejected: only in recent ST4 builds; 3.8 runs everywhere ST4 does.
- **Vendored third-party libs (e.g. an HTTP framework)** — rejected: the endpoint is one POST
  route; vendoring adds upgrade burden for nothing.
- **mypy** — rejected: recent releases no longer type-check against a 3.8 target; basedpyright does.
- **pip + requirements-dev.txt** — rejected: uv gives a lockfile and installs the pinned Python
  in one command.
- **Plugin in a `SublimeAgent/` subdirectory** — rejected: a root-level package symlinks
  straight into `Packages/` for development.

## Consequences

No `match`, no runtime `X | Y` unions, no newer stdlib APIs. Sublime API calls are untyped
unless stubbed in `typings/`. If ST drops the 3.8 host, move `.python-version` and ruff's
`target-version` together.
