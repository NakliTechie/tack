"""A9 — safety & economics: the "don't let it go insane (or broke)" layer.

These are independent guards, all pure agent-side software:

* **iteration cap** — a hard ceiling on turns (in the loop, not here).
* **doom-loop detection** — same action, or same error, N times → stop. On a
  cheap model this is *economic*, not just safety: a doom-loop can cost more
  than one frontier call, so "cheap" is only cheap if the loop self-terminates.
* **dangerous-command flag** — pattern-match destructive shell commands. OFF by
  default (sandbox-trust; per-action gates are fatigue theater).
* **git-per-step** — every step is a commit; a bad step is ``git reset --hard``.
"""

from __future__ import annotations

import re
import shlex
from collections import deque
from dataclasses import dataclass

from tack.adapters.base import ExecFS

# (regex, human description) — matched against bash commands when the flag is on.
DANGEROUS_PATTERNS: list[tuple[str, str]] = [
    (r"\brm\s+-[a-z]*r[a-z]*f|\brm\s+-[a-z]*f[a-z]*r", "recursive force remove"),
    (r"\brm\s+-[a-z]*r[a-z]*\s+/(?:\s|$)", "remove of /"),
    (r"\bmkfs\b", "filesystem format"),
    (r"\bdd\b\s+.*\bof=/dev/", "raw write to a device"),
    (r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", "fork bomb"),
    (r"\bgit\s+clean\s+-[a-z]*f", "git working-tree wipe"),
    (r">\s*/dev/sd[a-z]", "overwrite of a disk device"),
]


def is_dangerous(cmd: str) -> str | None:
    """Return a description if the command matches a destructive pattern, else None."""
    for pattern, desc in DANGEROUS_PATTERNS:
        if re.search(pattern, cmd):
            return desc
    return None


@dataclass
class SafetyConfig:
    max_iterations: int = 25
    doom_window: int = 3
    dangerous_command_flag: bool = False  # OFF by default — sandbox-trust
    git_per_step: bool = True


class DoomLoopDetector:
    """Stops when the agent is stuck: the last ``window`` actions are identical,
    or the last ``window`` failures share the same error."""

    def __init__(self, window: int = 3):
        self.window = window
        self._actions: deque[str] = deque(maxlen=window)
        self._errors: deque[str] = deque(maxlen=window)

    def record(self, signature: str, ok: bool, feedback: str = "") -> None:
        self._actions.append(signature)
        self._errors.append("" if ok else feedback.strip())

    def is_doomed(self) -> bool:
        if len(self._actions) < self.window:
            return False
        if len(set(self._actions)) == 1:  # same action N times
            return True
        errs = [e for e in self._errors if e]
        return len(errs) == self.window and len(set(errs)) == 1  # same error N times

    def reason(self) -> str:
        """A short signature of why it stalled — recorded as an anti-pattern."""
        if self._actions and len(set(self._actions)) == 1:
            return f"repeated action: {self._actions[-1]}"
        errs = [e for e in self._errors if e]
        if errs:
            return f"repeated error: {errs[-1][:120]}"
        return "stalled"


class GitStepper:
    """Per-step git snapshots over the exec seam. Real git in every adapter;
    zero new browser surface. Undo = reset to a captured SHA."""

    def __init__(self, fs: ExecFS):
        self.fs = fs

    def ensure_repo(self) -> None:
        if self.fs.run("git rev-parse --git-dir").exit_code != 0:
            self.fs.run("git init -q")
        # local identity so commits work in fresh/CI workspaces
        self.fs.run("git config user.email tack@local")
        self.fs.run("git config user.name Tack")
        if not self.head():
            self.fs.run("git add -A")
            self.fs.run("git commit -q -m 'tack: baseline' --allow-empty")

    def head(self) -> str | None:
        r = self.fs.run("git rev-parse HEAD")
        return r.stdout.strip() if r.exit_code == 0 else None

    def commit(self, message: str) -> str | None:
        self.fs.run("git add -A")
        if not self.fs.run("git status --porcelain").stdout.strip():
            return self.head()  # nothing changed this step — don't make an empty commit
        self.fs.run(f"git commit -q -m {shlex.quote(message)}")
        return self.head()

    def revert_to(self, sha: str) -> None:
        self.fs.run(f"git reset --hard {shlex.quote(sha)}")
