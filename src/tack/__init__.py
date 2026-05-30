"""Tack — a portable coding-agent harness.

An environment-agnostic plan→edit→verify→iterate→learn loop that speaks to
three adapter seams (see :mod:`tack.adapters.base`). Built and tuned native;
deployed *unchanged* to constrained targets (the Karkhana browser-VM at D1).

The public entry point is a *function*, not a REPL — so the future MCP
``ask_agent`` surface (external agents firing tasks at Tack) is cheap to add.
"""

__version__ = "0.0.0"

from tack.core import Config, TaskResult, run_task

__all__ = ["Config", "TaskResult", "run_task", "__version__"]
