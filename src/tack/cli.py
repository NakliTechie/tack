"""The command-line agent face.

The core entry is a *function* (:func:`tack.run_task`); this CLI is just one
caller of it — exactly as the future MCP ``ask_agent`` surface will be another.
Nothing here is load-bearing; the loop is fully usable without it.

    tack "make the failing test pass"
    tack --workspace ../repo --model gpt-4o-mini "fix the parser bug"
    OPENAI_API_KEY=sk-... tack --max-iterations 40 "implement the TODO in api.py"
"""

from __future__ import annotations

import argparse
import sys

from tack.adapters.native import native_adapters
from tack.core.loop import Config, run_task


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tack", description="Portable coding-agent harness.")
    p.add_argument("task", help="the task to drive to passing checks")
    p.add_argument("--workspace", default=".", help="workspace directory (default: .)")
    p.add_argument("--model", default="gpt-4o-mini", help="model id (default: gpt-4o-mini)")
    p.add_argument(
        "--base-url", default="https://api.openai.com/v1", help="OpenAI-compatible base URL"
    )
    p.add_argument("--verify", default=None, help="explicit verification command (else discovered)")
    p.add_argument("--max-iterations", type=int, default=25, help="hard turn ceiling (default: 25)")
    p.add_argument(
        "--dangerous-command-guard",
        action="store_true",
        help="block destructive shell commands (OFF by default — sandbox-trust)",
    )
    p.add_argument("--no-git", action="store_true", help="disable git-per-step snapshots")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    adapters = native_adapters(
        workspace=args.workspace, model=args.model, base_url=args.base_url
    )
    if adapters.llm.api_key is None:
        print(
            "error: no API key found. Set OPENAI_API_KEY (or TACK_API_KEY).",
            file=sys.stderr,
        )
        return 2

    config = Config(
        verify_command=args.verify,
        max_iterations=args.max_iterations,
        dangerous_command_flag=args.dangerous_command_guard,
        git_per_step=not args.no_git,
    )
    res = run_task(args.task, adapters, workspace=args.workspace, config=config)

    for e in res.transcript:
        action = e.get("action") or {}
        tool = (action.get("tool") or "—").ljust(7)
        print(f"  turn {e['turn']}: {tool}  ok={e.get('tool_ok')}  verify={e.get('verify_passed')}")
    print(f"\n[tack] {res.stop_reason} after {res.turns} turn(s) — success={res.success}")
    if res.summary:
        print(f"[tack] {res.summary}")
    return 0 if res.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
