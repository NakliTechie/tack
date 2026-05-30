"""Tack's small exception hierarchy.

Kept deliberately tiny — the loop turns most failures into *feedback text* for
the model rather than raising. These exist for the few cases the core must
distinguish programmatically (a bad edit it should relay verbatim, a path that
escapes the workspace, a transport that hard-failed).
"""

from __future__ import annotations


class TackError(Exception):
    """Base class for every Tack-raised error."""


class EditError(TackError):
    """An `edit` whose `old` text was missing or not unique — relayed to the
    model as a correction (ACI discipline: the interface corrects immediately)."""


class WorkspaceError(TackError):
    """A path that would escape the workspace root."""


class TransportError(TackError):
    """The LLM transport hard-failed (HTTP error, malformed response)."""
