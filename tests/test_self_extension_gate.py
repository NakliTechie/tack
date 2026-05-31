"""B4 — the v1.1 gate (mechanics).

Two halves, both Vision §6 / Handoff §8:
  1. the agent solves a task using a tool it wrote earlier (provisional → used in
     a green run → promoted);
  2. a known anti-pattern is recorded on a doom-loop, and a seeded anti-pattern is
     surfaced to the agent so it can be avoided.

Driven by the scripted brain over real FS / subprocess / git / pytest. The
live-model demonstration is owed once a key is wired.
"""

from tack.adapters.native import FileLearningStore
from tack.core.loop import Config, run_task

BUGGY = "def add(a, b):\n    return a - b\n"
TEST = "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"

# A helper the agent "writes" to .tack/bin/ and then runs to do the fix.
APPLY_FIX = (
    "#!/bin/sh\n"
    "python3 - <<'PY'\n"
    "import pathlib\n"
    "p = pathlib.Path('calc.py')\n"
    "p.write_text(p.read_text().replace('return a - b', 'return a + b'))\n"
    "PY\n"
)


def test_gate_solves_task_with_a_self_written_tool(tmp_path, scripted, act):
    (tmp_path / "calc.py").write_text(BUGGY)
    (tmp_path / "test_calc.py").write_text(TEST)

    adapters = scripted(
        [
            act("write", path=".tack/bin/apply_fix", content=APPLY_FIX),
            act("bash", cmd="sh .tack/bin/apply_fix"),
        ]
    )
    res = run_task(
        "Fix add() using a helper script you write.",
        adapters,
        workspace=str(tmp_path),
        config=Config(max_iterations=6),
    )

    assert res.success
    assert res.stop_reason == "verified"
    # the tool was provisional, then used in the turn that reached green → promoted
    assert res.promoted_tools == ["apply_fix"]
    assert "return a + b" in (tmp_path / "calc.py").read_text()


def test_gate_records_anti_pattern_on_doom_loop(tmp_path, scripted, act):
    store = FileLearningStore(root=str(tmp_path / "dev"))
    adapters = scripted([act("bash", cmd="false")])  # same failing action forever
    res = run_task(
        "do the thing",
        adapters,
        workspace=str(tmp_path),
        config=Config(git_per_step=False, doom_window=3),
        learning=store,
    )
    assert res.stop_reason == "doom_loop"
    # the stall signature is now in the device store, to be avoided next time
    assert "bash:false" in store.prior_knowledge()


def test_gate_known_anti_pattern_is_surfaced_to_the_agent(tmp_path, scripted, act):
    store = FileLearningStore(root=str(tmp_path / "dev"))
    store.record_anti_pattern("repeated action: bash:rm -rf build", "wiped needed artifacts")

    adapters = scripted([act("finish", summary="done, avoided the known trap")])
    res = run_task(
        "ship it",
        adapters,
        workspace=str(tmp_path),
        config=Config(git_per_step=False),
        learning=store,
    )
    # the agent was told about the anti-pattern (injected into its context)…
    assert any(
        "bash:rm -rf build" in m["content"] for msgs in adapters.llm.seen for m in msgs
    )
    # …and finished cleanly without ever emitting it
    assert res.success
