"""The command-line agent face.

The core entry is a *function* (:func:`tack.run_task`); this CLI is just one
caller of it — exactly as the future MCP ``ask_agent`` surface will be another.
Nothing here is load-bearing; the loop is fully usable without it.

    tack "make the failing test pass"
    tack --workspace ../repo --model gpt-4o-mini "fix the parser bug"
    OPENAI_API_KEY=sk-... tack --max-iterations 40 "implement the TODO in api.py"

    tack build specs/                     # multi-phase build from spec docs
    tack build specs/ --resume            # resume from checkpoint
"""

from __future__ import annotations

import argparse
import sys

from tack.adapters.native import FileLearningStore, NativeLLM, native_adapters
from tack.core.loop import Config, run_task
from tack.core.trace import render_trace


def _shared_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--workspace", default=".", help="workspace directory (default: .)")
    p.add_argument(
        "--model", default="gpt-4o-mini", help="cheap default model id (default: gpt-4o-mini)"
    )
    p.add_argument(
        "--frontier-model",
        default=None,
        help="stronger model to escalate to when the cheap model gets stuck",
    )
    p.add_argument(
        "--base-url", default="https://api.openai.com/v1", help="OpenAI-compatible base URL"
    )
    p.add_argument(
        "--verify",
        default=None,
        help="explicit verification command (else discovered); under `build`, the "
        "default for phases that don't set their own",
    )
    p.add_argument("--max-iterations", type=int, default=25, help="hard turn ceiling (default: 25)")
    p.add_argument(
        "--dangerous-command-guard",
        action="store_true",
        help="block destructive shell commands (OFF by default — sandbox-trust)",
    )
    p.add_argument("--no-git", action="store_true", help="disable git-per-step snapshots")
    p.add_argument(
        "--no-learning",
        action="store_true",
        help="disable the per-device learning store (~/.tack or $TACK_HOME)",
    )


def _build_task_parser() -> argparse.ArgumentParser:
    """Parser for ``tack "task"`` (legacy single-task mode)."""
    p = argparse.ArgumentParser(prog="tack", description="Portable coding-agent harness.")
    p.add_argument("task", help="the task to drive to passing checks")
    _shared_args(p)
    return p


# Public name for the single-task parser, kept for external callers that
# imported it before the ``build`` subcommand split the parsers in two.
# (Not to be confused with _build_build_parser, which serves `tack build`.)
build_parser = _build_task_parser


def _build_build_parser() -> argparse.ArgumentParser:
    """Parser for ``tack build <spec-dir>``."""
    p = argparse.ArgumentParser(
        prog="tack build",
        description="Multi-phase build from spec documents",
    )
    p.add_argument("spec_dir", help="directory containing .md specification documents")
    p.add_argument("--resume", action="store_true", help="resume from last checkpoint")
    # --verify comes from _shared_args (declaring it here too is an argparse conflict);
    # for `build` it acts as the default verify command for every phase.
    _shared_args(p)
    return p


def _run_task_cmd(args: argparse.Namespace) -> int:
    adapters = native_adapters(
        workspace=args.workspace, model=args.model, base_url=args.base_url
    )
    if adapters.llm.api_key is None:
        print("error: no API key found. Set OPENAI_API_KEY (or TACK_API_KEY).", file=sys.stderr)
        return 2

    config = Config(
        verify_command=args.verify,
        max_iterations=args.max_iterations,
        dangerous_command_flag=args.dangerous_command_guard,
        git_per_step=not args.no_git,
    )
    learning = None if args.no_learning else FileLearningStore()
    frontier = (
        NativeLLM(model=args.frontier_model, api_key=adapters.llm.api_key, base_url=args.base_url)
        if args.frontier_model
        else None
    )
    res = run_task(
        args.task,
        adapters,
        workspace=args.workspace,
        config=config,
        learning=learning,
        frontier=frontier,
    )

    print(render_trace(res))
    print(f"\n[tack] {res.stop_reason} after {res.turns} turn(s) — success={res.success}")
    if res.summary:
        print(f"[tack] {res.summary}")
    return 0 if res.success else 1


def _run_build_cmd(argv: list[str]) -> int:
    from tack.director import build_from_specs

    args = _build_build_parser().parse_args(argv)
    adapters = native_adapters(
        workspace=args.workspace, model=args.model, base_url=args.base_url
    )
    if adapters.llm.api_key is None:
        print("error: no API key found. Set OPENAI_API_KEY (or TACK_API_KEY).", file=sys.stderr)
        return 2

    results = build_from_specs(
        args.spec_dir,
        adapters,
        workspace=args.workspace,
        config=Config(
            verify_command=args.verify,
            max_iterations=args.max_iterations,
            dangerous_command_flag=args.dangerous_command_guard,
            git_per_step=not args.no_git,
        ),
        resume=args.resume,
        frontier=(
            NativeLLM(model=args.frontier_model, api_key=adapters.llm.api_key, base_url=args.base_url)
            if args.frontier_model
            else None
        ),
    )

    succeeded = sum(1 for r in results if r.status == "completed")
    return 0 if succeeded == len(results) else 1


def main(argv: list[str] | None = None) -> int:
    # Resolve argv *before* the subcommand check: the console-script entry calls
    # main() with no arguments, so leaving argv as None here sends `tack build ...`
    # to the single-task parser — which errors on the spec dir it doesn't know
    # about, making the whole `build` subcommand unreachable from a real shell.
    # Consequence: a single task whose text is literally "build" now has to be
    # run through the library entry, not the CLI.
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] == "build":
        return _run_build_cmd(argv[1:])
    return _run_task_cmd(_build_task_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
