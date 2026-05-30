"""Runnable closed-loop demo — the A10 gate artifact (scripted brain).

Proves the harness mechanics end to end (real FS, subprocess, git, pytest) with
a deterministic 'brain' standing in for the model, so it runs with no API key.
The live-model gate and the SWE-bench-lite number (A11) run when a key is set.

    uv run python examples/demo_closed_loop.py
"""

from __future__ import annotations

import json
import pathlib
import tempfile

from tack.adapters.base import Adapters, Completion
from tack.adapters.native import NativeControl, NativeExecFS
from tack.core.loop import Config, run_task

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
    return f"Working on it.\n```action\n{json.dumps({'tool': tool, **args})}\n```"


def main() -> None:
    work = tempfile.mkdtemp(prefix="tack-demo-")
    pathlib.Path(work, "calc.py").write_text(BUGGY)
    pathlib.Path(work, "test_calc.py").write_text(TEST)

    brain = ScriptedBrain(
        [
            act("bash", cmd="pytest -q"),
            act("read", path="calc.py"),
            act("edit", path="calc.py", old="return a - b", new="return a + b"),
        ]
    )
    adapters = Adapters(llm=brain, control=NativeControl(), execfs=NativeExecFS(work))

    print(f"workspace: {work}")
    print("task: Make the failing test pass.\n")

    res = run_task(
        "Make the failing test pass.",
        adapters,
        workspace=work,
        config=Config(max_iterations=8),
    )

    for e in res.transcript:
        action = e.get("action") or {}
        tool = (action.get("tool") or "—").ljust(7)
        print(
            f"  turn {e['turn']}: {tool}  ok={e.get('tool_ok')}  "
            f"verify_passed={e.get('verify_passed')}"
        )

    print(f"\nresult : success={res.success}  stop_reason={res.stop_reason}  turns={res.turns}")
    print(f"verify : {res.verify_command}")
    print(f"HEAD   : {(res.final_head or '')[:12]}")
    print(f"summary: {res.summary or '(loop saw green on its own verification)'}")


if __name__ == "__main__":
    main()
