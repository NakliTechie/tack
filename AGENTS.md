# AGENTS.md — Tack conventions

Conventions for any agent (a human, or Tack dogfooding itself) working in this
repo. Tack's context engine injects this file at session start.

## What this is
Tack is a portable coding-agent harness: an environment-agnostic core
(`src/tack/core/`) that speaks ONLY to three adapter seams
(`src/tack/adapters/base.py`) — LLM transport, control, execution+FS.

## Non-negotiables (from the locked decisions)
- **Adapters only.** No transport detail (HTTPS, serial, 9P, file-bridge,
  subprocess) may appear in `tack.core`. If the core needs env-specific code,
  the seam is wrong — fix the seam, not the core.
- **Exactly 4 tools** — read · write · edit · bash. No fifth; bash composes the
  rest, the agent self-extends (v1.1) into `.tack/bin/`.
- **Sandbox-trust.** No per-action approval gates. Dangerous-command flag is
  opt-in, OFF by default.
- **Git-per-step.** Every step commits; undo is `git reset --hard`.
- **Clean-room.** No leaked proprietary source — published techniques only.
- **Core entry is a function, not a REPL** (cheap future MCP `ask_agent`).
- **Keys never enter the VM** (Karkhana-adapter invariant).
- **Build native first, deploy unchanged behind adapters.** One environment
  variable at a time.

## Stack
- Python ≥ 3.11 (matches Karkhana's Alpine + Python 3.11). Dev env via `uv`;
  `.python-version` pins 3.11.
- The core aims for **zero runtime dependencies** (stdlib-first) so it drops
  into the Alpine VM unchanged. Dev-only deps: pytest, ruff.

## Workflow
- `uv sync --extra dev` — create `.venv` and install the package + dev deps.
- `uv run pytest` — run tests. Keep them green.
- `uv run ruff check .` — lint.
- Tack's own state lives in `.tack/` (gitignored).
