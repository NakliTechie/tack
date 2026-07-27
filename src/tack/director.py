"""Director loop — multi-phase orchestration with pluggable coding backends.

The director is the outer loop that makes "give it spec docs and it builds" work.
It decomposes specification documents into a phased build plan, executes each
phase through either an **Aider subprocess** (:ref:`backend="aider", default) or
Tack's own :func:`run_task` loop (``backend="tack"``), checkpoints progress, and
reports results. Lives *outside* the core.

Usage (CLI)::

    uv run tack build specs/              # fresh build (uses Aider by default)
    uv run tack build specs/ --resume     # resume from checkpoint

Usage (Python)::

    from tack.adapters.native import native_adapters
    from tack.director import build_from_specs

    results = build_from_specs(
        "specs/",
        native_adapters(workspace="."),
        workspace=".",
    )
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Literal

from tack.adapters.base import Adapters, ExecFS, LLMTransport, Message
from tack.core.loop import Config, TaskResult, run_task

DIRECTOR_STATE = ".tack/director-state.json"

# Aider retries per phase (maps to config.max_iterations when available).
AIDER_DEFAULT_RETRIES = 3
AIDER_DEFAULT_TIMEOUT = 600.0  # 10 min per aider invocation


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class PhaseResult:
    """Outcome of a single phase, serializable for checkpoint/resume."""

    phase_id: str
    title: str
    task: str
    status: str  # completed | failed | skipped | error
    backend: str = ""  # "aider" | "tack" — which engine ran this phase
    turns: int = 0
    success: bool = False
    stop_reason: str = ""
    verify_command: str | None = None
    summary: str | None = None
    error: str | None = None
    escalated: bool = False
    escalation_turn: int | None = None
    promoted_tools: list[str] = field(default_factory=list)


@dataclass
class DirectorState:
    """Persisted build state — enables resume after interruption."""

    spec_dir: str
    title: str
    phases: list[dict] = field(default_factory=list)
    results: list[dict] = field(default_factory=list)
    started_at: float = 0.0

    def save(self, workspace: str) -> None:
        path = os.path.join(workspace, DIRECTOR_STATE)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(asdict(self), f, indent=2, default=str)

    @classmethod
    def load(cls, workspace: str) -> DirectorState | None:
        path = os.path.join(workspace, DIRECTOR_STATE)
        try:
            with open(path) as f:
                data = json.load(f)
            return cls(**data)
        except (FileNotFoundError, json.JSONDecodeError, TypeError):
            return None


# ---------------------------------------------------------------------------
# Spec ingestion
# ---------------------------------------------------------------------------


def load_specs(spec_dir: str) -> list[dict]:
    """Read all ``.md`` files from *spec_dir*.

    Returns ``[{"file": "vision.md", "content": "..."}, ...]``.
    """
    path = Path(spec_dir)
    if not path.is_dir():
        raise NotADirectoryError(f"spec directory not found: {spec_dir}")

    specs: list[dict] = []
    for f in sorted(path.glob("*.md")):
        content = f.read_text(encoding="utf-8").strip()
        if content:
            specs.append({"file": f.name, "content": content})

    if not specs:
        raise ValueError(f"no .md files found in {spec_dir}")

    return specs


# ---------------------------------------------------------------------------
# Plan generation (LLM-driven)
# ---------------------------------------------------------------------------


def _extract_json(text: str) -> str | None:
    """Extract the first JSON array (or object) from *text*, stripping fences."""
    # strip markdown fences
    if text.startswith("```"):
        _, *rest = text.split("\n", 1)
        text = rest[0] if rest else text
        text = text.rsplit("```", 1)[0]
    m = re.search(r"(\[.*\]|\{.*\})", text, re.DOTALL)
    return m.group(1) if m else text


def build_plan_from_specs(
    llm: LLMTransport,
    specs: list[dict],
    title: str = "Build",
) -> list[dict]:
    """Ask the LLM to decompose specs into a phased build plan.

    Returns a list of phase dicts::

        [{"id": "01-setup", "title": "Scaffolding",
          "task": "…", "verify": "pytest -q",
          "depends_on": []}, …]

    Falls back to a single monolithic phase if parsing fails.
    """
    spec_text = "\n\n".join(
        f"## {s['file']}\n{s['content']}" for s in specs
    )

    prompt = Message(
        role="user",
        content=(
            "You are a technical project planner. Given these specification "
            "documents, produce a phased build plan.\n\n"
            "Each phase is a single self-contained task that an autonomous "
            "coding agent can execute and verify. Keep phases small\n"
            "(5-15 agent turns each). Every phase must have a clear\n"
            "goal and pass/fail condition.\n\n"
            "Rules:\n"
            "- Order phases so later phases build on earlier ones.\n"
            "- A phase should depend_on earlier phase IDs when it needs\n"
            "  their output. Use empty depends_on for independent phases.\n"
            "- Include a verify command when one exists (e.g. 'pytest -q').\n"
            "- Make task descriptions concrete: name files, mention\n"
            "  specific functions or features to implement.\n\n"
            "Respond with ONLY a JSON array of phase objects:\n"
            "[\n"
            '  {\n'
            '    "id": "01-scaffold",\n'
            '    "title": "Project scaffolding",\n'
            '    "task": "Create the project structure …",\n'
            '    "verify": "pytest -q",\n'
            '    "depends_on": []\n'
            "  },\n"
            "  …\n"
            "]\n\n"
            f"Specifications:\n\n{spec_text}"
        ),
    )

    response = llm.complete([prompt], temperature=0.1)
    raw = _extract_json(response.content) or ""

    try:
        phases = json.loads(raw)
    except json.JSONDecodeError:
        phases = None

    if not isinstance(phases, list):
        # Fallback: treat the whole build as one phase
        phases = [
            {
                "id": "01-build",
                "title": title,
                "task": (
                    "Read the spec documents and build the project. "
                    "Write code, create files, implement features. "
                    "Iterate until everything works."
                ),
                "verify": None,
                "depends_on": [],
            }
        ]

    # Normalise fields
    for i, p in enumerate(phases):
        p.setdefault("id", f"{i + 1:02d}-phase")
        p.setdefault("title", p.get("id", f"Phase {i + 1}"))
        p.setdefault("verify", None)
        p.setdefault("depends_on", [])
        if "task" not in p:
            p["task"] = p.get("title", f"Phase {i + 1}")

    return phases


# ---------------------------------------------------------------------------
# Dependency resolution
# ---------------------------------------------------------------------------


def _ready_phases(
    phases: list[dict],
    completed_ids: set[str],
    failed_ids: set[str],
) -> tuple[list[dict], list[str]]:
    """Return ``(ready_phases, blocked_ids)``.

    A phase is ready if all its dependencies are in *completed_ids* and it
    hasn't been run yet. Blocked phases are those whose dependency failed —
    they are skipped permanently.
    """
    ready: list[dict] = []
    blocked: list[str] = []
    for p in phases:
        pid = p["id"]
        if pid in completed_ids or pid in failed_ids:
            continue
        deps = set(p.get("depends_on", []))
        missing = deps - completed_ids
        if missing & failed_ids:
            blocked.append(pid)
        elif not missing:
            ready.append(p)
    return ready, blocked


# ---------------------------------------------------------------------------
# Backend: Aider subprocess
# ---------------------------------------------------------------------------


def _check_aider_available() -> bool:
    """Return ``True`` if ``aider`` is on PATH."""
    return shutil.which("aider") is not None


def _execute_phase_with_aider(
    pid: str,
    phase: dict,
    workspace: str,
    execfs: ExecFS,
    api_key: str | None,
    verify_cmd: str | None,
    *,
    retries: int = AIDER_DEFAULT_RETRIES,
    model: str | None = None,
    architect: bool = False,
    timeout: float = AIDER_DEFAULT_TIMEOUT,
) -> PhaseResult:
    """Execute a phase by shelling out to ``aider``.

    Builds an Aider CLI invocation, runs it in the workspace, then checks
    the verify command.  Retries up to *retries* times on verification
    failure, passing the previous failure output back as context.

    Returns a :class:`PhaseResult` regardless of outcome.
    """
    task: str = phase["task"]

    # --- Build aider CLI ---------------------------------------------------
    args: list[str] = [
        "aider",
        "--yes",           # auto-confirm file creation / edits
        "--exit",          # exit after processing --message (non-interactive)
        "--no-git",        # don't touch git — Tack owns versioning
        "--no-auto-commits",
        "--message",
        task,
    ]
    if model:
        args.extend(["--model", model])
    if architect:
        args.append("--architect")
    if api_key:
        args.extend(["--openai-api-key", api_key])

    escaped = " ".join(shlex.quote(a) for a in args)

    # --- Execute with retry loop ------------------------------------------
    last_error = ""
    for attempt in range(1, retries + 1):
        # On retry, augment the message with the previous failure context
        cmd = escaped
        if attempt > 1 and last_error:
            retry_args = list(args)
            # Replace the --message value
            msg_idx = retry_args.index("--message") + 1
            retry_args[msg_idx] = (
                f"The previous attempt failed verification. Fix the issue.\n\n"
                f"Original task: {task}\n\n"
                f"Verification output from last attempt:\n{last_error}"
            )
            cmd = " ".join(shlex.quote(a) for a in retry_args)

        # Run aider (respects cwd via execfs.run, which uses workspace as cwd)
        try:
            result = execfs.run(cmd, timeout=timeout)
        except Exception as exc:
            last_error = f"aider subprocess error: {exc}"
            continue

        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()
        aider_ok = result.exit_code == 0

        # --- Run verification ----------------------------------------------
        if verify_cmd:
            vresult = execfs.run(verify_cmd)
            if vresult.exit_code == 0:
                return PhaseResult(
                    phase_id=pid,
                    title=phase["title"],
                    task=task,
                    backend="aider",
                    status="completed",
                    turns=attempt,
                    success=True,
                    verify_command=verify_cmd,
                    summary=f"Verified on aider attempt {attempt}/{retries}",
                )
            last_error = (
                vresult.stderr or vresult.stdout or "(verify produced no output)"
            ).strip()[:2000]
        else:
            # No verify command — trust aider's exit code
            if aider_ok:
                return PhaseResult(
                    phase_id=pid,
                    title=phase["title"],
                    task=task,
                    backend="aider",
                    status="completed",
                    turns=attempt,
                    success=True,
                    summary="Aider completed (no verify command)",
                )
            last_error = (
                stderr or stdout or f"aider exited {result.exit_code}"
            )[:2000]

    # --- All retries exhausted --------------------------------------------
    return PhaseResult(
        phase_id=pid,
        title=phase["title"],
        task=task,
        backend="aider",
        status="failed",
        turns=retries,
        success=False,
        verify_command=verify_cmd,
        error=f"Failed after {retries} attempts. Last error: {last_error[:500]}",
        summary=last_error,
    )


# ---------------------------------------------------------------------------
# Backend: Tack's own run_task() loop
# ---------------------------------------------------------------------------


def _execute_phase_with_tack(
    pid: str,
    phase: dict,
    workspace: str,
    adapters: Adapters,
    config: Config,
    frontier: LLMTransport | None = None,
) -> PhaseResult:
    """Execute a phase through :func:`tack.core.loop.run_task`.

    This is the original Tack backend for the director — used when ``aider``
    is unavailable, or when ``backend="tack"`` is explicitly selected (e.g. in
    tests with a scripted brain).
    """
    task: str = phase["task"]

    phase_config = Config(
        max_iterations=config.max_iterations,
        verify_command=phase.get("verify") or config.verify_command,
        verify_each_turn=config.verify_each_turn,
        doom_window=config.doom_window,
        dangerous_command_flag=config.dangerous_command_flag,
        git_per_step=config.git_per_step,
        bash_timeout=config.bash_timeout,
        compact_threshold_tokens=config.compact_threshold_tokens,
        keep_recent_turns=config.keep_recent_turns,
        escalate_on_doom=config.escalate_on_doom,
        escalate_without_ground_truth=config.escalate_without_ground_truth,
    )

    try:
        tr: TaskResult = run_task(
            task, adapters, workspace=workspace, config=phase_config, frontier=frontier,
        )

        return PhaseResult(
            phase_id=pid,
            title=phase["title"],
            task=task,
            backend="tack",
            status="completed" if tr.success else "failed",
            turns=tr.turns,
            success=tr.success,
            stop_reason=tr.stop_reason,
            verify_command=tr.verify_command,
            summary=tr.summary or "",
            escalated=tr.escalated,
            escalation_turn=tr.escalation_turn,
            promoted_tools=tr.promoted_tools,
        )
    except Exception as exc:
        return PhaseResult(
            phase_id=pid,
            title=phase["title"],
            task=task,
            backend="tack",
            status="error",
            error=str(exc),
        )


# ---------------------------------------------------------------------------
# The director
# ---------------------------------------------------------------------------


def build_from_specs(
    spec_dir: str,
    adapters: Adapters,
    *,
    workspace: str = ".",
    config: Config | None = None,
    resume: bool = False,
    frontier: LLMTransport | None = None,
    backend: str | None = None,
    aider_model: str | None = None,
    aider_architect: bool = False,
) -> list[PhaseResult]:
    """Orchestrate a full build from specification documents.

    This is the outer loop that makes Tack autonomous over multi-hour builds::

        1. Read ``.md`` files from *spec_dir*
        2. Ask the LLM to decompose them into a phased plan
        3. Execute each phase — via Aider (default) or Tack's loop
        4. Checkpoint after each phase (survives crash / Ctrl-C)
        5. Report per-phase and overall results

    Parameters
    ----------
    spec_dir:
        Directory with ``*.md`` spec documents (vision, handoff, …).
    adapters:
        The Tack environment binding (LLM transport, exec, control).
    workspace:
        The build output directory (default: ``.``).
    config:
        Tack loop config (for the ``"tack"`` backend; ``max_iterations`` maps
        to Aider retry budget for the ``"aider"`` backend).
    resume:
        If True, load checkpoint from ``.tack/director-state.json``
        and continue where the last run stopped.
    frontier:
        Optional stronger LLM for the Tack loop's frontier-escalation
        path (only used by ``backend="tack"``).
    backend:
        Which coding engine to use per phase:

        * ``"auto"`` (default) — use Aider if installed, fall back to Tack.
        * ``"aider"`` — use Aider subprocess (raises if not installed).
        * ``"tack"`` — use Tack's own :func:`~tack.core.loop.run_task`.

    aider_model:
        Model name to pass to Aider (e.g. ``"gpt-4o"``).  Default uses
        Aider's own model resolution.
    aider_architect:
        If True, enable Aider's ``--architect`` mode (plan-then-code).

    Returns
    -------
    list[PhaseResult]
        One entry per executed phase.
    """
    config = config or Config()
    llm = adapters.llm
    control = adapters.control
    execfs = adapters.execfs
    spec_dir = os.path.abspath(spec_dir)

    # --- Resolve backend --------------------------------------------------
    resolved_backend = _resolve_backend(backend)
    print(f"[director] backend: {resolved_backend}")
    if resolved_backend == "aider":
        print(f"[director]   aider args: {'architect' if aider_architect else 'direct'}"
              f"{', model=' + aider_model if aider_model else ''}"
              f", retries={config.max_iterations if config.max_iterations < 100 else AIDER_DEFAULT_RETRIES}")

    # ------------------------------------------------------------------
    # Load or build the build plan
    # ------------------------------------------------------------------
    state: DirectorState | None = None

    if resume:
        state = DirectorState.load(workspace)
        if state is None:
            print("[director] no checkpoint found — starting fresh")

    if state is None:
        print(f"[director] reading specs from {spec_dir}")
        specs = load_specs(spec_dir)
        print(f"[director] found {len(specs)} spec file(s)")
        for s in specs:
            print(f"  {s['file']}: {len(s['content'])} chars")

        title = (
            specs[0]["file"].replace(".md", "").replace("-", " ").title()
            if specs
            else "Build"
        )
        print("[director] generating build plan from specs …")
        phases = build_plan_from_specs(llm, specs, title=title)
        print(f"[director] plan has {len(phases)} phase(s):")
        for p in phases:
            deps = p.get("depends_on", [])
            dep_str = f"  [after: {', '.join(deps)}]" if deps else ""
            print(f"  {p['id']}: {p['title']}{dep_str}")

        state = DirectorState(
            spec_dir=spec_dir,
            title=title,
            phases=phases,
            started_at=time.time(),
        )
        state.save(workspace)

    # ------------------------------------------------------------------
    # Replay completed results from checkpoint
    # ------------------------------------------------------------------
    completed_ids: set[str] = set()
    failed_ids: set[str] = set()
    results: list[PhaseResult] = []

    for r in state.results:
        pr = PhaseResult(**r)
        results.append(pr)
        if pr.status == "completed":
            completed_ids.add(pr.phase_id)
        elif pr.status in ("failed", "error"):
            failed_ids.add(pr.phase_id)

    if state.results:
        print(
            f"[director] checkpoint has {len(completed_ids)} completed, "
            f"{len(failed_ids)} failed — {'resuming' if resume else 'starting fresh'}"
        )

    # --- Compute Aider retry budget from config ---------------------------
    aider_retries = (
        config.max_iterations
        if config.max_iterations and config.max_iterations < 100
        else AIDER_DEFAULT_RETRIES
    )

    # ------------------------------------------------------------------
    # Phase execution loop
    # ------------------------------------------------------------------
    while not control.is_cancelled():
        ready, blocked = _ready_phases(state.phases, completed_ids, failed_ids)

        if not ready:
            if blocked:
                print(
                    f"[director] {len(blocked)} phase(s) blocked by failed "
                    f"dependencies — {len(completed_ids)} completed, "
                    f"{len(failed_ids)} failed"
                )
            else:
                print(
                    f"[director] all phases done — "
                    f"{len(completed_ids)} completed, {len(failed_ids)} failed"
                )
            break

        phase = ready[0]
        pid: str = phase["id"]
        print(f"\n{'=' * 60}")
        print(f"[director] phase {pid}: {phase['title']}")
        print(f"{'=' * 60}")

        # ---- Dispatch to the chosen backend -----------------------------
        if resolved_backend == "aider":
            outcome = _execute_phase_with_aider(
                pid=pid,
                phase=phase,
                workspace=workspace,
                execfs=execfs,
                api_key=getattr(llm, "api_key", None),
                verify_cmd=phase.get("verify") or config.verify_command,
                retries=aider_retries,
                model=aider_model,
                architect=aider_architect,
            )
        else:
            outcome = _execute_phase_with_tack(
                pid=pid,
                phase=phase,
                workspace=workspace,
                adapters=adapters,
                config=config,
                frontier=frontier,
            )

        # ---- Record outcome --------------------------------------------
        is_ok = outcome.status == "completed"
        if is_ok:
            completed_ids.add(pid)
            extra = (
                f" (escalated @ turn {outcome.escalation_turn})"
                if outcome.escalated
                else ""
            )
            print(
                f"[director] ✓ phase {pid} done in {outcome.turns} attempt(s)"
                f" — verified{extra}"
            )
            if outcome.promoted_tools:
                print(
                    f"[director]   promoted tools: "
                    f"{', '.join(outcome.promoted_tools)}"
                )
        else:
            failed_ids.add(pid)
            print(
                f"[director] ✗ phase {pid} failed after "
                f"{outcome.turns} attempt(s) — {outcome.error or outcome.summary or ''}"
            )

        results.append(outcome)
        state.results = [asdict(r) for r in results]
        state.save(workspace)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    elapsed = time.time() - state.started_at
    done = sum(1 for r in results if r.status == "completed")
    nf = sum(1 for r in results if r.status in ("failed", "error"))
    total = len(results)

    print(f"\n{'=' * 60}")
    print(
        f"[director] build finished — {done}/{total} phases passed"
        f" ({nf} failed) in {elapsed:.0f}s"
    )
    for r in results:
        icon = (
            "✓"
            if r.status == "completed"
            else "✗"
            if r.status in ("failed", "error")
            else "—"
        )
        label = f" (aider)" if r.backend == "aider" else ""
        print(f"  {icon} {r.phase_id} {r.title}: {r.status}{label} ({r.turns}t)")
        if r.error:
            print(f"       error: {r.error[:120]}")
        if r.promoted_tools:
            print(f"       tools: {', '.join(r.promoted_tools)}")

    return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_backend(backend: str | None) -> str:
    """Resolve the ``backend`` parameter to ``"aider"`` or ``"tack"``.

    * ``"aider"`` — use Aider (raises if not installed).
    * ``"tack"`` — use Tack's own loop.
    * ``None`` / ``"auto"`` — auto-detect: Aider if on PATH, else Tack.
    """
    if backend in (None, "auto"):
        if _check_aider_available():
            return "aider"
        print("[director] Aider not found on PATH — falling back to Tack loop backend")
        return "tack"
    if backend == "aider":
        if not _check_aider_available():
            raise RuntimeError(
                "backend='aider' but `aider` is not on PATH. "
                "Install it with `pip install aider-chat`."
            )
        return "aider"
    if backend == "tack":
        return "tack"

    raise ValueError(f"unknown backend: {backend!r} (expected 'aider', 'tack', or 'auto')")
