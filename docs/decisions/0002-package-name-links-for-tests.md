# 0002. Tests import the plugin as `SublimeAgentOverview` through links in `.venv/pkgroot`

- **Date:** 2026-09-22
- **Status:** accepted

## Context

Sublime loads the repo as the package `SublimeAgentOverview`, so code imports across tiers relatively
(`from ..core import event`). A relative import above `agents/` only resolves if `agents` and
`core` share a parent package — which, outside the editor, the checkout directory (named anything,
e.g. `sublime-agent`) is not. Tests and basedpyright need the same package name Sublime uses.

## Decision

`./scripts/setup` creates `.venv/pkgroot/SublimeAgentOverview/` holding one symlink per top-level
subpackage. pytest's `pythonpath` and basedpyright's `extraPaths` both point at `.venv/pkgroot`;
tests import `SublimeAgentOverview.core...`.

## Alternatives considered

- **One link `.venv/pkgroot/SublimeAgentOverview` → repo root** — rejected: the link sits inside the
  package it points at, so once the repo is in Sublime's `Packages/`, a recursive resource scan
  can loop.
- **Absolute `SublimeAgentOverview.` imports in the plugin** — same problem moved, not solved: tests would
  still need the name.
- **A conftest alias module** — works for pytest, invisible to the type checker.

## Consequences

A fresh checkout must run `./scripts/setup` before tests or typecheck resolve imports; CI does.
`sublime_agent_overview.py` itself isn't imported by tests (it needs the editor).
