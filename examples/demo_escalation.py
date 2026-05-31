"""Runnable escalation demo — the v1.2 gate artifact (scripted brains).

A cheap model doom-loops on a wrong edit; the loop escalates to a frontier model,
which fixes the bug and reaches green. The legible trace shows the hand-off. No
API key — two scripted brains stand in for the cheap and frontier models.

    uv run python examples/demo_escalation.py
"""

from __future__ import annotations

import json
import pathlib
import tempfile

from tack.adapters.base import Adapters, Completion
from tack.adapters.native import NativeControl, NativeExecFS
from tack.core.loop import Config, run_task
from tack.core.trace import render_trace

BUGGY = "def add(a, b):\n    return a - b\n"
TEST = "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"


class ScriptedBrain:
    def __init__(self, replies: list[str]):
        self.replies = replies
        self.i = 0

    def complete(self, messages, **opts) -> Completion:
        reply = self.replies[min(self.i, len(self.replies) - 1)]
        self.i += 1
        return Completion(content=reply)


def act(tool: str, **args) -> str:
    return f"step\n```action\n{json.dumps({'tool': tool, **args})}\n```"


def main() -> None:
    work = tempfile.mkdtemp(prefix="tack-v12-")
    pathlib.Path(work, "calc.py").write_text(BUGGY)
    pathlib.Path(work, "test_calc.py").write_text(TEST)

    cheap = ScriptedBrain([act("edit", path="calc.py", old="NONEXISTENT", new="x")])  # fails always
    frontier = ScriptedBrain([act("edit", path="calc.py", old="return a - b", new="return a + b")])
    adapters = Adapters(llm=cheap, control=NativeControl(), execfs=NativeExecFS(work))

    print(f"workspace: {work}\n")
    res = run_task(
        "Make the failing test pass.",
        adapters,
        workspace=work,
        config=Config(doom_window=3, max_iterations=10),
        frontier=frontier,
    )

    print(render_trace(res))
    print(
        f"\ncheap calls: {cheap.i}  frontier calls: {frontier.i}  "
        f"escalated@{res.escalation_turn}  success={res.success}"
    )


if __name__ == "__main__":
    main()
