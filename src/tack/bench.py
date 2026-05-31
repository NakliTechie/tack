"""A11 — a small fixed task set + runner: the v1.0 gate's baseline number.

The handoff accepts "SWE-bench-lite OR a small fixed task set". This is the
latter: a handful of self-contained Python bug-fix tasks (buggy source + a
failing test), each run in a fresh temp workspace. A task *passes* when the loop
reaches ground-truth green (``stop_reason == "verified"``). The score is the
baseline the D1 (Karkhana) tax is later measured against.

SWE-bench-lite proper is a future swap-in — the runner is solver-agnostic
(``run_bench(tasks, solve)``), so only ``tasks`` and ``solve`` change.

Run the baseline against a real model (needs a key):

    OPENAI_API_KEY=sk-... uv run tack-bench --model gpt-4o-mini
    OPENAI_API_KEY=sk-... uv run tack-bench --model gpt-4o-mini --frontier-model gpt-4o
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass

from tack.adapters.native import NativeLLM, native_adapters
from tack.core.loop import Config, TaskResult, run_task

PROMPT = "Make the failing test pass. Edit the source, not the test."


@dataclass
class TaskCase:
    name: str
    files: dict[str, str]


# --- the fixed task set: small, varied, self-contained Python bugs --------
TASKS: list[TaskCase] = [
    TaskCase(
        "subtraction_for_addition",
        {
            "calc.py": "def add(a, b):\n    return a - b\n",
            "test_calc.py": (
                "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"
            ),
        },
    ),
    TaskCase(
        "max_returns_min",
        {
            "pick.py": "def bigger(a, b):\n    return a if a < b else b\n",
            "test_pick.py": (
                "from pick import bigger\n\n\n"
                "def test_bigger():\n    assert bigger(7, 2) == 7\n    assert bigger(1, 9) == 9\n"
            ),
        },
    ),
    TaskCase(
        "off_by_one_range",
        {
            "seq.py": "def up_to(n):\n    return list(range(1, n))\n",
            "test_seq.py": (
                "from seq import up_to\n\n\n"
                "def test_up_to():\n    assert up_to(5) == [1, 2, 3, 4, 5]\n"
            ),
        },
    ),
    TaskCase(
        "fizzbuzz_swapped",
        {
            "fb.py": (
                "def fizzbuzz(n):\n"
                "    if n % 3 == 0:\n        return 'Buzz'\n"
                "    if n % 5 == 0:\n        return 'Fizz'\n"
                "    return str(n)\n"
            ),
            "test_fb.py": (
                "from fb import fizzbuzz\n\n\n"
                "def test_fb():\n"
                "    assert fizzbuzz(3) == 'Fizz'\n"
                "    assert fizzbuzz(5) == 'Buzz'\n"
                "    assert fizzbuzz(7) == '7'\n"
            ),
        },
    ),
    TaskCase(
        "wrong_default_arg",
        {
            "greet.py": "def greet(name, prefix='Bye'):\n    return f'{prefix}, {name}'\n",
            "test_greet.py": (
                "from greet import greet\n\n\n"
                "def test_greet():\n    assert greet('Tack') == 'Hello, Tack'\n"
            ),
        },
    ),
]


@dataclass
class BenchResult:
    name: str
    passed: bool
    stop_reason: str
    turns: int
    escalated: bool


@dataclass
class BenchReport:
    results: list[BenchResult]

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def total(self) -> int:
        return len(self.results)

    def render(self) -> str:
        lines = [f"Tack baseline — {self.passed}/{self.total} tasks passed"]
        for r in self.results:
            tag = "PASS" if r.passed else "FAIL"
            esc = " (escalated)" if r.escalated else ""
            lines.append(f"  [{tag}] {r.name:<26} {r.stop_reason:<14} {r.turns} turn(s){esc}")
        pct = round(100 * self.passed / self.total) if self.total else 0
        lines.append(f"score: {self.passed}/{self.total} ({pct}%)")
        return "\n".join(lines)


# solver signature: (task_prompt, workspace_dir) -> TaskResult
Solver = Callable[[str, str], TaskResult]


def run_bench(tasks: list[TaskCase], solve: Solver, *, prompt: str = PROMPT) -> BenchReport:
    """Set up each task in a fresh temp workspace, solve it, and score it."""
    results: list[BenchResult] = []
    for task in tasks:
        with tempfile.TemporaryDirectory(prefix=f"tack-bench-{task.name}-") as work:
            for rel, content in task.files.items():
                path = pathlib.Path(work, rel)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            res = solve(prompt, work)
            results.append(
                BenchResult(
                    name=task.name,
                    passed=res.success and res.stop_reason == "verified",
                    stop_reason=res.stop_reason,
                    turns=res.turns,
                    escalated=res.escalated,
                )
            )
    return BenchReport(results)


def native_solver(
    *,
    model: str,
    frontier_model: str | None = None,
    base_url: str = "https://api.openai.com/v1",
    max_iterations: int = 25,
) -> Solver:
    """A solver backed by real models via the native adapter. Tasks run
    independently (no cross-task learning) so the number is a clean baseline."""

    def solve(prompt: str, workspace: str) -> TaskResult:
        adapters = native_adapters(workspace=workspace, model=model, base_url=base_url)
        frontier = (
            NativeLLM(model=frontier_model, api_key=adapters.llm.api_key, base_url=base_url)
            if frontier_model
            else None
        )
        return run_task(
            prompt,
            adapters,
            workspace=workspace,
            config=Config(max_iterations=max_iterations),
            frontier=frontier,
        )

    return solve


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tack-bench", description="Tack baseline task set (A11).")
    p.add_argument("--model", default="gpt-4o-mini", help="cheap default model id")
    p.add_argument("--frontier-model", default=None, help="optional escalation model id")
    p.add_argument("--base-url", default="https://api.openai.com/v1")
    p.add_argument("--max-iterations", type=int, default=25)
    args = p.parse_args(argv)

    probe = native_adapters(workspace=".", model=args.model, base_url=args.base_url)
    if probe.llm.api_key is None:
        print("error: no API key found. Set OPENAI_API_KEY (or TACK_API_KEY).", file=sys.stderr)
        return 2

    solver = native_solver(
        model=args.model,
        frontier_model=args.frontier_model,
        base_url=args.base_url,
        max_iterations=args.max_iterations,
    )
    report = run_bench(TASKS, solver)
    print(report.render())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
