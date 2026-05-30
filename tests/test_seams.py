"""A1 — the three adapter seams are well-formed and implementable.

Build a trivial in-memory adapter for each seam, bind them into an ``Adapters``
bundle, and assert structural conformance plus the contracts the core leans on
(injection round-trip, exit codes, exact-replace edit). No network, no
subprocess — just shape and behaviour.
"""

from tack.adapters import (
    Adapters,
    Completion,
    Control,
    ExecFS,
    ExecResult,
    LLMTransport,
    Message,
)


class _FakeLLM:
    def complete(self, messages, **opts):
        last = messages[-1]["content"] if messages else ""
        return Completion(content=f"echo:{last}", stop_reason="stop")


class _FakeControl:
    def __init__(self):
        self._tasks: list[str] = []
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def inject_task(self, task):
        self._tasks.append(task)

    def is_cancelled(self):
        return self._cancelled

    def take_injected_task(self):
        return self._tasks.pop(0) if self._tasks else None


class _FakeExecFS:
    def __init__(self):
        self._fs: dict[str, str] = {}

    def run(self, cmd, *, timeout=None):
        return ExecResult(stdout="", stderr="", exit_code=0)

    def read(self, path):
        return self._fs[path]

    def write(self, path, content):
        self._fs[path] = content

    def edit(self, path, old, new):
        self._fs[path] = self._fs[path].replace(old, new)


def test_seams_are_structurally_conformant():
    assert isinstance(_FakeLLM(), LLMTransport)
    assert isinstance(_FakeControl(), Control)
    assert isinstance(_FakeExecFS(), ExecFS)


def test_adapters_bundle_binds_all_three():
    a = Adapters(llm=_FakeLLM(), control=_FakeControl(), execfs=_FakeExecFS())
    reply = a.llm.complete([Message(role="user", content="hi")])
    assert reply.content == "echo:hi"
    assert reply.stop_reason == "stop"


def test_control_injection_roundtrip():
    c = _FakeControl()
    assert c.take_injected_task() is None
    c.inject_task("do x")
    assert c.is_cancelled() is False
    assert c.take_injected_task() == "do x"
    assert c.take_injected_task() is None
    c.cancel()
    assert c.is_cancelled() is True


def test_execresult_exit_code_is_the_signal():
    fs = _FakeExecFS()
    assert fs.run("pytest").exit_code == 0


def test_execfs_edit_is_exact_replace():
    fs = _FakeExecFS()
    fs.write("a.txt", "hello world")
    fs.edit("a.txt", "world", "tack")
    assert fs.read("a.txt") == "hello tack"
