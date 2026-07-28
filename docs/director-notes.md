# director — status notes (not a gate)

`docs/v1.0-gate.md`, `v1.1-gate.md` and `v1.2-gate.md` each record a **passed** gate. This
document deliberately does not follow that pattern, because the director has not passed
one. It records what the director is, what it demonstrably does, and the open decision
that has to be settled before it can be called a milestone.

## What it is

`tack.director.build_from_specs()` — the outer loop that makes "hand it spec docs and it
builds" work. It reads `*.md` from a spec directory, asks the LLM to decompose them into a
phased plan, executes each phase, checkpoints to `.tack/director-state.json` after every
phase (so a crash or Ctrl-C is resumable), and reports per-phase results.

```sh
uv run tack build specs/            # fresh build
uv run tack build specs/ --resume   # resume from checkpoint
```

It lives *outside* the core, alongside `run_task` rather than inside it — consistent with
the standing rule that the core talks only to the three adapter seams.

## What is actually demonstrated

Reproduce: `uv run python examples/demo_director.py` (no API key needed — scripted brain,
`backend="tack"`).

```
[director] phase 01-fix-add: Fix the add function
[director] ✓ phase 01-fix-add done in 3 attempt(s) — verified
[director] phase 02-verify-clean: Verify final state
[director] ✓ phase 02-verify-clean done in 1 attempt(s) — verified
[director] build finished — 2/2 phases passed (0 failed) in 5s
overall   : ✓ PASS
```

So: multi-phase decomposition, per-phase execution through Tack's own loop, per-phase
verification, and the completion report all work against a scripted brain. 28 tests in
`tests/test_director.py` cover planning, checkpoint/resume, and both backends.

## Why this is not `docs/v1.4-gate.md`

Four reasons, in descending order of weight.

1. **The backend is chosen by auto-detection.** `_resolve_backend(None)` returns `"aider"`
   if `aider` is on `PATH` and `"tack"` otherwise. The engine behind `tack build` therefore
   depends on what happens to be installed on the machine — the same command runs a
   different agent for different users, with no flag in the CLI to pin it
   (`build_from_specs(backend=...)` exists; `tack build` does not expose it).
2. **The default backend cannot exist on the primary target.** D1 deploys the *unchanged*
   core into Karkhana's Alpine + Python 3.11 VM. Aider is not there and will not be. A
   headline feature whose default engine is unavailable on the deployment target that the
   vision calls the defensibility centerpiece is not a milestone yet.
3. **Aider is positioned in the vision as a competitor, not a dependency** — named in the
   crowded-field passage that motivates building the engine at all. Shelling the flagship
   "build from specs" loop out to it inverts the project's own thesis, which is that
   Tack's loop plus a cheap model is the thing worth having.
4. **No live-model run.** Every other gate doc records mechanics proven against a scripted
   brain *and* names the live run it still owes. The director has the former and has never
   had the latter. Until 2026-07-28 it was also unreachable from the command line at all
   (see below).

## Fixed on 2026-07-28

Committed as part of repairing the landing, not as new work:

- `tack "task" --verify <cmd>` — restored; `--verify` had moved into the `build` subparser
  only, so single-task mode rejected it.
- `tack build specs/` — **was unreachable from a real shell.** `main()` tested
  `argv[0] == "build"` before resolving `argv` from `sys.argv`, and the console-script
  entry calls `main()` with `argv=None`. Every command-line invocation fell through to the
  single-task parser. It only routed for library callers passing `argv` explicitly, which
  is how the tests called it — so the tests passed while the feature did not exist.
- `build_parser` — restored as a public alias after being renamed to a private name.

## The open decision

**Is the director a v1.4 milestone, or an exploratory spike?** Six weeks of context was
lost between writing (2026-06-12) and committing (2026-07-28); it appears in neither
`tack-VISION-AND-ROADMAP.md`, `tack-HANDOFF.md`, nor the README roadmap, and was never in
`plan/pending.md`.

Recorded default, pending the author's call: **exploratory**, on the four grounds above.
If it is instead intended as v1.4, the smallest path to a real gate is:

1. Decide the backend question — most likely default `backend="tack"` and make Aider an
   explicit opt-in, since a machine-dependent default is the worst of the three options.
2. Expose `--backend` on `tack build` so the choice is visible and pinnable.
3. Do a live-model run of `tack build specs/` and record the transcript, as
   `docs/v1.{0,1,2}-gate.md` each do.
4. Rename this file to `docs/v1.4-gate.md` and put v1.4 on the roadmap between v1.3 and D1.
