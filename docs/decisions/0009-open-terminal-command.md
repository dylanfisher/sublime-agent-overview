# 0009. Open Terminal command: focus an agent's tab, else open a new window

- **Date:** 2026-09-23
- **Status:** accepted

## Context

The Command Palette should get you to a terminal for the current window's project. Sublime can't
see a terminal's working directory, so the only tabs we can find are the ones agents report
(0008).

## Decision

**SublimeAgentOverview: Open Terminal** picks the window's folder that holds the active file, or
its first folder if none does. If a session under that folder has a terminal we can drive, the
one whose state changed last gets focused. Otherwise it runs `open -a <terminal_app> <folder>`,
where `terminal_app` is a setting that defaults to `"Terminal"`.

## Alternatives considered

- **Look for any tab already in the folder** — rejected: Terminal.app's AppleScript doesn't
  expose a tab's cwd. iTerm2's does, but only through shell integration.
- **Open whichever app the agents' tabs run in** — rejected: when no agent has run yet there's
  nothing to go on, so a setting is needed anyway.

## Consequences

Opening a new window is macOS-only, the same as focusing. A tab you opened yourself is never
reused, so running the command twice with no agent opens two windows.
