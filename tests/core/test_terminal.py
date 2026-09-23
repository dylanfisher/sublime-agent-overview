from SublimeAgentOverview.core.terminal import Terminal, focus, focus_command, parse


def test_parse_takes_what_ps_prints() -> None:
    assert parse("Apple_Terminal", " ttys010 ") == Terminal("Apple_Terminal", "/dev/ttys010")


def test_parse_is_none_without_a_tty_or_program() -> None:
    assert parse("Apple_Terminal", "??") is None
    assert parse("Apple_Terminal", None) is None
    assert parse("", "ttys010") is None
    assert parse("Apple_Terminal", 'ttys010" & quit') is None


def test_focus_passes_the_tty_as_an_argument_not_script_text() -> None:
    command = focus_command(Terminal("iTerm.app", "/dev/ttys004"))
    assert command is not None
    assert command[:2] == ["osascript", "-e"]
    assert command[3:] == ["/dev/ttys004"]
    assert "ttys004" not in command[2]


def test_focus_is_none_for_a_terminal_we_cannot_drive() -> None:
    assert focus_command(Terminal("vscode", "/dev/ttys004")) is None


def test_focus_reports_why_it_failed() -> None:
    assert focus(["true"]) is None
    assert focus(["sh", "-c", "echo no tab >&2; exit 1"]) == "no tab"
    assert focus(["sh", "-c", "exit 3"]) == "sh exited 3"
    assert focus(["sleep", "5"], timeout=0.1) == "sleep took longer than 0.1s"
    error = focus(["/nonexistent/osascript"])
    assert error is not None and "/nonexistent/osascript" in error
