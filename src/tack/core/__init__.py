"""The environment-agnostic core.

Loop (6-phase ReAct), the 4 tools, context engine, verification, and
safety/economics live here. Everything in this package depends only on
:mod:`tack.adapters.base` — never on a concrete transport.

The public surface is :func:`run_task`.
"""

from tack.core.loop import Config, TaskResult, parse_action, run_task

__all__ = ["Config", "TaskResult", "parse_action", "run_task"]
