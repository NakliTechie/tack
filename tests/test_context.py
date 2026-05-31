"""A7 — context engine: filesystem-as-memory + progressive compaction."""

from tack.adapters.base import Completion, Message
from tack.adapters.native import NativeExecFS
from tack.core.context import Context, ContextConfig


class _StubLLM:
    def __init__(self, reply="SUMMARY"):
        self.reply = reply
        self.calls: list = []

    def complete(self, messages, **opts):
        self.calls.append(messages)
        return Completion(content=self.reply)


def test_system_messages_inject_conventions_and_plan(tmp_path):
    fs = NativeExecFS(str(tmp_path))
    fs.write("AGENTS.md", "be careful")
    fs.write(".tack/plan.md", "1. do x")
    ctx = Context(fs, _StubLLM(), system_prompt="SYS")
    blob = " ".join(m["content"] for m in ctx.system_messages())
    assert "SYS" in blob
    assert "be careful" in blob
    assert "do x" in blob


def test_plan_read_write(tmp_path):
    ctx = Context(NativeExecFS(str(tmp_path)), _StubLLM(), system_prompt="S")
    assert ctx.read_plan() == ""
    ctx.write_plan("step one")
    assert "step one" in ctx.read_plan()


def test_system_messages_inject_workspace_playbook(tmp_path):
    fs = NativeExecFS(str(tmp_path))
    fs.write(".tack/playbook.md", "always run pytest -q first")
    ctx = Context(fs, _StubLLM(), system_prompt="S")
    blob = " ".join(m["content"] for m in ctx.system_messages())
    assert "always run pytest -q first" in blob


def test_system_messages_append_extra_blocks(tmp_path):
    ctx = Context(NativeExecFS(str(tmp_path)), _StubLLM(), system_prompt="S")
    extra = [Message(role="system", content="DYNAMIC LEARNING BLOCK")]
    blob = " ".join(m["content"] for m in ctx.system_messages(extra))
    assert "DYNAMIC LEARNING BLOCK" in blob


def test_no_compaction_under_threshold(tmp_path):
    ctx = Context(
        NativeExecFS(str(tmp_path)),
        _StubLLM(),
        system_prompt="S",
        config=ContextConfig(compact_threshold_tokens=100_000, keep_recent_turns=2),
    )
    hist = [Message(role="user", content="hi")]
    assert ctx.maybe_compact(hist) is hist


def test_compaction_summarizes_oldest_keeps_recent(tmp_path):
    llm = _StubLLM("COMPACTED")
    ctx = Context(
        NativeExecFS(str(tmp_path)),
        llm,
        system_prompt="S",
        config=ContextConfig(compact_threshold_tokens=1, keep_recent_turns=2),
    )
    hist = [
        Message(role="user", content="a" * 100),
        Message(role="assistant", content="b" * 100),
        Message(role="user", content="c" * 100),
        Message(role="assistant", content="recent-1"),
        Message(role="user", content="recent-2"),
    ]
    out = ctx.maybe_compact(hist)
    assert len(out) == 3
    assert "COMPACTED" in out[0]["content"]
    assert out[-2]["content"] == "recent-1"
    assert out[-1]["content"] == "recent-2"
    assert llm.calls  # the summarizer was actually invoked
