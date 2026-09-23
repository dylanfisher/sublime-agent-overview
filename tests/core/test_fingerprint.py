from pathlib import Path

from SublimeAgentOverview.core.fingerprint import changed, digests


def test_changed_lists_only_files_edited_since_loading(tmp_path: Path) -> None:
    a, b = tmp_path / "a.py", tmp_path / "b.py"
    a.write_text("x = 1\n")
    b.write_text("y = 1\n")
    loaded = digests([str(a), str(b)])
    assert changed(loaded) == []
    b.write_text("y = 2\n")
    assert changed(loaded) == [str(b)]


def test_same_content_has_the_same_digest(tmp_path: Path) -> None:
    a, b = tmp_path / "a.py", tmp_path / "b.py"
    a.write_text("x = 1\n")
    b.write_text("x = 1\n")
    assert len(set(digests([str(a), str(b)]).values())) == 1
