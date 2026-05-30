"""Small shared helpers for the core."""

from __future__ import annotations

MAX_FEEDBACK = 4000  # default chars of tool/verify output folded back into context


def truncate(text: str, limit: int = MAX_FEEDBACK) -> str:
    """Keep the head and tail, drop the middle — the signal usually lives at the
    ends (the command and its final error). ACI discipline: don't let one noisy
    blob rot the window."""
    if len(text) <= limit:
        return text
    keep = limit // 2
    dropped = len(text) - 2 * keep
    return f"{text[:keep]}\n... [tack truncated {dropped} chars] ...\n{text[-keep:]}"


def estimate_tokens(text: str) -> int:
    """Cheap, dependency-free token estimate (~4 chars/token). Good enough to
    drive the compaction trigger without pulling in a tokenizer."""
    return len(text) // 4
