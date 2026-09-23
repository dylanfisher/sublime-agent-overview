# 0005. Agents view grouped by project; sessions stay until they end

- **Date:** 2026-09-22
- **Status:** accepted

## Context

The view from [0004](0004-agents-view-layout.md) split sessions into Needs you, Working, Done
and Idle sections. A session moved between sections as its state changed, so its project was
spread across the view and rows jumped around. A finished session was dropped 30 seconds after
its turn ended, so an open but idle agent vanished from the view.

## Decision

Sessions are grouped by project only, with no state sections. Projects and the sessions in them
keep the order they were first seen, and a blank line separates projects. `N`/`P` and `1`–`4`
move between projects instead of sections. A session stays listed until its agent reports it
ended (`SessionEnd`) or it is dismissed with `x`.

Every row, subagents included, puts its fixed-width columns first: state, then elapsed time in
one column for the whole view. The free text (tool call, prompt, task) comes last, so a change
in one row never moves the columns of another.

## Alternatives considered

- **Projects ordered by urgency** — rejected: rows would still move whenever a state changes.
  The tab title already flags a session waiting on you.

## Consequences

A session whose agent exits without reporting `SessionEnd`, such as a killed terminal, stays
listed until you dismiss it.
