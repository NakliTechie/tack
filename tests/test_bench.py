"""A11 — the baseline harness: task setup, scoring, report (keyless)."""

import json

from tack.adapters.base import Adapters, Completion
from tack.adapters.native import NativeControl, NativeExecFS
from tack.bench import TASKS, run_bench
from tack.bench import main as bench_main
from tack.core.loop import Config, TaskResult, run_task


class _Brain:
    def __init__(self, replies):
        self.replies = replies
        self.i = 0

    def complete(self, messages, **opts):
        reply = self.replies[min(self.i, len(self.replies) - 1)]
        self.i += 1
        return Completion(content=reply)


def _act(tool, **args):
    return "x\n```action\n" + json.dumps({"tool": tool, **args}) + "\n```"


def _const_solver(success, reason):
    def solve(prompt, work):
        return TaskResult(success=success, stop_reason=reason, turns=1, verify_command="pytest -q")

    return solve


def test_report_counts_all_pass():
    report = run_bench(TASKS[:2], _const_solver(True, "verified"))
    assert report.passed == 2
    assert report.total == 2
    assert "2/2" in report.render()
    assert "[PASS]" in report.render()


def test_report_counts_all_fail():
    report = run_bench(TASKS[:2], _const_solver(False, "doom_loop"))
    assert report.passed == 0
    assert "[FAIL]" in report.render()


def test_task_set_is_nontrivial():
    assert len(TASKS) >= 4
    for t in TASKS:
        assert any(p.startswith("test_") for p in t.files)  # each ships a failing test


def test_run_bench_end_to_end_on_one_task():
    """Drive the first task to green through the real harness (scripted brain),
    proving task setup + solver wiring + scoring all work."""
    task = TASKS[0]  # subtraction_for_addition: add returns a - b

    def solve(prompt, work):
        brain = _Brain([_act("edit", path="calc.py", old="return a - b", new="return a + b")])
        adapters = Adapters(llm=brain, control=NativeControl(), execfs=NativeExecFS(work))
        return run_task(prompt, adapters, workspace=work, config=Config(max_iterations=5))

    report = run_bench([task], solve)
    assert report.passed == 1
    assert report.results[0].stop_reason == "verified"


def test_bench_main_errors_without_key(monkeypatch, capsys):
    for var in ("OPENAI_API_KEY", "TACK_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    assert bench_main(["--model", "gpt-4o-mini"]) == 2
    assert "no API key" in capsys.readouterr().err
