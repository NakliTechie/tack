"""Tack — a portable coding-agent harness.

An environment-agnostic plan→edit→verify→iterate→learn loop that speaks to
three adapter seams (see :mod:`tack.adapters.base`). Built and tuned native;
deployed *unchanged* to constrained targets (the Karkhana browser-VM at D1).

The public entry point is a *function*, not a REPL — so the future MCP
``ask_agent`` surface (external agents firing tasks at Tack) is cheap to add.

The :func:`tack.director.build_from_specs` function wraps the core loop in a
higher-order orchestrator that decomposes spec documents into a multi-phase
build plan, executes phases through :func:`run_task`, checkpoints progress,
and reports results — the "give it two docs and it builds" experience.
"""

__version__ = "0.0.0"

from tack.core import Config, TaskResult, run_task

__all__ = ["Config", "TaskResult", "run_task", "__version__"]
