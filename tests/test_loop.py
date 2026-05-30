"""A6 — the loop: action parsing, control, safety/economic stops, injection."""

from tack.core.loop import Config, parse_action, run_task


def test_parse_action_picks_last_valid_block():
    text = (
        '```action\n{"tool":"read","path":"a"}\n```\n'
        "then I reconsider\n"
        '```action\n{"tool":"bash","cmd":"ls"}\n```'
    )
    assert parse_action(text) == {"tool": "bash", "cmd": "ls"}


def test_parse_action_none_when_absent():
    assert parse_action("no fenced action here") is None


def test_parse_action_ignores_non_action_json():
    assert parse_action('```json\n{"not_a_tool": 1}\n```') is None


def test_finish_without_verify_is_trusted(tmp_path, scripted, act):
    a = scripted(["thinking", act("finish", summary="done")])
    res = run_task("noop", a, workspace=str(tmp_path), config=Config(git_per_step=False))
    assert res.success
    assert res.stop_reason == "model_finished"
    assert res.summary == "done"


def test_cancelled_stops_immediately(tmp_path, scripted, act):
    a = scripted([act("bash", cmd="echo hi")])
    a.control.cancel()
    res = run_task("x", a, workspace=str(tmp_path), config=Config(git_per_step=False))
    assert not res.success
    assert res.stop_reason == "cancelled"


def test_iteration_cap(tmp_path, scripted, act):
    a = scripted([act("bash", cmd="echo working")])
    res = run_task(
        "x",
        a,
        workspace=str(tmp_path),
        config=Config(max_iterations=3, git_per_step=False, doom_window=99),
    )
    assert not res.success
    assert res.stop_reason == "iteration_cap"
    assert res.turns == 3


def test_doom_loop_stops_early(tmp_path, scripted, act):
    a = scripted([act("bash", cmd="false")])  # same failing action forever
    res = run_task(
        "x",
        a,
        workspace=str(tmp_path),
        config=Config(max_iterations=10, git_per_step=False, doom_window=3),
    )
    assert not res.success
    assert res.stop_reason == "doom_loop"
    assert res.turns == 3  # stopped well before the cap — the economic win


def test_dangerous_command_blocked_when_flag_on(tmp_path, scripted, act):
    a = scripted([act("bash", cmd="rm -rf /"), act("finish", summary="took a safer path")])
    res = run_task(
        "x",
        a,
        workspace=str(tmp_path),
        config=Config(git_per_step=False, dangerous_command_flag=True),
    )
    assert res.success  # the rm was blocked, not executed; the model then finished
    assert res.stop_reason == "model_finished"


def test_injected_task_reaches_the_model(tmp_path, scripted, act):
    a = scripted([act("finish", summary="ok")])
    a.control.inject_task("also handle the edge case")
    run_task("base task", a, workspace=str(tmp_path), config=Config(git_per_step=False))
    assert any(
        "also handle the edge case" in m["content"] for msgs in a.llm.seen for m in msgs
    )
