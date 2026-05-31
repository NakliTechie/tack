"""The native adapter — dev box / CI.

Implements the three seams (:mod:`tack.adapters.base`) for a real OS:

    LLM transport   : direct HTTPS, BYOK (OpenAI-compatible chat completions)
    Control         : in-process, thread-safe, optional SIGINT → cancel
    Execution + FS  : subprocess + the real filesystem, workspace-scoped

This is the only place transport detail (HTTPS, subprocess) is allowed to live
for the native environment. The Karkhana adapter (D1) is a sibling file that
swaps the mechanisms without the core noticing.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from tack.adapters.base import Adapters, Completion, ExecResult, Message
from tack.errors import EditError, TransportError, WorkspaceError

# Conventional exit code for "we killed it on a timeout" (matches `timeout(1)`).
TIMEOUT_EXIT = 124


# ==========================================================================
# Seam 3 — Execution + filesystem
# ==========================================================================
class NativeExecFS:
    """subprocess + real FS, scoped to a workspace directory.

    Every path is resolved relative to ``workspace`` and may not escape it.
    ``run`` shells out with the workspace as cwd.
    """

    def __init__(self, workspace: str = "."):
        self.workspace = os.path.realpath(workspace)

    def _resolve(self, path: str) -> str:
        full = os.path.realpath(os.path.join(self.workspace, path))
        if full != self.workspace and not full.startswith(self.workspace + os.sep):
            raise WorkspaceError(f"path escapes workspace: {path!r}")
        return full

    def run(self, cmd: str, *, timeout: float | None = None) -> ExecResult:
        # Never let stale Python bytecode mask a source edit. The loop edits a
        # file and re-runs the check, often within the same second; CPython's
        # .pyc invalidation uses second-resolution mtime, so a same-second edit
        # can be ignored and the agent would doom-loop on already-fixed code.
        # Writing no bytecode removes the trap (a real "edit, re-test, trust the
        # exit code" harness must not be fooled by a cache).
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        try:
            p = subprocess.run(
                cmd,
                shell=True,
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
            return ExecResult(stdout=p.stdout, stderr=p.stderr, exit_code=p.returncode)
        except subprocess.TimeoutExpired as e:
            out = _as_text(e.stdout)
            err = _as_text(e.stderr)
            return ExecResult(
                stdout=out,
                stderr=f"{err}\n[tack] command timed out after {timeout}s".strip(),
                exit_code=TIMEOUT_EXIT,
            )

    def read(self, path: str) -> str:
        with open(self._resolve(path), encoding="utf-8") as f:
            return f.read()

    def write(self, path: str, content: str) -> None:
        full = self._resolve(path)
        parent = os.path.dirname(full)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(content)

    def edit(self, path: str, old: str, new: str) -> None:
        full = self._resolve(path)
        with open(full, encoding="utf-8") as f:
            content = f.read()
        occurrences = content.count(old)
        if occurrences == 0:
            raise EditError(f"edit failed: `old` text not found in {path}")
        if occurrences > 1:
            raise EditError(
                f"edit failed: `old` text appears {occurrences} times in {path}; "
                "include more surrounding context so it matches exactly once"
            )
        with open(full, "w", encoding="utf-8") as f:
            f.write(content.replace(old, new, 1))


def _as_text(maybe: Any) -> str:
    if maybe is None:
        return ""
    if isinstance(maybe, bytes):
        return maybe.decode("utf-8", errors="replace")
    return str(maybe)


# ==========================================================================
# Seam 2 — Control
# ==========================================================================
class NativeControl:
    """Thread-safe in-process control.

    The outward surface (``cancel`` / ``inject_task``) is driven by whatever
    operational wiring the host attaches — a SIGINT handler, a stdin reader, a
    unix socket. The core-facing surface (``is_cancelled`` / ``take_injected_task``)
    is polled by the loop between turns. The core never learns which wiring it is.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cancelled = False
        self._tasks: list[str] = []

    def cancel(self) -> None:
        with self._lock:
            self._cancelled = True

    def inject_task(self, task: str) -> None:
        with self._lock:
            self._tasks.append(task)

    def is_cancelled(self) -> bool:
        with self._lock:
            return self._cancelled

    def take_injected_task(self) -> str | None:
        with self._lock:
            return self._tasks.pop(0) if self._tasks else None

    def install_sigint(self) -> None:
        """Optional: wire Ctrl-C to cooperative cancellation."""
        signal.signal(signal.SIGINT, lambda *_: self.cancel())


# ==========================================================================
# Seam 1 — LLM transport
# ==========================================================================
# Injection point for tests: anything with urlopen's (request) -> context-manager
# shape. Defaults to the real urllib opener.
Opener = Callable[[urllib.request.Request], Any]


class NativeLLM:
    """Direct HTTPS to an OpenAI-compatible ``/chat/completions`` endpoint, BYOK.

    The seam returns plain text (``Completion.content``) — tool-call *parsing*
    lives in the core, not here, so the same loop drives an API brain now and a
    local ``<tool_call>``-emitting brain later (v1.3) with no transport change.
    """

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 120.0,
        opener: Opener | None = None,
    ):
        self.model = model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get(
            "TACK_API_KEY"
        )
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._opener = opener or (lambda req: urllib.request.urlopen(req, timeout=self.timeout))

    def complete(self, messages: list[Message], **opts: Any) -> Completion:
        body = json.dumps({"model": self.model, "messages": messages, **opts}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with self._opener(req) as resp:
                data = json.loads(_as_text(resp.read()))
        except urllib.error.HTTPError as e:
            detail = _as_text(e.read())
            raise TransportError(f"LLM HTTP {e.code}: {detail[:500]}") from e
        except urllib.error.URLError as e:
            raise TransportError(f"LLM transport failed: {e.reason}") from e

        try:
            choice = data["choices"][0]
            usage = data.get("usage", {})
            return Completion(
                content=choice["message"]["content"],
                stop_reason=choice.get("finish_reason"),
                input_tokens=usage.get("prompt_tokens"),
                output_tokens=usage.get("completion_tokens"),
            )
        except (KeyError, IndexError, TypeError) as e:
            raise TransportError(f"malformed LLM response: {str(data)[:500]}") from e


# ==========================================================================
# Per-device learning store (native; v1.1)
# ==========================================================================
class FileLearningStore:
    """System-level learning under ``~/.tack`` (or ``$TACK_HOME``).

    Native-only: it reaches the host home directly, not through the
    workspace-scoped ExecFS seam (the workspace can't see the device store). The
    Karkhana adapter will supply its own store rooted at the VM's persistent home
    at D1. Plain append-only Markdown — no server, no telemetry (Vision §4.4).
    """

    def __init__(self, root: str | None = None):
        base = root or os.environ.get("TACK_HOME") or os.path.join(os.path.expanduser("~"), ".tack")
        self.root = base
        self.playbook = os.path.join(base, "playbook.md")
        self.anti = os.path.join(base, "anti-patterns.md")

    def _read(self, path: str) -> str:
        try:
            with open(path, encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return ""

    def _append(self, path: str, line: str) -> None:
        existing = self._read(path)
        if line.strip() and line.strip() in existing:
            return  # dedup
        os.makedirs(self.root, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            f.write(line.rstrip() + "\n")

    def prior_knowledge(self) -> str:
        parts = []
        playbook = self._read(self.playbook).strip()
        anti = self._read(self.anti).strip()
        if playbook:
            parts.append("# Device playbook — moves that have worked before\n" + playbook)
        if anti:
            parts.append("# Known anti-patterns — avoid these\n" + anti)
        return "\n\n".join(parts)

    def record_success(self, note: str) -> None:
        self._append(self.playbook, f"- {note}")

    def record_anti_pattern(self, signature: str, note: str) -> None:
        self._append(self.anti, f"- {signature} — {note}")


# ==========================================================================
# Convenience binding
# ==========================================================================
def native_adapters(
    *,
    workspace: str = ".",
    model: str = "gpt-4o-mini",
    api_key: str | None = None,
    base_url: str = "https://api.openai.com/v1",
    opener: Opener | None = None,
) -> Adapters:
    """Build the full native :class:`Adapters` bundle in one call."""
    return Adapters(
        llm=NativeLLM(model=model, api_key=api_key, base_url=base_url, opener=opener),
        control=NativeControl(),
        execfs=NativeExecFS(workspace=workspace),
    )
