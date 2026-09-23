"""The terminal tab an agent runs in, as its hook reports it, and how to bring that tab forward."""

import re
import subprocess
from typing import List, NamedTuple, Optional

PROGRAM_HEADER = "X-Term-Program"
TTY_HEADER = "X-Term-TTY"

# Arguments for a hook's curl. The hook runs without a controlling terminal, but its parent —
# the agent itself — still has the terminal's tty.
CURL_HEADERS = f'-H "{PROGRAM_HEADER}: $TERM_PROGRAM" -H "{TTY_HEADER}: $(ps -o tty= -p $PPID)"'

# osascript waits while macOS asks for permission to control the terminal; past this, give up
# rather than hold Sublime's shared async thread.
FOCUS_TIMEOUT_SECONDS = 10.0

TTY_RE = re.compile(r"tty\w+")  # what `ps -o tty=` prints; "??" when there is none

# $TERM_PROGRAM -> AppleScript that brings the tab on the tty in argv forward. Both apps
# report each tab's tty, so a tab is found the same way in either.
SCRIPTS = {
    "Apple_Terminal": """
on run argv
    set wanted to item 1 of argv
    tell application "Terminal"
        repeat with w in windows
            repeat with t in tabs of w
                if tty of t is wanted then
                    set miniaturized of w to false
                    set selected tab of w to t
                    set index of w to 1
                    activate
                    return
                end if
            end repeat
        end repeat
    end tell
    error "no Terminal tab on " & wanted
end run
""",
    "iTerm.app": """
on run argv
    set wanted to item 1 of argv
    tell application "iTerm2"
        repeat with w in windows
            repeat with t in tabs of w
                repeat with s in sessions of t
                    if tty of s is wanted then
                        tell w to select
                        tell t to select
                        tell s to select
                        activate
                        return
                    end if
                end repeat
            end repeat
        end repeat
    end tell
    error "no iTerm2 session on " & wanted
end run
""",
}


class Terminal(NamedTuple):
    program: str  # $TERM_PROGRAM, e.g. "Apple_Terminal"
    tty: str  # e.g. "/dev/ttys010"


def parse(program: Optional[str], tty: Optional[str]) -> Optional[Terminal]:
    """The terminal from a hook's headers; None when either is missing or has no tty."""
    program = (program or "").strip()
    tty = (tty or "").strip()
    if not program or not TTY_RE.fullmatch(tty):
        return None
    return Terminal(program, "/dev/" + tty)


def focus_command(terminal: Terminal) -> Optional[List[str]]:
    """The command that brings `terminal`'s tab forward; None for a program we can't drive."""
    script = SCRIPTS.get(terminal.program)
    return None if script is None else ["osascript", "-e", script, terminal.tty]


def focus(command: List[str], timeout: float = FOCUS_TIMEOUT_SECONDS) -> Optional[str]:
    """Run a focus_command; why it failed, or None when it worked."""
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return f"{command[0]} took longer than {timeout:g}s"
    except OSError as e:
        return str(e)
    if result.returncode != 0:
        return result.stderr.strip() or f"{command[0]} exited {result.returncode}"
    return None
