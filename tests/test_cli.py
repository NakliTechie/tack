"""CLI plumbing — argument parsing and the no-key guard (keyless tests)."""

from tack.cli import _build_task_parser, main


def test_parser_defaults():
    args = _build_task_parser().parse_args(["fix the bug"])
    assert args.task == "fix the bug"
    assert args.workspace == "."
    assert args.model == "gpt-4o-mini"
    assert args.max_iterations == 25
    assert args.dangerous_command_guard is False
    assert args.no_git is False


def test_parser_flags():
    args = _build_task_parser().parse_args(
        ["--workspace", "/tmp/x", "--max-iterations", "9", "--no-git", "do it"]
    )
    assert args.workspace == "/tmp/x"
    assert args.max_iterations == 9
    assert args.no_git is True
    assert args.task == "do it"


def test_main_errors_without_key(monkeypatch, capsys):
    for var in ("OPENAI_API_KEY", "TACK_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    code = main(["do something"])
    assert code == 2
    assert "no API key" in capsys.readouterr().err
