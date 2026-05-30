"""A7 — the context engine.

Filesystem-as-memory: the agent's working memory lives in files, not just the
window. Each turn the loop re-reads the plan and re-injects project conventions,
so a fresh window boots already oriented — the primitive that turns single-turn
into multi-session.

* ``.tack/plan.md``  — goal → ordered steps, re-read each turn, the agent edits it.
* ``AGENTS.md``      — project conventions, injected at session start.
* progressive compaction — when the window fills, summarise the oldest turns
  (via the LLM seam) so the API never errors on context.
"""

from __future__ import annotations

from dataclasses import dataclass

from tack.adapters.base import LLMTransport, Message
from tack.core.util import estimate_tokens, truncate
from tack.errors import TackError

PLAN_FILE = ".tack/plan.md"
AGENTS_FILE = "AGENTS.md"


@dataclass
class ContextConfig:
    compact_threshold_tokens: int = 12000
    keep_recent_turns: int = 6


class Context:
    """Assembles the messages sent each turn and keeps the window bounded."""

    def __init__(
        self,
        fs,
        llm: LLMTransport,
        *,
        system_prompt: str,
        config: ContextConfig | None = None,
    ):
        self.fs = fs
        self.llm = llm
        self.system_prompt = system_prompt
        self.config = config or ContextConfig()

    # -- filesystem-as-memory ---------------------------------------------
    def _read_or_empty(self, path: str) -> str:
        try:
            return self.fs.read(path)
        except (FileNotFoundError, TackError, OSError):
            return ""

    def read_plan(self) -> str:
        return self._read_or_empty(PLAN_FILE)

    def write_plan(self, text: str) -> None:
        self.fs.write(PLAN_FILE, text)

    def read_conventions(self) -> str:
        return self._read_or_empty(AGENTS_FILE)

    # -- message assembly --------------------------------------------------
    def system_messages(self) -> list[Message]:
        """The persistent head of every request: harness prompt + conventions +
        the current plan. Rebuilt each turn so plan/convention edits take effect."""
        msgs: list[Message] = [Message(role="system", content=self.system_prompt)]
        conventions = self.read_conventions().strip()
        if conventions:
            msgs.append(
                Message(role="system", content=f"# Project conventions (AGENTS.md)\n{conventions}")
            )
        plan = self.read_plan().strip()
        if plan:
            msgs.append(Message(role="system", content=f"# Current plan (.tack/plan.md)\n{plan}"))
        return msgs

    # -- progressive compaction -------------------------------------------
    def estimate(self, history: list[Message]) -> int:
        return estimate_tokens("".join(m["content"] for m in history))

    def maybe_compact(self, history: list[Message]) -> list[Message]:
        """If the running history is over budget, replace its oldest turns with a
        single LLM-written summary, keeping the most recent turns verbatim."""
        if self.estimate(history) <= self.config.compact_threshold_tokens:
            return history
        keep = self.config.keep_recent_turns
        if len(history) <= keep:
            return history  # already at the floor; nothing safe to drop
        head, tail = history[:-keep], history[-keep:]
        summary = self._summarize(head)
        compacted = Message(
            role="user", content=f"[earlier progress, compacted]\n{summary}"
        )
        return [compacted, *tail]

    def _summarize(self, messages: list[Message]) -> str:
        convo = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
        prompt = [
            Message(
                role="system",
                content=(
                    "Summarise the progress so far in <=200 words: the goal, what was "
                    "tried, what worked, what failed and why, and the current state. Be "
                    "concrete (file names, errors). This replaces the raw history."
                ),
            ),
            Message(role="user", content=truncate(convo, 8000)),
        ]
        return self.llm.complete(prompt).content
