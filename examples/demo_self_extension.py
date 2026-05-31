"""Runnable self-extension demo — the v1.1 gate artifact (scripted brain).

The agent writes a helper script to ``.tack/bin/``, runs it to fix the bug, and
the loop promotes that tool (provisional → used in a green run → verified). A
success breadcrumb is written to a temp per-device learning store. No API key.

    uv run python examples/demo_self_extension.py
"""

from __future__ import annotations

import json
import pathlib
import tempfile

from tack.adapters.base import Adapters, Completion
from tack.adapters.native import FileLearningStore, NativeControl, NativeExecFS
from tack.core.loop import Config, run_task

BUGGY = "def add(a, b):\n    return a - b\n"
TEST = "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"
APPLY_FIX = (
    "#!/bin/sh\n"
    "python3 - <<'PY'\n"
    "import pathlib\n"
    "p = pathlib.Path('calc.py')\n"
    "p.write_text(p.read_text().replace('return a - b', 'return a + b'))\n"
    "PY\n"
)


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
    work = tempfile.mkdtemp(prefix="tack-v11-")
    home = tempfile.mkdtemp(prefix="tack-home-")
    pathlib.Path(work, "calc.py").write_text(BUGGY)
    pathlib.Path(work, "test_calc.py").write_text(TEST)

    brain = ScriptedBrain(
        [
            act("write", path=".tack/bin/apply_fix", content=APPLY_FIX),
            act("bash", cmd="sh .tack/bin/apply_fix"),
        ]
    )
    adapters = Adapters(llm=brain, control=NativeControl(), execfs=NativeExecFS(work))
    learning = FileLearningStore(root=home)

    print(f"workspace    : {work}")
    print(f"device store : {home}\n")

    res = run_task(
        "Fix add() with a helper you write.",
        adapters,
        workspace=work,
        config=Config(max_iterations=6),
        learning=learning,
    )

    for e in res.transcript:
        a = e.get("action") or {}
        tool = (a.get("tool") or "—").ljust(6)
        print(
            f"  turn {e['turn']}: {tool}  ok={e.get('tool_ok')}  "
            f"verify={e.get('verify_passed')}  new_tools={e.get('new_tools')}"
        )

    print(f"\nresult         : success={res.success}  stop={res.stop_reason}  turns={res.turns}")
    print(f"promoted tools : {res.promoted_tools}  (provisional → used in a green run → verified)")
    print(f"device playbook: {FileLearningStore(root=home).prior_knowledge()!r}")


if __name__ == "__main__":
    main()
