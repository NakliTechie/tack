"""C2 — observability: render a run's trace legibly.

The loop already records a structured per-turn transcript (model, action,
tool_ok, verify, git head). This turns it into one readable block — step / model
/ exit-state / iteration / per-step commit — so a stuck-then-escalated run is
inspectable at a glance (the v1.2 gate asks for a legible trace).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tack.core.loop import TaskResult


def render_trace(result: TaskResult) -> str:
    lines = [
        f"task trace — stop={result.stop_reason} success={result.success} "
        f"turns={result.turns} verify={result.verify_command}"
    ]
    if result.escalated:
        where = (
            "from the start"
            if result.escalation_turn in (0, None)
            else f"at turn {result.escalation_turn}"
        )
        lines.append(f"  ** escalated to the frontier model {where}")

    for e in result.transcript:
        action = e.get("action") or {}
        bits = [f"  turn {e['turn']:>2}"]
        if "model" in e:
            bits.append(f"[{e['model']:<8}]")
        bits.append(f"{(action.get('tool') or '—'):<7}")
        if "tool_ok" in e:
            bits.append(f"ok={e['tool_ok']}")
        if "verify_passed" in e:
            bits.append(f"verify={e['verify_passed']}")
        if e.get("new_tools"):
            bits.append(f"+tools={e['new_tools']}")
        if e.get("critique"):
            bits.append(f"({e['critique']})")
        if e.get("head"):
            bits.append(f"@{e['head'][:8]}")
        lines.append(" ".join(bits))

    if result.promoted_tools:
        lines.append(f"  promoted tools: {', '.join(result.promoted_tools)}")
    return "\n".join(lines)
