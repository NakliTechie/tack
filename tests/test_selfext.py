"""B1 — the self-written-tool registry and promotion-via-verification."""

from tack.adapters.native import NativeExecFS
from tack.core.selfext import ToolRegistry


def _fs(tmp_path):
    return NativeExecFS(str(tmp_path))


def test_scan_registers_new_tools_as_provisional(tmp_path):
    fs = _fs(tmp_path)
    fs.write(".tack/bin/greet", "#!/bin/sh\necho hi\n")
    reg = ToolRegistry(fs)
    assert reg.scan(turn=1) == ["greet"]
    assert reg.tools["greet"].state == "provisional"
    assert reg.tools["greet"].created_turn == 1


def test_promotion_requires_use_then_green(tmp_path):
    fs = _fs(tmp_path)
    fs.write(".tack/bin/greet", "#!/bin/sh\necho hi\n")
    reg = ToolRegistry(fs)
    reg.scan(1)
    assert reg.promote_used() == []  # never used → stays provisional
    assert reg.tools["greet"].state == "provisional"
    reg.note_uses("sh .tack/bin/greet")
    assert reg.tools["greet"].used == 1
    assert reg.promote_used() == ["greet"]  # used + green → promoted
    assert reg.tools["greet"].state == "verified"


def test_registry_persists_across_instances(tmp_path):
    fs = _fs(tmp_path)
    fs.write(".tack/bin/t", "echo x")
    r1 = ToolRegistry(fs)
    r1.scan(1)
    r1.note_uses("t")
    r1.promote_used()
    r2 = ToolRegistry(fs)  # reload from .tack/tools.json
    assert r2.tools["t"].state == "verified"


def test_rewritten_tool_drops_back_to_provisional(tmp_path):
    fs = _fs(tmp_path)
    fs.write(".tack/bin/t", "echo v1")
    reg = ToolRegistry(fs)
    reg.scan(1)
    reg.note_uses("t")
    reg.promote_used()
    assert reg.tools["t"].state == "verified"
    fs.write(".tack/bin/t", "echo v2 changed")  # rewritten → trust re-earned
    reg.scan(2)
    assert reg.tools["t"].state == "provisional"


def test_note_uses_is_token_not_substring(tmp_path):
    fs = _fs(tmp_path)
    fs.write(".tack/bin/cat", "echo x")
    reg = ToolRegistry(fs)
    reg.scan(1)
    assert reg.note_uses("echo concatenate") == []  # 'cat' inside a word — not a use
    assert reg.note_uses(".tack/bin/cat input.txt") == ["cat"]  # real invocation


def test_summary_lists_state(tmp_path):
    fs = _fs(tmp_path)
    fs.write(".tack/bin/a", "x")
    fs.write(".tack/bin/b", "y")
    reg = ToolRegistry(fs)
    reg.scan(1)
    reg.note_uses("a")
    reg.promote_used()
    summary = reg.summary()
    assert "a [verified]" in summary
    assert "b [provisional]" in summary


def test_empty_registry_summary_is_blank(tmp_path):
    assert ToolRegistry(_fs(tmp_path)).summary() == ""
