"""Runnable director demo — multi-phase build from spec documents.

Creates a temp workspace with a broken project and two spec files, then feeds
them to Tack's director loop. The director reads the specs, generates a phased
build plan (scripted), and executes each phase through run_task().

    uv run python examples/demo_director.py
"""

from __future__ import annotations

import json
import pathlib
import tempfile

from tack.adapters.base import Adapters, Completion
from tack.adapters.native import NativeControl, NativeExecFS
from tack.core.loop import Config
from tack.director import build_from_specs

# ---------------------------------------------------------------------------
# Broken project
# ---------------------------------------------------------------------------
CALC_PY = "def add(a, b):\n    return a - b\n"
TEST_CALC_PY = (
    "from calc import add\n\n"
    "def test_add():\n"
    "    assert add(2, 3) == 5\n"
)

# ---------------------------------------------------------------------------
# Spec docs the director will read
# ---------------------------------------------------------------------------
VISION_MD = """# Calculator project

A simple Python calculator library with basic arithmetic.

## Requirements
- `add(a, b)` returns the sum of a and b
- The project must pass all tests

## Constraints
- Python 3, no external dependencies
"""

HANDOFF_MD = """# Handoff

The project has a failing test. Fix it.

## Current state
- `calc.py` has a buggy `add` function
- `test_calc.py` has a test that fails

## Definition of done
- All tests pass (`pytest -q` exits 0)
"""

# ---------------------------------------------------------------------------
# Scripted brain: returns replies in order; clamps at the last.
# ---------------------------------------------------------------------------
PHASE_PLAN = json.dumps([
    {
        "id": "01-fix-add",
        "title": "Fix the add function",
        "task": "Make the failing test pass in calc.py",
        "verify": "pytest -q",
        "depends_on": [],
    },
    {
        "id": "02-verify-clean",
        "title": "Verify final state",
        "task": "Run the full test suite to confirm everything passes",
        "verify": "pytest -q",
        "depends_on": ["01-fix-add"],
    },
])


def act(tool: str, **args: str) -> str:
    return f"Working on it.\n```action\n{json.dumps({'tool': tool, **args})}\n```"


# Reply sequence:
#   0 → phase plan (planning call from build_plan_from_specs)
#   1 → phase 1: run tests (they fail)
#   2 → phase 1: read the buggy file
#   3 → phase 1: edit the fix
#   4 → phase 1: run tests (now green → phase done)
#   5 → phase 2: run tests (already green → phase done)
SCRIPTED_REPLIES = [
    PHASE_PLAN,
    act("bash", cmd="pytest -q"),
    act("read", path="calc.py"),
    act("edit", path="calc.py", old="return a - b", new="return a + b"),
    act("bash", cmd="pytest -q"),
    act("bash", cmd="pytest -q"),
]


class ScriptedBrain:
    """Deterministic model stand-in — returns queued replies."""

    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.i = 0
        self.seen: list = []

    def complete(self, messages, **opts) -> Completion:
        self.seen.append(messages)
        reply = self.replies[min(self.i, len(self.replies) - 1)]
        self.i += 1
        return Completion(content=reply)


def main() -> None:
    work = tempfile.mkdtemp(prefix="tack-director-demo-")
    specs_dir = tempfile.mkdtemp(prefix="tack-specs-")

    # Seed the workspace with the broken project
    pathlib.Path(work, "calc.py").write_text(CALC_PY)
    pathlib.Path(work, "test_calc.py").write_text(TEST_CALC_PY)

    # Write spec documents
    pathlib.Path(specs_dir, "vision.md").write_text(VISION_MD)
    pathlib.Path(specs_dir, "handoff.md").write_text(HANDOFF_MD)

    brain = ScriptedBrain(SCRIPTED_REPLIES)
    adapters = Adapters(
        llm=brain,
        control=NativeControl(),
        execfs=NativeExecFS(work),
    )

    print(f"workspace : {work}")
    print(f"specs dir : {specs_dir}")
    print(f"specs     : vision.md + handoff.md")
    print(f"project   : calc.py (buggy add) + test_calc.py (failing test)")
    print()

    results = build_from_specs(
        specs_dir,
        adapters,
        workspace=work,
        config=Config(max_iterations=8),
    )

    print(f"\nFinal project state:")
    print(f"  calc.py  : {pathlib.Path(work, 'calc.py').read_text().strip()}")
    passed = all(r.status == "completed" for r in results)
    print(f"\noverall   : {'✓ PASS' if passed else '✗ FAIL'}")
    print(f"phases    : {len(results)} ({sum(1 for r in results if r.status == 'completed')} passed)")


if __name__ == "__main__":
    main()
