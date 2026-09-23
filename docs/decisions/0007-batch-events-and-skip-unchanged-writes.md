# 0007. Drain events a burst at a time; skip writes an Agents view already shows

- **Date:** 2026-09-22
- **Status:** accepted

## Context

Claude Code fires a hook on every tool call, and parallel subagents fire several at once. Each
event used to schedule its own main-thread callback, and each callback redrew every Agents view
and appended to the log separately. The one-second tick also read each view's whole buffer back
over the plugin host's IPC every time, only to find that nothing had changed while no session
was running.

## Decision

Server threads put events in a `core.server.Inbox`. Only the first event of a burst schedules a
main-thread drain, and the drain applies every queued event before it redraws and logs once.
The plugin remembers the title and text it last wrote to each Agents buffer, and writes only
when one of them has changed. It also stops calling `substr` to compare.

## Alternatives considered

- **Debounce the redraw with a timer (e.g. 50 ms)** — rejected: it adds latency to every
  event, including the first one in a burst, and it still needs one callback per event.
- **Diff the text and replace only the changed lines** — rejected: while any session is
  running, the elapsed column changes on most rows every second. A 40-line replace is cheap,
  and one region edit per line costs more IPC than it saves.
- **Keep the `substr` comparison as a safety net** — rejected: the view is read-only and only
  `_refresh` writes to it, so the cache is enough. The comparison was the most expensive
  call on an idle tick.

## Consequences

Events in one burst share a timestamp in the log. The write cache is keyed by buffer id, so
clones of an Agents view are written once. It resets on plugin reload, when every view is
redrawn. If the user changes an Agents view's syntax by hand, it is no longer switched back
every tick; it is switched back only when the view is first seen after a load.
