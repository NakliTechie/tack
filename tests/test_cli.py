"""CLI plumbing — argument parsing and the no-key guard (keyless tests)."""

import sys

from tack import cli
from tack.cli import _build_build_parser, _build_task_parser, build_parser, main


def test_parser_defaults():
    args = _build_task_parser().parse_args(["fix the bug"])
    assert args.task == "fix the bug"
    assert args.workspace == "."
    assert args.model == "gpt-4o-mini"
    assert args.max_iterations == 25
    assert args.dangerous_command_guard is False
    assert args.no_git is False
    assert args.verify is None


def test_parser_flags():
    # fmt: off
    args = _build_task_parser().parse_args([
        "--workspace", "/tmp/x", "--max-iterations", "9", "--no-git",
        "--verify", "pytest", "do it",
    ])
    # fmt: on
    assert args.workspace == "/tmp/x"
    assert args.max_iterations == 9
    assert args.no_git is True
    assert args.verify == "pytest"
    assert args.task == "do it"


def test_verify_available_on_both_parsers():
    """`--verify` is shared: single-task mode had it, then lost it to the build split."""
    task = _build_task_parser().parse_args(["--verify", "pytest -q", "do it"])
    assert task.verify == "pytest -q"

    build = _build_build_parser().parse_args(["--verify", "pytest -q", "specs/"])
    assert build.verify == "pytest -q"
    assert build.spec_dir == "specs/"
    assert build.resume is False


def test_build_parser_public_alias():
    """`build_parser` is the pre-director public name — external callers import it."""
    assert build_parser is _build_task_parser
    assert build_parser().parse_args(["do it"]).task == "do it"


def test_build_subcommand_routes_when_argv_is_none(monkeypatch):
    """The console script calls main() with no args — `tack build` must still route.

    Regression: main() checked `argv[0] == "build"` before resolving argv from
    sys.argv, so the entry point sent `tack build specs/` to the task parser.
    """
    seen: list[list[str]] = []

    def fake_build(argv: list[str]) -> int:
        seen.append(argv)
        return 0

    monkeypatch.setattr(cli, "_run_build_cmd", fake_build)
    monkeypatch.setattr(sys, "argv", ["tack", "build", "specs/", "--resume"])

    assert main() == 0
    assert seen == [["specs/", "--resume"]]


def test_build_subcommand_routes_with_explicit_argv(monkeypatch):
    """Library callers pass argv explicitly — this path already worked; fence it."""
    seen: list[list[str]] = []

    def fake_build(argv: list[str]) -> int:
        seen.append(argv)
        return 0

    monkeypatch.setattr(cli, "_run_build_cmd", fake_build)

    assert main(["build", "specs/"]) == 0
    assert seen == [["specs/"]]


def test_main_errors_without_key(monkeypatch, capsys):
    for var in ("OPENAI_API_KEY", "TACK_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    code = main(["do something"])
    assert code == 2
    assert "no API key" in capsys.readouterr().err
