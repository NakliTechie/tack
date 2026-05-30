"""A10 — the v1.0 closed-loop gate (harness mechanics).

A deterministic brain drives a *real* broken project to green: failing pytest →
read → edit the source → the loop's own verification flips to exit 0 and stops.
Real filesystem, real subprocess, real git, real pytest. The live-model run and
the SWE-bench-lite number (A11) are deferred until an API key is available — but
the harness itself is proven end to end here.
"""

BUGGY = "def add(a, b):\n    return a - b\n"  # the bug: minus instead of plus
TEST = "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"


def test_closed_loop_drives_failing_test_to_green(tmp_path, scripted, act):
    (tmp_path / "calc.py").write_text(BUGGY)
    (tmp_path / "test_calc.py").write_text(TEST)

    from tack.core.loop import Config, run_task

    adapters = scripted(
        [
            act("bash", cmd="pytest -q"),  # observe the failure (red)
            act("read", path="calc.py"),  # inspect the source
            act("edit", path="calc.py", old="return a - b", new="return a + b"),  # fix
        ]
    )

    res = run_task(
        "Make the failing test pass.",
        adapters,
        workspace=str(tmp_path),
        config=Config(max_iterations=8),
    )

    # the loop reached green on its own ground-truth check
    assert res.success
    assert res.stop_reason == "verified"
    assert res.verify_command == "pytest -q"
    assert res.turns == 3

    # the fix really landed on disk
    assert "return a + b" in (tmp_path / "calc.py").read_text()

    # every step was a real commit; the edit step is in the log
    assert res.final_head
    log = adapters.execfs.run("git log --oneline").stdout
    assert "tack turn 3: edit" in log

    # the transcript closes green
    assert res.transcript[-1]["verify_passed"] is True


def test_closed_loop_is_undoable(tmp_path, scripted, act):
    """git-per-step means the pre-edit state is recoverable by reset."""
    (tmp_path / "calc.py").write_text(BUGGY)
    (tmp_path / "test_calc.py").write_text(TEST)

    from tack.core.loop import Config, run_task
    from tack.core.safety import GitStepper

    adapters = scripted(
        [
            act("edit", path="calc.py", old="return a - b", new="return a + b"),
        ]
    )
    res = run_task("fix it", adapters, workspace=str(tmp_path), config=Config(max_iterations=4))
    assert res.success
    assert "return a + b" in (tmp_path / "calc.py").read_text()

    # roll the workspace back to the baseline commit — the bug returns, proving
    # each step is genuinely undoable
    baseline = adapters.execfs.run("git rev-list --max-parents=0 HEAD").stdout.strip()
    GitStepper(adapters.execfs).revert_to(baseline)
    assert "return a - b" in (tmp_path / "calc.py").read_text()
