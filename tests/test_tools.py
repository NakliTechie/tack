"""A5 — the four tools and their ACI-disciplined feedback."""

from tack.adapters.native import NativeExecFS
from tack.core.tools import Tools


def _tools(tmp_path):
    return Tools(NativeExecFS(str(tmp_path)))


def test_read_numbers_lines(tmp_path):
    fs = NativeExecFS(str(tmp_path))
    fs.write("f.py", "first\nsecond\n")
    r = Tools(fs).read("f.py")
    assert r.ok
    assert "1| first" in r.feedback
    assert "2| second" in r.feedback


def test_read_missing_is_a_correction(tmp_path):
    r = _tools(tmp_path).read("nope.py")
    assert not r.ok
    assert "not found" in r.feedback


def test_write_then_edit_roundtrip(tmp_path):
    fs = NativeExecFS(str(tmp_path))
    t = Tools(fs)
    assert t.write("f.txt", "hello world").ok
    assert t.edit("f.txt", "world", "tack").ok
    assert fs.read("f.txt") == "hello tack"


def test_edit_missing_relays_correction(tmp_path):
    fs = NativeExecFS(str(tmp_path))
    fs.write("f.txt", "abc")
    r = Tools(fs).edit("f.txt", "xyz", "q")
    assert not r.ok
    assert "not found" in r.feedback


def test_bash_captures_exit_and_both_streams(tmp_path):
    r = _tools(tmp_path).bash("echo out; echo err 1>&2; exit 3")
    assert not r.ok
    assert "exit: 3" in r.feedback
    assert "out" in r.feedback
    assert "err" in r.feedback


def test_dispatch_unknown_tool(tmp_path):
    r = _tools(tmp_path).dispatch("frobnicate", {})
    assert not r.ok
    assert "unknown tool" in r.feedback


def test_dispatch_missing_arg(tmp_path):
    r = _tools(tmp_path).dispatch("read", {})
    assert not r.ok
    assert "missing required" in r.feedback
