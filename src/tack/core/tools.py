"""A5 — the four tools: read · write · edit · bash.

Exactly four (locked decision); bash composes the rest, the agent self-extends
(v1.1) into ``.tack/bin/``. Every tool is built on the Execution+FS seam and
returns *ACI-disciplined feedback*: structured, truncated, signal-not-noise —
because the brain may be a small local model with a small window, so noisy tool
output is context rot.

The result also carries a compact ``signature`` (the action, normalised) that
the safety layer uses for doom-loop detection.
"""

from __future__ import annotations

from dataclasses import dataclass

from tack.adapters.base import ExecFS
from tack.core.util import truncate
from tack.errors import EditError, TackError


@dataclass
class ToolResult:
    ok: bool
    feedback: str
    signature: str = ""


class Tools:
    """Dispatch + feedback-formatting for the four tools, over an ExecFS seam."""

    NAMES = ("read", "write", "edit", "bash")

    def __init__(self, execfs: ExecFS, *, bash_timeout: float | None = 60.0):
        self.fs = execfs
        self.bash_timeout = bash_timeout

    # -- dispatch ----------------------------------------------------------
    def dispatch(self, tool: str, args: dict) -> ToolResult:
        if tool not in self.NAMES:
            return ToolResult(
                False,
                f"unknown tool {tool!r}; available tools: {', '.join(self.NAMES)}",
                f"unknown:{tool}",
            )
        try:
            if tool == "read":
                return self.read(args["path"])
            if tool == "write":
                return self.write(args["path"], args.get("content", ""))
            if tool == "edit":
                return self.edit(args["path"], args["old"], args["new"])
            if tool == "bash":
                return self.bash(args["cmd"])
        except KeyError as e:
            return ToolResult(False, f"{tool}: missing required argument {e}", f"badargs:{tool}")
        raise AssertionError("unreachable")  # pragma: no cover

    # -- individual tools --------------------------------------------------
    def read(self, path: str) -> ToolResult:
        try:
            content = self.fs.read(path)
        except FileNotFoundError:
            return ToolResult(False, f"read: file not found: {path}", f"read:{path}")
        except (TackError, OSError) as e:
            return ToolResult(False, f"read: {e}", f"read:{path}")
        if not content:
            return ToolResult(True, f"{path} is empty", f"read:{path}")
        numbered = "\n".join(
            f"{i:>4}| {line}" for i, line in enumerate(content.splitlines(), start=1)
        )
        return ToolResult(True, truncate(numbered), f"read:{path}")

    def write(self, path: str, content: str) -> ToolResult:
        try:
            self.fs.write(path, content)
        except (TackError, OSError) as e:
            return ToolResult(False, f"write: {e}", f"write:{path}")
        return ToolResult(True, f"wrote {len(content)} chars to {path}", f"write:{path}")

    def edit(self, path: str, old: str, new: str) -> ToolResult:
        try:
            self.fs.edit(path, old, new)
        except EditError as e:
            return ToolResult(False, str(e), f"edit:{path}")  # the correction, verbatim
        except FileNotFoundError:
            return ToolResult(False, f"edit: file not found: {path}", f"edit:{path}")
        except (TackError, OSError) as e:
            return ToolResult(False, f"edit: {e}", f"edit:{path}")
        return ToolResult(True, f"edited {path}", f"edit:{path}")

    def bash(self, cmd: str) -> ToolResult:
        r = self.fs.run(cmd, timeout=self.bash_timeout)
        parts = [f"$ {cmd}", f"exit: {r.exit_code}"]
        if r.stdout.strip():
            parts.append("--- stdout ---\n" + truncate(r.stdout))
        if r.stderr.strip():
            parts.append("--- stderr ---\n" + truncate(r.stderr))
        return ToolResult(r.exit_code == 0, "\n".join(parts), f"bash:{cmd.strip()}")
