"""C1/C3 — frontier escalation + the legible trace (v1.2)."""

from tack.core.loop import Config, run_task
from tack.core.trace import render_trace

BUGGY = "def add(a, b):\n    return a - b\n"
TEST = "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"


def test_stuck_cheap_run_escalates_and_completes(tmp_path, make_llm, make_adapters, act):
    """The v1.2 gate: a cheap model doom-loops, the loop escalates to the frontier
    model, and the run completes."""
    (tmp_path / "calc.py").write_text(BUGGY)
    (tmp_path / "test_calc.py").write_text(TEST)

    cheap = make_llm([act("edit", path="calc.py", old="DOES NOT EXIST", new="x")])  # always fails
    frontier = make_llm([act("edit", path="calc.py", old="return a - b", new="return a + b")])
    adapters = make_adapters(cheap)

    res = run_task(
        "Make the failing test pass.",
        adapters,
        workspace=str(tmp_path),
        config=Config(doom_window=3, max_iterations=10),
        frontier=frontier,
    )

    assert res.escalated is True
    assert res.escalation_turn == 3  # after 3 identical failures on the cheap model
    assert res.success is True
    assert res.stop_reason == "verified"
    assert len(cheap.seen) == 3  # cheap ran until it stalled
    assert len(frontier.seen) >= 1  # frontier took over and finished
    assert "return a + b" in (tmp_path / "calc.py").read_text()


def test_no_frontier_means_doom_still_stops(tmp_path, make_llm, make_adapters, act):
    adapters = make_adapters(make_llm([act("bash", cmd="false")]))
    res = run_task(
        "x",
        adapters,
        workspace=str(tmp_path),
        config=Config(doom_window=3, git_per_step=False),
    )
    assert res.escalated is False
    assert res.stop_reason == "doom_loop"


def test_judgment_task_starts_on_frontier(tmp_path, make_llm, make_adapters, act):
    """No verify command → no ground truth to iterate against → judgment task →
    start on the frontier model (cheap-model parity doesn't hold)."""
    cheap = make_llm([act("finish", summary="cheap")])
    frontier = make_llm([act("finish", summary="frontier handled the judgment call")])
    adapters = make_adapters(cheap)

    res = run_task(
        "Is this architecture sound?",
        adapters,
        workspace=str(tmp_path),
        config=Config(git_per_step=False),
        frontier=frontier,
    )

    assert res.escalated is True
    assert len(frontier.seen) >= 1  # frontier did the work
    assert len(cheap.seen) == 0  # cheap was never asked
    assert res.success is True


def test_render_trace_is_legible(tmp_path, make_llm, make_adapters, act):
    (tmp_path / "calc.py").write_text(BUGGY)
    (tmp_path / "test_calc.py").write_text(TEST)
    cheap = make_llm([act("edit", path="calc.py", old="NOPE", new="x")])
    frontier = make_llm([act("edit", path="calc.py", old="return a - b", new="return a + b")])
    res = run_task(
        "fix it",
        make_adapters(cheap),
        workspace=str(tmp_path),
        config=Config(doom_window=3, max_iterations=10),
        frontier=frontier,
    )
    trace = render_trace(res)
    assert "escalated to the frontier model" in trace
    assert "[cheap" in trace
    assert "[frontier" in trace
    assert "verify=True" in trace
    assert trace.count("turn") >= 4  # header + per-turn rows
