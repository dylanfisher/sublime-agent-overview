# 0003. One global Agents view instead of per-window status bars

- **Date:** 2026-09-22
- **Status:** accepted

## Context

The first design routed each event to the Sublime window whose project folder contained the
agent's `cwd`, and showed that window's sessions in its status bar. An agent running in a folder
no window had open fell back to whichever window was active, and you saw nothing about agents
working in other projects. The point of the plugin is to see all agents at once.

## Decision

Sessions are global. One read-only scratch view, **Agents**, lists every session, one row each
(agent, project folder name, state). The same idea as SublimeGit's `*git-status*` view. It is
marked by the `sublime_agent_overview_view` view setting. Show Agents opens it in the current
window, so each window (e.g. one per project) can hold its own; every marked view is redrawn from
the same render. The log goes to the active window. A session waiting on you flags the tab title
(`🔴 Agents — needs input`) instead of a popup, which interrupted whatever view was active.

## Alternatives considered

- **Keep routing, show all sessions in every status bar** — rejected: one status line can't fit
  several sessions with their tool targets, and it repeats in every view.
- **Output panel** — rejected: panels are per window and close when you switch panels. A view can
  sit in its own window or split.
- **Quick panel / popup on demand** — rejected: you have to open it to see anything.
- **Exactly one view, focused in whichever window holds it** — rejected: Show Agents jumped to
  another project's window. Redrawing several views costs one text replace per view per second,
  on a buffer of a few dozen lines; the render itself is computed once.

## Consequences

`core/routing.py` is gone; `Session` records its `cwd` for display. The view only updates while
it is open; closing it loses nothing, since reopening redraws it from the session store.
