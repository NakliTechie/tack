"""Shared test helpers: a scripted (deterministic) brain and an adapter factory.

The scripted brain stands in for a live model so the loop can be driven through
exact paths — no network, no key. ExecFS/Control/git/pytest all run for real.
"""

import json

import pytest

from tack.adapters.base import Adapters, Completion
from tack.adapters.native import NativeControl, NativeExecFS


class ScriptedLLM:
    """Returns queued replies in order; clamps to the last once exhausted."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.i = 0
        self.seen: list = []

    def complete(self, messages, **opts):
        self.seen.append(messages)
        reply = self.replies[min(self.i, len(self.replies) - 1)]
        self.i += 1
        return Completion(content=reply)


@pytest.fixture
def act():
    """Build a model reply carrying exactly one fenced action block."""

    def _act(tool, **args):
        return "Reasoning about the next step.\n```action\n" + json.dumps(
            {"tool": tool, **args}
        ) + "\n```"

    return _act


@pytest.fixture
def scripted(tmp_path):
    """Factory: replies -> Adapters bound to this test's tmp_path workspace."""

    def _build(replies):
        return Adapters(
            llm=ScriptedLLM(replies),
            control=NativeControl(),
            execfs=NativeExecFS(str(tmp_path)),
        )

    return _build
