# 0006. Reload the whole package on plugin reload; expose GET /status

- **Date:** 2026-09-22
- **Status:** accepted

## Context

Sublime reloads a plugin when its top-level file changes, and re-imports only that file. The
modules under `core/` and `agents/` stayed cached in `sys.modules`, so a fix there never ran
until Sublime restarted — while the syntax file, which Sublime reloads on its own, did change.
A fixed bug looked unfixed, and nothing showed which code was running.

## Decision

`plugin_unloaded` drops the package's submodules from `sys.modules` (keeping the package itself,
which the reload needs as the parent), so the reload imports them afresh. The server answers
`GET /status` with the plugin's load time, a content digest of every module it loaded, the files
changed on disk since, and the Agents view's text.

## Alternatives considered

- **`importlib.reload` each submodule in dependency order** — rejected: the order has to be kept
  by hand, and a stale `from x import y` binding survives it.
- **Watch `core/` and `agents/` and reload on their save** — rejected: Sublime has no hook for
  that; an `on_post_save` listener would reload on every save of any file in the repo.
- **Digest files at `/status` time only** — rejected: without the load-time digests there is
  nothing to compare against, so stale code would read as current.

## Consequences

An edit under `core/` or `agents/` still loads only on the next save of
`sublime_agent_overview.py` or a restart; `/status` lists those files until then. The change
itself needed one restart to take effect, since the old `plugin_unloaded` didn't drop modules.
`/status` is on localhost only, like the event route, and reveals nothing beyond source paths
and what the Agents view shows.
