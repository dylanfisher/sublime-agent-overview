# 0008. Focus an agent's terminal tab by its tty

- **Date:** 2026-09-22
- **Status:** accepted

## Context

`enter` in the Agents view should bring up the terminal tab the agent runs in. Claude Code's hook
payload says nothing about the terminal. The hook process itself has no controlling terminal
(`ps -o tty= -p $$` prints `??`), but its parent, the agent, does.

## Decision

The hook's curl sends `X-Term-Program: $TERM_PROGRAM` and `X-Term-TTY: $(ps -o tty= -p $PPID)`
as headers. The server attaches them to the event as a `Terminal`, the session keeps the latest
one, and `enter` runs an AppleScript that finds the tab with that tty. Terminal.app and iTerm2
are supported. `cmd+enter` opens the project in Sublime, which is what `enter` did before.

## Alternatives considered

- **Merge the fields into the JSON body** — rejected: that needs `jq` or similar in the hook,
  and headers work the same way for every agent.
- **Match on `TERM_SESSION_ID` / `ITERM_SESSION_ID`** — rejected: Terminal.app can't look up a
  tab by its session id, and both apps can look one up by tty.
- **WezTerm, kitty, tmux** — left out for now. WezTerm and kitty need their CLI on Sublime's
  PATH (and kitty needs remote control turned on). tmux can select the pane, but its tty belongs
  to tmux, so finding the terminal window around it is a second lookup.

## Consequences

Existing installs have to reinstall hooks before tabs can be focused. The command changes, so
`install_hooks` replaces the old entry. The tty is passed to `osascript` as an argument, never
put into the script text. It is also checked against `tty\w+`, which is macOS's tty naming.
Focusing is macOS-only: elsewhere the tty (e.g. `pts/3`) fails that check, so the session never
learns its terminal and `enter` says it isn't known yet. With an unsupported `$TERM_PROGRAM`,
`enter` names the supported ones. `osascript` gets 10 seconds (long enough to answer macOS's
first-run automation prompt) before it is abandoned, so it can't hold Sublime's shared async
thread. Every failure, the timeout included, goes to the console.
