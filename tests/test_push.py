from pathlib import Path

from gnwmanager.cli._push import _expand_glob


def test_expand_glob_star(tmp_path):
    (tmp_path / "a.txt").touch()
    (tmp_path / "b.txt").touch()
    (tmp_path / "c.bin").touch()

    result = _expand_glob([tmp_path / "*.txt"])
    assert result == sorted([tmp_path / "a.txt", tmp_path / "b.txt"])


def test_expand_glob_question_mark(tmp_path):
    (tmp_path / "a1.txt").touch()
    (tmp_path / "a2.txt").touch()
    (tmp_path / "bb.txt").touch()

    result = _expand_glob([tmp_path / "a?.txt"])
    assert result == sorted([tmp_path / "a1.txt", tmp_path / "a2.txt"])


def test_expand_glob_no_match_preserves_original(tmp_path):
    path = tmp_path / "*.xyz"
    result = _expand_glob([path])
    assert result == [path]


def test_expand_glob_no_metacharacters(tmp_path):
    path = tmp_path / "plain.txt"
    path.touch()
    result = _expand_glob([path])
    assert result == [path]


def test_expand_glob_no_metacharacters_nonexistent(tmp_path):
    path = tmp_path / "missing.txt"
    result = _expand_glob([path])
    assert result == [path]


def test_expand_glob_mixed(tmp_path):
    (tmp_path / "a.txt").touch()
    (tmp_path / "b.txt").touch()
    explicit = tmp_path / "explicit.bin"
    explicit.touch()

    result = _expand_glob([explicit, tmp_path / "*.txt"])
    assert result == [explicit] + sorted([tmp_path / "a.txt", tmp_path / "b.txt"])


def test_expand_glob_directories_included(tmp_path):
    (tmp_path / "subdir").mkdir()
    (tmp_path / "file.txt").touch()

    result = _expand_glob([tmp_path / "*"])
    assert sorted(result) == sorted([tmp_path / "subdir", tmp_path / "file.txt"])
