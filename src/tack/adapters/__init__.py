"""Adapter seams and concrete adapters.

:mod:`tack.adapters.base` defines the three Protocols the core depends on.
Concrete adapters (``native``, later ``karkhana``) live alongside it and are
the only environment-specific code in the project.
"""

from tack.adapters.base import (
    Adapters,
    Completion,
    Control,
    ExecFS,
    ExecResult,
    LLMTransport,
    Message,
    Role,
)

__all__ = [
    "Adapters",
    "Completion",
    "Control",
    "ExecFS",
    "ExecResult",
    "LLMTransport",
    "Message",
    "Role",
]
