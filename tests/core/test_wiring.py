import sys


def test_runs_on_the_plugin_host_python() -> None:
    assert sys.version_info[:2] == (3, 8)
