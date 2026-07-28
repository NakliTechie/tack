"""Tests for the director loop — spec ingestion, plan generation, phase
execution, checkpoint/resume, and dependency ordering.

Uses the scripted brain from conftest.py so all tests run keyless.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from tack.adapters.base import Adapters, Completion
from tack.adapters.native import NativeControl, NativeExecFS
from tack.core.loop import Config
from tack.director import (
    DirectorState,
    _check_aider_available,
    _ready_phases,
    _resolve_backend,
    build_from_specs,
    build_plan_from_specs,
    load_specs,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SIMPLE_SPEC = "# Test\n\nA simple project."
PHASE_PLAN_JSON = json.dumps([
    {
        "id": "01-setup",
        "title": "Setup",
        "task": "Initialize the project",
        "verify": None,
        "depends_on": [],
    },
    {
        "id": "02-build",
        "title": "Build",
        "task": "Build feature",
        "verify": "pytest -q",
        "depends_on": ["01-setup"],
    },
])


def make_reply(tool: str, **args) -> str:
    return f"step\n```action\n{json.dumps({'tool': tool, **args})}\n```"


class ScriptedBrain:
    """Returns queued replies in order; clamps at the last."""

    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.i = 0

    def complete(self, messages, **opts) -> Completion:
        reply = self.replies[min(self.i, len(self.replies) - 1)]
        self.i += 1
        return Completion(content=reply)


# Lightweight mock control that doesn't raise on method call.
class MockControl:
    def is_cancelled(self) -> bool:
        return False
    def take_injected_task(self):
        return None
    def cancel(self) -> None:
        pass
    def inject_task(self, task: str) -> None:
        pass


@staticmethod
def _mock_exec(read_map: dict[str, str] | None = None):
    store: dict[str, str] = dict(read_map or {})

    def _run(cmd: str, timeout=None):
        # Only used by director for verify discovery — must look like a real result.
        return type("R", (), {"stdout": "", "stderr": "", "exit_code": 0})()

    def _read(path: str) -> str:
        return store.get(path, "")

    def _write(path: str, content: str) -> None:
        store[path] = content

    def _edit(path: str, old: str, new: str) -> None:
        store[path] = store.get(path, "").replace(old, new, 1)

    return type("MockExecFS", (), {
        "run": _run,
        "read": _read,
        "write": _write,
        "edit": _edit,
    })()


# ---------------------------------------------------------------------------
# load_specs
# ---------------------------------------------------------------------------


def test_load_specs_reads_markdown_files(tmp_path: pathlib.Path) -> None:
    (tmp_path / "vision.md").write_text("# Vision\n\nBuild something great.")
    (tmp_path / "handoff.md").write_text("# Handoff\n\nMake it work.")
    specs = load_specs(str(tmp_path))
    assert len(specs) == 2
    assert specs[0]["file"] == "handoff.md"  # sorted alphabetically
    assert specs[1]["file"] == "vision.md"


def test_load_specs_ignores_empty(tmp_path: pathlib.Path) -> None:
    (tmp_path / "empty.md").write_text("   \n\n  ")  # whitespace-only
    (tmp_path / "real.md").write_text("content")
    specs = load_specs(str(tmp_path))
    assert len(specs) == 1
    assert specs[0]["file"] == "real.md"


def test_load_specs_raises_on_missing_dir() -> None:
    with pytest.raises(NotADirectoryError):
        load_specs("/nonexistent/path")


def test_load_specs_raises_on_empty_dir(tmp_path: pathlib.Path) -> None:
    with pytest.raises(ValueError, match="no .md files"):
        load_specs(str(tmp_path))


# ---------------------------------------------------------------------------
# build_plan_from_specs
# ---------------------------------------------------------------------------


def test_build_plan_from_specs_parses_json(tmp_path: pathlib.Path) -> None:
    brain = ScriptedBrain([PHASE_PLAN_JSON])
    specs = [{"file": "vision.md", "content": SIMPLE_SPEC}]
    phases = build_plan_from_specs(brain, specs, title="Test")
    assert len(phases) == 2
    assert phases[0]["id"] == "01-setup"
    assert phases[0]["title"] == "Setup"
    assert phases[1]["depends_on"] == ["01-setup"]


def test_build_plan_from_specs_fallback_on_bad_json(tmp_path: pathlib.Path) -> None:
    brain = ScriptedBrain(["this is not json"])
    specs = [{"file": "vision.md", "content": SIMPLE_SPEC}]
    phases = build_plan_from_specs(brain, specs, title="Fallback")
    assert len(phases) == 1
    assert phases[0]["id"] == "01-build"
    assert "Fallback" in phases[0]["title"]


def test_build_plan_from_specs_handles_fenced_json(tmp_path: pathlib.Path) -> None:
    fenced = f"```json\n{PHASE_PLAN_JSON}\n```"
    brain = ScriptedBrain([fenced])
    specs = [{"file": "vision.md", "content": SIMPLE_SPEC}]
    phases = build_plan_from_specs(brain, specs)
    assert len(phases) == 2


# ---------------------------------------------------------------------------
# _ready_phases
# ---------------------------------------------------------------------------


def test_ready_phases_all_independent() -> None:
    phases = [
        {"id": "a", "depends_on": []},
        {"id": "b", "depends_on": []},
    ]
    ready, blocked = _ready_phases(phases, set(), set())
    assert len(ready) == 2
    assert len(blocked) == 0


def test_ready_phases_respects_order() -> None:
    phases = [
        {"id": "a", "depends_on": []},
        {"id": "b", "depends_on": ["a"]},
    ]
    ready, _ = _ready_phases(phases, set(), set())
    assert len(ready) == 1
    assert ready[0]["id"] == "a"

    ready, _ = _ready_phases(phases, {"a"}, set())
    assert len(ready) == 1
    assert ready[0]["id"] == "b"


def test_ready_phases_blocks_on_failed_dep() -> None:
    phases = [
        {"id": "a", "depends_on": []},
        {"id": "b", "depends_on": ["a"]},
        {"id": "c", "depends_on": ["b"]},
    ]
    # 'a' failed → 'b' blocked → 'c' transitively blocked
    ready, blocked = _ready_phases(phases, set(), {"a"})
    assert len(ready) == 0
    assert "b" in blocked
    # 'c' is not directly blocked by a failed dep, but its dep 'b' is
    # never ready — so it won't appear in either list. That's correct:
    # it'll never be attempted.
    assert "c" not in blocked  # it's not in ready either


def test_ready_phases_skips_completed() -> None:
    phases = [
        {"id": "a", "depends_on": []},
        {"id": "b", "depends_on": []},
    ]
    ready, _ = _ready_phases(phases, {"a"}, set())
    assert len(ready) == 1
    assert ready[0]["id"] == "b"


# ---------------------------------------------------------------------------
# DirectorState checkpoint / resume
# ---------------------------------------------------------------------------


def test_state_save_and_load(tmp_path: pathlib.Path) -> None:
    state = DirectorState(
        spec_dir="/specs",
        title="Test",
        phases=[{"id": "01-test", "task": "do it", "depends_on": []}],
        results=[
            {
                "phase_id": "01-test",
                "title": "Test",
                "task": "do it",
                "status": "completed",
                "turns": 3,
                "success": True,
                "stop_reason": "verified",
            }
        ],
        started_at=1000.0,
    )
    state.save(str(tmp_path))

    loaded = DirectorState.load(str(tmp_path))
    assert loaded is not None
    assert loaded.title == "Test"
    assert len(loaded.results) == 1
    assert loaded.results[0]["status"] == "completed"

    # Resume builds on this
    completed_ids = {r["phase_id"] for r in loaded.results if r["status"] == "completed"}
    assert "01-test" in completed_ids


def test_state_load_missing(tmp_path: pathlib.Path) -> None:
    assert DirectorState.load(str(tmp_path)) is None


def test_state_load_corrupt(tmp_path: pathlib.Path) -> None:
    (tmp_path / ".tack").mkdir()
    (tmp_path / ".tack/director-state.json").write_text("not json")
    assert DirectorState.load(str(tmp_path)) is None


# ---------------------------------------------------------------------------
# Backend resolution
# ---------------------------------------------------------------------------


def test_check_aider_available() -> None:
    """Aider is installed on the dev box — should be findable on PATH."""
    assert _check_aider_available() is True


def test_resolve_backend_auto_prefers_aider() -> None:
    assert _resolve_backend(None) == "aider"
    assert _resolve_backend("auto") == "aider"


def test_resolve_backend_tack() -> None:
    assert _resolve_backend("tack") == "tack"


def test_resolve_backend_aider_raises_if_missing(monkeypatch) -> None:
    monkeypatch.setattr("tack.director._check_aider_available", lambda: False)
    with pytest.raises(RuntimeError, match="aider.*not on"):
        _resolve_backend("aider")


def test_resolve_backend_unknown() -> None:
    with pytest.raises(ValueError, match="unknown backend"):
        _resolve_backend("gpt")


# ---------------------------------------------------------------------------
# Full director loop (scripted brain)
# ---------------------------------------------------------------------------


def test_build_from_specs_two_phases(tmp_path: pathlib.Path) -> None:
    """Two phases: fix the bug, then confirm it passes. RunTask does the real
    work over real FS + subprocess; the director sequences them."""
    ws = tmp_path / "ws"
    specs_dir = tmp_path / "specs"
    ws.mkdir()
    specs_dir.mkdir()

    # Workspace: broken project (real files for real pytest)
    (ws / "calc.py").write_text("def add(a, b):\n    return a - b\n")
    (ws / "test_calc.py").write_text(
        "from calc import add\n\ndef test_add():\n    assert add(2, 3) == 5\n"
    )
    # Specs: vision + handoff
    (specs_dir / "vision.md").write_text(
        "# Calculator\n\nSimple arithmetic library."
    )
    (specs_dir / "handoff.md").write_text(
        "# Handoff\n\nFix the broken add() in calc.py and verify all tests pass."
    )

    brain = ScriptedBrain([
        PHASE_PLAN_JSON,
        # Phase 1: fix the add function
        make_reply("bash", cmd="pytest -q"),
        make_reply("read", path="calc.py"),
        make_reply("edit", path="calc.py", old="return a - b", new="return a + b"),
        # Phase 2: verify clean
        make_reply("bash", cmd="pytest -q"),
    ])

    adapters = Adapters(
        llm=brain,
        control=NativeControl(),
        execfs=NativeExecFS(str(ws)),
    )

    results = build_from_specs(
        str(specs_dir),
        adapters,
        workspace=str(ws),
        config=Config(max_iterations=8),
        backend="tack",  # scripted brain needs Tack loop
    )

    assert len(results) == 2
    assert results[0].status == "completed"
    assert results[0].phase_id == "01-setup"
    assert results[0].turns == 3  # bash → read → edit (edit makes verify pass)
    assert results[1].status == "completed"
    assert results[1].phase_id == "02-build"
    assert results[1].turns == 1  # bash (verify passes immediately)


def test_build_from_specs_resume_after_interrupt(tmp_path: pathlib.Path) -> None:
    """Simulate an interrupted build: checkpoint has one completed phase.
    Resuming should skip it and run the second."""
    ws = tmp_path / "ws"
    specs_dir = tmp_path / "specs"
    ws.mkdir()
    specs_dir.mkdir()

    (ws / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    (ws / "test_calc.py").write_text(
        "from calc import add\n\ndef test_add():\n    assert add(2, 3) == 5\n"
    )
    (specs_dir / "vision.md").write_text(
        "# Calculator\n\nSimple arithmetic library."
    )

    # Brain: no plan needed (resume loads state directly).
    # One reply: bash to run pytest (already passing in phase 2).
    brain = ScriptedBrain([
        make_reply("bash", cmd="pytest -q"),
    ])

    adapters = Adapters(
        llm=brain,
        control=NativeControl(),
        execfs=NativeExecFS(str(ws)),
    )

    # Pre-seed the checkpoint: phase 1 already done, phase 2 pending
    state = DirectorState(
        spec_dir=str(specs_dir),
        title="Test",
        phases=[
            {"id": "01-setup", "title": "Setup", "task": "make it work",
             "verify": None, "depends_on": []},
            {"id": "02-build", "title": "Build", "task": "build feature",
             "verify": "pytest -q", "depends_on": ["01-setup"]},
        ],
        results=[{
            "phase_id": "01-setup",
            "title": "Setup",
            "task": "make it work",
            "status": "completed",
            "turns": 3,
            "success": True,
            "stop_reason": "verified",
            "verify_command": None,
            "summary": "done",
        }],
        started_at=100.0,
    )
    state.save(str(ws))

    results = build_from_specs(
        str(specs_dir),
        adapters,
        workspace=str(ws),
        config=Config(max_iterations=8),
        resume=True,
        backend="tack",  # scripted brain needs Tack loop
    )

    assert len(results) == 2
    assert results[0].status == "completed"  # from checkpoint
    assert results[0].turns == 3
    assert results[1].status == "completed"  # from fresh run
    assert results[1].phase_id == "02-build"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_phase_failure_blocks_dependents(tmp_path: pathlib.Path) -> None:
    """A phase that fails should block any phase that depends on it."""
    ws = tmp_path / "ws"
    specs_dir = tmp_path / "specs"
    ws.mkdir()
    specs_dir.mkdir()

    # Workspace has a failing test — real pytest will fail
    (ws / "calc.py").write_text("def add(a, b):\n    return a - b\n")
    (ws / "test_calc.py").write_text(
        "from calc import add\n\ndef test_add():\n    assert add(2, 3) == 5\n"
    )
    (specs_dir / "vision.md").write_text("# Proj\n\nSpec.")

    failing_plan = json.dumps([
        {"id": "01-will-fail", "title": "Fails", "task": "will fail",
         "verify": None, "depends_on": []},
        {"id": "02-blocked", "title": "Blocked", "task": "depends on prev",
         "verify": None, "depends_on": ["01-will-fail"]},
    ])

    brain = ScriptedBrain([
        failing_plan,
        # Finish without fixing → pytest-verify fails → run_task
        # hits iteration_cap (or doom if it recorded the tool).
        make_reply("finish"),
    ])

    adapters = Adapters(
        llm=brain,
        control=NativeControl(),
        execfs=NativeExecFS(str(ws)),
    )

    results = build_from_specs(
        str(specs_dir),
        adapters,
        workspace=str(ws),
        config=Config(max_iterations=4),
        backend="tack",  # scripted brain needs Tack loop
    )

    assert len(results) >= 1
    assert results[0].status in ("failed", "error")
    # Phase 2 depends on phase 1 — if phase 1 failed, phase 2
    # should be blocked and never appear in results.
    assert len(results) <= 1, (
        "phase 2 should be blocked when phase 1 fails"
    )


def test_build_from_specs_no_specs_raises(tmp_path: pathlib.Path) -> None:
    specs_dir = tmp_path / "specs"
    specs_dir.mkdir()
    brain = ScriptedBrain(["irrelevant"])
    adapters = Adapters(llm=brain, control=ScriptedBrain([]), execfs=ScriptedBrain([]))

    with pytest.raises(ValueError, match="no .md files"):
        build_from_specs(str(specs_dir), adapters, backend="tack")
