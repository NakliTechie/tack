"""A2/A3/A4 — the native adapters implement the seams against a real OS.

ExecFS and Control run for real (subprocess, FS, threads). The LLM transport is
exercised with an injected fake opener — no network, no key — so the request
construction and response parsing are covered without a live call.
"""

import json

import pytest

from tack.adapters.base import Control, ExecFS, LLMTransport, Message
from tack.adapters.native import (
    NativeControl,
    NativeExecFS,
    NativeLLM,
    native_adapters,
)
from tack.errors import EditError, TransportError, WorkspaceError


# --- ExecFS ---------------------------------------------------------------
def test_execfs_conforms_and_runs(tmp_path):
    fs = NativeExecFS(str(tmp_path))
    assert isinstance(fs, ExecFS)
    r = fs.run("echo hi")
    assert r.exit_code == 0
    assert r.stdout.strip() == "hi"


def test_execfs_nonzero_exit_is_captured(tmp_path):
    fs = NativeExecFS(str(tmp_path))
    r = fs.run("ls /no/such/path/xyz")
    assert r.exit_code != 0
    assert r.stderr  # the error text the loop will feed back


def test_execfs_write_read_roundtrip_creates_parents(tmp_path):
    fs = NativeExecFS(str(tmp_path))
    fs.write("pkg/mod.py", "x = 1\n")
    assert fs.read("pkg/mod.py") == "x = 1\n"


def test_execfs_edit_exact_unique(tmp_path):
    fs = NativeExecFS(str(tmp_path))
    fs.write("a.txt", "alpha beta gamma")
    fs.edit("a.txt", "beta", "BETA")
    assert fs.read("a.txt") == "alpha BETA gamma"


def test_execfs_edit_rejects_missing(tmp_path):
    fs = NativeExecFS(str(tmp_path))
    fs.write("a.txt", "hello")
    with pytest.raises(EditError, match="not found"):
        fs.edit("a.txt", "world", "x")


def test_execfs_edit_rejects_ambiguous(tmp_path):
    fs = NativeExecFS(str(tmp_path))
    fs.write("a.txt", "na na na")
    with pytest.raises(EditError, match="appears 3 times"):
        fs.edit("a.txt", "na", "la")


def test_execfs_blocks_path_escape(tmp_path):
    fs = NativeExecFS(str(tmp_path))
    with pytest.raises(WorkspaceError):
        fs.read("../../../etc/passwd")


def test_execfs_timeout_returns_124(tmp_path):
    fs = NativeExecFS(str(tmp_path))
    r = fs.run("sleep 5", timeout=0.2)
    assert r.exit_code == 124
    assert "timed out" in r.stderr


# --- Control --------------------------------------------------------------
def test_control_conforms_and_roundtrips():
    c = NativeControl()
    assert isinstance(c, Control)
    assert c.take_injected_task() is None
    c.inject_task("t1")
    c.inject_task("t2")
    assert c.is_cancelled() is False
    assert c.take_injected_task() == "t1"
    assert c.take_injected_task() == "t2"
    assert c.take_injected_task() is None
    c.cancel()
    assert c.is_cancelled() is True


# --- LLM transport (mocked) ----------------------------------------------
class _FakeResp:
    def __init__(self, payload: dict):
        self._b = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_llm_conforms_and_parses_response():
    captured = {}

    def opener(req):
        captured["url"] = req.full_url
        captured["auth"] = req.headers.get("Authorization")
        captured["body"] = json.loads(req.data)
        return _FakeResp(
            {
                "choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 3},
            }
        )

    llm = NativeLLM(model="gpt-4o-mini", api_key="sk-test", opener=opener)
    assert isinstance(llm, LLMTransport)
    out = llm.complete([Message(role="user", content="hi")], temperature=0)

    assert out.content == "hello"
    assert out.stop_reason == "stop"
    assert out.input_tokens == 11
    assert out.output_tokens == 3
    # request was built correctly
    assert captured["url"].endswith("/chat/completions")
    assert captured["auth"] == "Bearer sk-test"
    assert captured["body"]["model"] == "gpt-4o-mini"
    assert captured["body"]["temperature"] == 0
    assert captured["body"]["messages"][0]["content"] == "hi"


def test_llm_raises_on_malformed_response():
    llm = NativeLLM(model="m", api_key="k", opener=lambda req: _FakeResp({"nope": True}))
    with pytest.raises(TransportError, match="malformed"):
        llm.complete([Message(role="user", content="hi")])


def test_native_adapters_bundle(tmp_path):
    a = native_adapters(workspace=str(tmp_path), opener=lambda req: _FakeResp({}))
    assert isinstance(a.execfs, ExecFS)
    assert isinstance(a.control, Control)
    assert isinstance(a.llm, LLMTransport)
