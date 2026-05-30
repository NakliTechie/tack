"""A6 — the core loop: 6-phase ReAct, environment-agnostic.

    pre-check/compact → think → self-critique → act → execute → post-process

The public entry point is :func:`run_task` — a *function*, not a REPL — so the
future MCP ``ask_agent`` surface (external agents firing tasks at Tack) is a thin
wrapper, not a rewrite. The loop touches the world only through the ``Adapters``
bundle; nothing here knows whether it's native or in a browser VM.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

from tack.adapters.base import Adapters, Message
from tack.core.context import Context, ContextConfig
from tack.core.prompts import build_system_prompt
from tack.core.safety import DoomLoopDetector, GitStepper, is_dangerous
from tack.core.tools import Tools
from tack.core.verify import discover_verify_command, run_verification

_FENCE = re.compile(r"```(?:[a-zA-Z0-9_]*)\n(.*?)```", re.DOTALL)


def parse_action(text: str) -> dict | None:
    """Extract the last fenced block that parses as a JSON object with a ``tool``
    key. Forgiving about the language tag (```action / ```json / bare ```)."""
    for block in reversed(_FENCE.findall(text)):
        try:
            obj = json.loads(block.strip())
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "tool" in obj:
            return obj
    return None


@dataclass
class Config:
    max_iterations: int = 25
    verify_command: str | None = None  # explicit override; else discovered
    verify_each_turn: bool = True
    doom_window: int = 3
    dangerous_command_flag: bool = False  # OFF by default — sandbox-trust
    git_per_step: bool = True
    bash_timeout: float | None = 60.0
    compact_threshold_tokens: int = 12000
    keep_recent_turns: int = 6
    model_opts: dict = field(default_factory=lambda: {"temperature": 0})


@dataclass
class TaskResult:
    success: bool
    stop_reason: str
    turns: int
    verify_command: str | None
    summary: str | None = None
    final_head: str | None = None
    transcript: list[dict] = field(default_factory=list)


def run_task(
    task: str,
    adapters: Adapters,
    *,
    workspace: str = ".",
    config: Config | None = None,
) -> TaskResult:
    """Drive ``task`` to a passing verification command, or stop and report why.

    Stop reasons: ``verified`` (success) · ``model_finished`` (no verify command
    available) · ``iteration_cap`` · ``doom_loop`` · ``cancelled``.
    """
    config = config or Config()
    llm, control, fs = adapters.llm, adapters.control, adapters.execfs

    tools = Tools(fs, bash_timeout=config.bash_timeout)
    detector = DoomLoopDetector(config.doom_window)
    stepper = GitStepper(fs)
    if config.git_per_step:
        stepper.ensure_repo()

    verify_cmd = discover_verify_command(fs, explicit=config.verify_command)
    system_prompt = build_system_prompt(os.path.abspath(workspace), verify_cmd)
    ctx = Context(
        fs,
        llm,
        system_prompt=system_prompt,
        config=ContextConfig(config.compact_threshold_tokens, config.keep_recent_turns),
    )

    history: list[Message] = [Message(role="user", content=f"Task: {task}")]
    transcript: list[dict] = []
    turn = 0

    def done(success: bool, reason: str, summary: str | None = None) -> TaskResult:
        return TaskResult(
            success=success,
            stop_reason=reason,
            turns=turn,
            verify_command=verify_cmd,
            summary=summary,
            final_head=stepper.head() if config.git_per_step else None,
            transcript=transcript,
        )

    for turn in range(1, config.max_iterations + 1):
        # PHASE 1 — pre-check / compact
        if control.is_cancelled():
            return done(False, "cancelled")
        injected = control.take_injected_task()
        if injected:
            history.append(Message(role="user", content=f"[injected task] {injected}"))
        history = ctx.maybe_compact(history)

        # PHASE 2 — think
        reply = llm.complete(ctx.system_messages() + history, **config.model_opts).content
        history.append(Message(role="assistant", content=reply))
        action = parse_action(reply)
        entry: dict = {"turn": turn, "action": action}

        # PHASE 3 — self-critique (programmatic, before executing anything)
        if action is None:
            detector.record("noaction", False, reply[:200])
            history.append(
                Message(
                    role="user",
                    content="No action found. Reply with reasoning, then EXACTLY ONE "
                    "```action {json}``` block.",
                )
            )
            entry["critique"] = "no-action"
            transcript.append(entry)
            if detector.is_doomed():
                return done(False, "doom_loop")
            continue

        tool = action.get("tool")
        if tool == "finish":
            summary = action.get("summary", "")
            if verify_cmd:
                outcome = run_verification(fs, verify_cmd)
                entry["verify_passed"] = outcome.passed
                transcript.append(entry)
                if outcome.passed:
                    return done(True, "verified", summary)
                history.append(Message(role="user", content=f"Not done yet — {outcome.feedback}"))
                continue
            transcript.append(entry)
            return done(True, "model_finished", summary)

        if config.dangerous_command_flag and tool == "bash":
            danger = is_dangerous(action.get("cmd", ""))
            if danger:
                history.append(
                    Message(
                        role="user",
                        content=f"[blocked] refusing dangerous command ({danger}). "
                        "Take a safer path.",
                    )
                )
                entry["critique"] = f"blocked:{danger}"
                transcript.append(entry)
                continue

        # PHASE 4 + 5 — act + execute
        tr = tools.dispatch(tool, action)
        history.append(Message(role="user", content=f"[tool:{tool}]\n{tr.feedback}"))
        detector.record(tr.signature, tr.ok, tr.feedback)
        entry["tool_ok"] = tr.ok

        # PHASE 6 — post-process
        if config.git_per_step:
            entry["head"] = stepper.commit(f"tack turn {turn}: {tool}")
        if config.verify_each_turn and verify_cmd:
            outcome = run_verification(fs, verify_cmd)
            history.append(Message(role="user", content=outcome.feedback))
            entry["verify_passed"] = outcome.passed
            if outcome.passed:
                transcript.append(entry)
                return done(True, "verified")
        transcript.append(entry)
        if detector.is_doomed():
            return done(False, "doom_loop")

    return done(False, "iteration_cap")
