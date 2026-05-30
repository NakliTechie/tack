"""The environment-agnostic core.

Loop (6-phase ReAct), the 4 tools, context engine, verification, and
safety/economics live here. Everything in this package depends only on
:mod:`tack.adapters.base` — never on a concrete transport. Filled in across
Batch A (A5–A9).
"""
