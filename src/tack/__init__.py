"""Tack — a portable coding-agent harness.

An environment-agnostic plan→edit→verify→iterate→learn loop that speaks to
three adapter seams (see :mod:`tack.adapters.base`). Built and tuned native;
deployed *unchanged* to constrained targets (the Karkhana browser-VM at D1).

The public entry point is a *function*, not a REPL — so the future MCP
``ask_agent`` surface (external agents firing tasks at Tack) is cheap to add.

:func:`tack.director.build_from_specs` is an *exploratory* orchestrator above
the core (not a milestone — see ``docs/director-notes.md``): it decomposes spec
documents into a multi-phase build plan, executes each phase through
:func:`run_task`, checkpoints progress, and reports results.
"""

__version__ = "0.0.0"

from tack.core import Config, TaskResult, run_task

__all__ = ["Config", "TaskResult", "run_task", "__version__"]
