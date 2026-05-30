"""A8 — verification: the closed loop's arbiter.

Discover the project's own check command, run it through the exec seam, and turn
its exit code into a continue/stop signal. exit 0 advances; non-zero feeds the
actual error text back into the next turn. *That feedback is the loop.*

Discovery order (Handoff §3.4): explicit override → ``.tack/verify`` file →
infer from project markers → ``None`` (caller decides; the loop falls back to
trusting the model's ``finish``).
"""

from __future__ import annotations

from dataclasses import dataclass

from tack.adapters.base import ExecFS, ExecResult
from tack.core.util import truncate
from tack.errors import TackError

VERIFY_FILE = ".tack/verify"


@dataclass
class VerifyOutcome:
    passed: bool
    command: str
    result: ExecResult
    feedback: str


def _probe(fs: ExecFS, cmd: str) -> bool:
    return fs.run(cmd).exit_code == 0


def discover_verify_command(fs: ExecFS, *, explicit: str | None = None) -> str | None:
    """Find the command whose exit code defines 'done' for this workspace."""
    if explicit:
        return explicit
    # 1. an operator-/agent-written .tack/verify wins
    try:
        text = fs.read(VERIFY_FILE).strip()
        if text:
            return text.splitlines()[0].strip()
    except (FileNotFoundError, TackError, OSError):
        pass
    # 2. infer from common project markers
    if _probe(fs, "ls tests >/dev/null 2>&1 || ls test_*.py >/dev/null 2>&1") or _probe(
        fs, "grep -q pytest pyproject.toml setup.cfg tox.ini 2>/dev/null"
    ):
        return "pytest -q"
    if _probe(fs, "[ -f package.json ] && grep -q '\"test\"' package.json"):
        return "npm test --silent"
    if _probe(fs, "[ -f Makefile ] && grep -qE '^test:' Makefile"):
        return "make test"
    # 3. give up — the loop will rely on the model's finish signal
    return None


def run_verification(fs: ExecFS, command: str) -> VerifyOutcome:
    r = fs.run(command)
    if r.exit_code == 0:
        return VerifyOutcome(True, command, r, f"verification passed: `{command}` (exit 0)")
    detail = r.stderr.strip() or r.stdout.strip() or "(no output)"
    feedback = (
        f"verification FAILED: `{command}` exited {r.exit_code}\n{truncate(detail)}"
    )
    return VerifyOutcome(False, command, r, feedback)
