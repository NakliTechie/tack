"""B2/B3 — local two-layer learning. No sharing transport (Vision §4.4).

Two layers, both on-device:

* **User-level (per-workspace)** — ``.tack/playbook.md`` lives in the workspace and
  is read/written through the ExecFS seam (handled in the context engine). It
  travels with the folder.
* **System-level (per-device)** — this :class:`LearningStore`. Cross-workspace
  memory that *flattens the curve*: a new workspace boots already knowing common
  moves and the anti-patterns that caused doom-loops. ``prior_knowledge()`` is
  injected at session start; ``record_*`` persist what a run learned.

The store is supplied per-environment (native: ``~/.tack``; Karkhana at D1: the
VM's persistent home), which is why it is an interface, not baked into the core.
It is **optional** — the core runs fine without it (:class:`NullLearningStore`).
There is deliberately no server, telemetry, or sharing transport; public
dissemination is manual operator curation (Vision §5).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LearningStore(Protocol):
    def prior_knowledge(self) -> str:
        """Text injected at session start — device playbook + known anti-patterns."""
        ...

    def record_success(self, note: str) -> None:
        """Persist something that worked, for future workspaces."""
        ...

    def record_anti_pattern(self, signature: str, note: str) -> None:
        """Persist a pattern that caused a stall, so it can be avoided next time."""
        ...


class NullLearningStore:
    """The no-op default: no cross-workspace memory."""

    def prior_knowledge(self) -> str:
        return ""

    def record_success(self, note: str) -> None:
        pass

    def record_anti_pattern(self, signature: str, note: str) -> None:
        pass
