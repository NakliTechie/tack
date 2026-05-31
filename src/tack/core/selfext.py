"""B1 — self-extension: the agent's own tools, with promotion-via-verification.

Locked decisions: exactly 4 built-in tools, no 5th (Handoff §3.2); self-extension
over a plugin ecosystem (Vision §4.2). So this is NOT a new tool — the agent
writes a small shell script to ``.tack/bin/`` with ``write`` + ``bash`` and calls
it like any command. This registry only *tracks* those scripts.

The untrusted author is the agent itself (Vision §4.3): a cheap model can write a
subtly-broken tool and lean on it for 40 turns. So a freshly written tool is
**provisional**; it is **promoted** to *verified* only once it has been used in a
turn that reached ground-truth green. That promotion is the code review the human
isn't doing. A rewritten tool drops back to provisional — trust is re-earned.

State persists in ``.tack/tools.json`` (workspace-local → portable across adapters).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass

from tack.errors import TackError

BIN_DIR = ".tack/bin"
REGISTRY_FILE = ".tack/tools.json"


@dataclass
class LearnedTool:
    name: str
    state: str  # "provisional" | "verified"
    created_turn: int
    used: int = 0
    digest: str = ""


class ToolRegistry:
    """Tracks self-written tools in ``.tack/bin/`` and their trust state."""

    def __init__(self, fs):
        self.fs = fs
        self.tools: dict[str, LearnedTool] = self._load()

    # -- persistence -------------------------------------------------------
    def _load(self) -> dict[str, LearnedTool]:
        try:
            raw = json.loads(self.fs.read(REGISTRY_FILE))
        except (FileNotFoundError, TackError, OSError, json.JSONDecodeError):
            return {}
        return {name: LearnedTool(**d) for name, d in raw.items()}

    def _save(self) -> None:
        data = {name: asdict(t) for name, t in self.tools.items()}
        self.fs.write(REGISTRY_FILE, json.dumps(data, indent=2, sort_keys=True))

    # -- inspection of .tack/bin ------------------------------------------
    def _list_bin(self) -> list[str]:
        out = self.fs.run(f"ls -1 {BIN_DIR} 2>/dev/null").stdout
        return [ln.strip() for ln in out.splitlines() if ln.strip()]

    def _digest(self, name: str) -> str:
        try:
            content = self.fs.read(f"{BIN_DIR}/{name}")
        except (FileNotFoundError, TackError, OSError):
            return ""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]

    # -- lifecycle ---------------------------------------------------------
    def scan(self, turn: int) -> list[str]:
        """Register any new ``.tack/bin/`` files as provisional; a rewritten tool
        drops back to provisional. Returns the newly discovered names."""
        new: list[str] = []
        changed = False
        for name in self._list_bin():
            digest = self._digest(name)
            existing = self.tools.get(name)
            if existing is None:
                self.tools[name] = LearnedTool(
                    name=name, state="provisional", created_turn=turn, digest=digest
                )
                new.append(name)
                changed = True
            elif digest and digest != existing.digest:
                existing.state = "provisional"
                existing.digest = digest
                changed = True
        if changed:
            self._save()
        return new

    def note_uses(self, cmd: str) -> list[str]:
        """Which registered tools does this bash command invoke? Bumps their use
        count (substring on a word boundary — tool names are distinctive)."""
        used: list[str] = []
        for name in self.tools:
            if re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", cmd):
                self.tools[name].used += 1
                used.append(name)
        if used:
            self._save()
        return used

    def promote_used(self) -> list[str]:
        """On ground-truth green: promote every provisional tool that was used."""
        promoted = [
            t.name for t in self.tools.values() if t.state == "provisional" and t.used > 0
        ]
        for name in promoted:
            self.tools[name].state = "verified"
        if promoted:
            self._save()
        return promoted

    def summary(self) -> str:
        """One injectable block describing the current self-written toolset."""
        if not self.tools:
            return ""
        lines = [
            f"- {t.name} [{t.state}]"
            for t in sorted(self.tools.values(), key=lambda x: x.name)
        ]
        return (
            "Self-written tools in .tack/bin/ "
            "(provisional = verify its output against ground truth before you rely on it):\n"
            + "\n".join(lines)
        )
