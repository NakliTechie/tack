"""The three adapter seams — the only interfaces the Tack core may touch.

The core is environment-agnostic: it speaks to these three Protocols and
nothing else. No transport detail (HTTPS, serial, 9P, file-bridge, subprocess)
appears here or anywhere in :mod:`tack.core`. Each concrete environment supplies
an adapter implementing these seams:

    native (dev / CI)  : direct HTTPS BYOK · stdin/signal/socket · subprocess + real FS
    karkhana (D1)      : file→fetch bridge · serial console · in-VM bash + 9P/FSA workspace

If the core ever needs editing to run somewhere new, the seam abstraction
failed — fix the seam, not the core.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol, TypedDict, runtime_checkable

Role = Literal["system", "user", "assistant", "tool"]


class Message(TypedDict):
    """One entry in the conversation handed to the model."""

    role: Role
    content: str


# --------------------------------------------------------------------------
# Seam 1 — LLM transport
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Completion:
    """What the core gets back from a single model call.

    ``content`` is the model's text. Token counts feed the context engine's
    compaction trigger and the economic accounting; they may be ``None`` when
    a transport doesn't report usage.
    """

    content: str
    stop_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


@runtime_checkable
class LLMTransport(Protocol):
    """Seam 1 — turn a message list into a model response.

    Native: direct HTTPS, BYOK. Karkhana: the agent writes the request to a
    file, the browser fetches it with the key injected browser-side — the key
    never enters the VM.
    """

    def complete(self, messages: list[Message], **opts: Any) -> Completion: ...


# --------------------------------------------------------------------------
# Seam 2 — Control
# --------------------------------------------------------------------------
@runtime_checkable
class Control(Protocol):
    """Seam 2 — cooperative cancellation and task injection.

    Two sides, one Protocol:

    * **outward** — the operator (or the future MCP ``ask_agent`` surface)
      calls :meth:`cancel` and :meth:`inject_task`. Native wires these to
      stdin / signal / a unix socket; Karkhana wires them to the serial console
      (written invisibly post-boot). The core never sees which.
    * **core-facing** — the loop polls :meth:`is_cancelled` and
      :meth:`take_injected_task` between turns.
    """

    # outward surface (called by the operator / external agents)
    def cancel(self) -> None: ...
    def inject_task(self, task: str) -> None: ...

    # core-facing surface (polled by the loop)
    def is_cancelled(self) -> bool: ...
    def take_injected_task(self) -> str | None: ...


# --------------------------------------------------------------------------
# Seam 3 — Execution + filesystem
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class ExecResult:
    """Captured result of one command.

    ``exit_code`` is the closed-loop signal: 0 advances; non-zero feeds the
    actual ``stderr`` text into the next turn. That feedback *is* the loop.
    """

    stdout: str
    stderr: str
    exit_code: int


@runtime_checkable
class ExecFS(Protocol):
    """Seam 3 — run commands and touch files in the workspace.

    Native: subprocess + real FS. Karkhana: in-VM bash + a 9P-mounted FSA
    workspace. The four core tools (read / write / edit / bash) are built on
    exactly this seam — nothing else.
    """

    def run(self, cmd: str, *, timeout: float | None = None) -> ExecResult: ...
    def read(self, path: str) -> str: ...
    def write(self, path: str, content: str) -> None: ...
    def edit(self, path: str, old: str, new: str) -> None: ...


# --------------------------------------------------------------------------
# The environment binding handed to the core at startup
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Adapters:
    """The full environment binding the core runs against.

    One of these is constructed per environment (native, karkhana) and passed
    into the core's entry function. The core holds a reference and reaches the
    world only through ``.llm`` / ``.control`` / ``.execfs``.
    """

    llm: LLMTransport
    control: Control
    execfs: ExecFS
