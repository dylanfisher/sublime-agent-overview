# 0004. Agents view in urgency sections, colored by foreground scopes

- **Date:** 2026-09-22
- **Status:** accepted; the urgency sections are superseded by [0005](0005-agents-view-grouped-by-project.md)

## Context

The first Agents view was one row per session: glyph, agent, project, state. Every row looked
alike, a permission prompt read the same as a finished turn, two sessions in one project were
indistinguishable, and subagents didn't show. `SubagentStop` was mapped to `done`, so a subagent
finishing marked its still-working parent done. Mockups were compared in the editor; the chosen
layout follows SublimeGit's `*git-status*` (header lines, titled sections, a help block) with
sessions grouped by project inside each section.

## Decision

Sessions sit in four sections — Needs you, Working, Done, Idle — grouped by project folder, with
subagents in a tree under their parent. "Needs input" splits into permission, plan and question,
plus error for a turn that stopped on a failure. Colors come from `Agents.sublime-syntax` using
foreground-only scopes: `markup.deleted` / `markup.changed` / `markup.inserted` for red, orange
and green, and `support.function`, `constant.numeric` and `keyword` for cyan, purple and pink. The
plugin ships no color scheme. The help block uses comment and string scopes, like git-status's.

For Claude, subagents come from two signals: the `Task`/`Agent` tool call announces one (with its
type and task), and `SubagentStart` claims the oldest announcement of the same type with its
`agent_id`, which later tool calls and `SubagentStop` carry. The `PermissionRequest` hook is not
installed. A hook there sits between Claude Code and its own prompt, and this plugin only watches.
`Notification` reports the same prompt, and the view takes the tool from the `PreToolUse` before
it. `idle_prompt` notifications are dropped: they fire a minute after every finished turn.

## Alternatives considered

- **Grouped by project only, ordered by urgency** — rejected: no sections for `N`/`P` to jump
  between, and the urgent rows aren't set apart as clearly.
- **A packaged color scheme for the view** — rejected: replaces the user's scheme in that tab.
- **`region.redish` … `region.pinkish` scopes** — tried first: Sublime derives them for every
  scheme, but Monokai and others paint them as a background, which read as highlighted blocks.
  Standard scopes give fewer distinct colors (plan, question and tool call share one) and vary
  by scheme; the glyph and label still tell states apart.
- **Only `SubagentStart`/`SubagentStop`** — rejected: they carry no task description.
- **Only the `Task` tool call** — rejected: a background subagent's call returns while it runs, and
  the tool call has no id that the subagent's own tool calls carry.

## Consequences

Two same-type subagents started together may show each other's task, since a start is matched to
an announcement by type and order. The view redraws every second so elapsed times stay current.
The caret stays on its session when rows move. Context fill and the usage window aren't shown:
no hook payload carries them, so they need transcript and `~/.claude.json` reads.
