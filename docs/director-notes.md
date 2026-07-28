# director — status notes (not a gate)

`docs/v1.0-gate.md`, `v1.1-gate.md` and `v1.2-gate.md` each record a gate's evidence.
This document deliberately does not follow that pattern, because the director has no gate
to record. It sets down what the director is, what it demonstrably does, and the open
decision that has to be settled before it can be called a milestone.

## What it is

`tack.director.build_from_specs()` — the outer loop that makes "hand it spec docs and it
builds" work. It reads `*.md` from a spec directory, asks the LLM to decompose them into a
phased plan, executes each phase, checkpoints to `.tack/director-state.json` after every
phase (so a crash or Ctrl-C is resumable), and reports per-phase results.

```sh
uv run tack build specs/            # fresh build
uv run tack build specs/ --resume   # resume from checkpoint
```

It sits as a separate module above the core (`src/tack/director.py`), importing
`tack.core.loop` and `tack.adapters.base`; nothing under `src/tack/core/` imports it back,
so the rule that the core reaches only for the three adapter seams is intact.

## What is actually demonstrated

Reproduce: `uv run python examples/demo_director.py` (no API key needed — scripted brain,
`backend="tack"`). Excerpted, `…` marking elisions:

```
[director] backend: tack
…
[director] phase 01-fix-add: Fix the add function
[director] ✓ phase 01-fix-add done in 3 attempt(s) — verified
[director] phase 02-verify-clean: Verify final state
[director] ✓ phase 02-verify-clean done in 1 attempt(s) — verified
[director] all phases done — 2 completed, 0 failed
…
[director] build finished — 2/2 phases passed (0 failed) in Ns
overall   : ✓ PASS
phases    : 2 (2 passed)
```

So: multi-phase decomposition, per-phase execution through Tack's own loop, per-phase
verification, and the completion report all work against a scripted brain. 24 tests in
`tests/test_director.py` cover spec ingestion, plan generation, dependency ordering,
checkpoint/resume, and backend *resolution*.

**The Aider execution path has no test at all.** Every end-to-end test passes
`backend="tack"`; `_execute_phase_with_aider` is never called by the suite. The untested
path is the default one.

## Why this is not `docs/v1.4-gate.md`

Four reasons, in descending order of weight.

1. **The default backend leaks the API key into the sandbox.** `_execute_phase_with_aider`
   takes the key off the transport (`api_key=getattr(llm, "api_key", None)`), appends it
   to the Aider argv (`args.extend(["--openai-api-key", api_key])`), `shlex.quote`s the
   lot into a command string, and hands it to `execfs.run()`. Under the Karkhana adapter
   `execfs.run` *is* in-VM bash — so the key crosses into the VM on a command line, where
   it sits in the process table. That contradicts a locked, explicitly non-relitigable
   invariant stated in three places: `AGENTS.md:22`, `tack-VISION-AND-ROADMAP.md:50`
   (decision 6, "preserved"), `tack-HANDOFF.md:83` (rule 9) — **"Keys never enter the
   VM."** This is an architectural conflict, not a preference.
2. **The backend is chosen by auto-detection.** `_resolve_backend(None)` returns `"aider"`
   if `aider` is on `PATH` and `"tack"` otherwise. The engine behind `tack build`
   therefore depends on what happens to be installed on the machine — the same command
   runs a different agent for different users, with no flag in the CLI to pin it
   (`build_from_specs(backend=...)` exists; `tack build` does not expose it).
3. **The default backend can't ride into the deployment target.** D1 deploys the
   *unchanged* core into Karkhana's Alpine + Python 3.11 VM. Aider is an external runtime
   dependency, and the project's rule is zero of those precisely so the core drops in with
   nothing to install (`AGENTS.md:29`, `dependencies = []`). The image spec ships `pip`,
   so `pip install aider-chat` isn't impossible in principle — but a mid-task install
   needs egress the VM doesn't have until the owned network relay ships
   (`tack-VISION-AND-ROADMAP.md:87`, a Future item). So on the target the vision calls the
   defensibility centerpiece, the default backend is unavailable in practice.
4. **No live-model run.** Every other gate doc records mechanics proven against a scripted
   brain *and* names the live run it still owes. The director has the former and has never
   had the latter. Until 2026-07-28 it was also unreachable from the command line at all
   (see below).

The vision does list Aider among competing harnesses
(`tack-VISION-AND-ROADMAP.md:95`) — but that line sits under *Honest costs* and argues the
harness is not the moat, and the catalog already mines Aider for technique. So "shelling
out to a competitor" is **not** offered here as an argument; reasons 1–4 stand on their own.

## Fixed on 2026-07-28

Committed as part of repairing the landing, not as new work:

- `tack "task" --verify <cmd>` — restored; `--verify` had moved into the `build` subparser
  only, so single-task mode rejected it.
- `tack build specs/` — **was unreachable from a real shell.** `main()` tested
  `argv[0] == "build"` before resolving `argv` from `sys.argv`, and the console-script
  entry calls `main()` with `argv=None`. Every command-line invocation fell through to the
  single-task parser. No test exercised the CLI `build` route at all — `test_director.py`
  calls `build_from_specs()` directly — so the suite stayed green while the subcommand did
  not exist.
- `build_parser` — restored as a public alias after being renamed to a private name.
- The 7 ruff errors the director commit shipped — cleared.
- Two machine-dependent tests — `test_check_aider_available` and
  `test_resolve_backend_auto_prefers_aider` asserted Aider *was* on `PATH` (one docstring
  read "Aider is installed on the dev box"), so the suite failed on any machine without
  it. Both now monkeypatch the lookup, and the fallback branch got the test it never had.

## The open decision

**Is the director a v1.4 milestone, or an exploratory spike?** Six weeks of context was
lost between writing (2026-06-12) and committing (2026-07-28); it appears in neither
`tack-VISION-AND-ROADMAP.md`, `tack-HANDOFF.md`, nor the README roadmap, and was never in
`plan/pending.md`.

Recorded default, pending the author's call: **exploratory**, on the four grounds above.
If it is instead intended as v1.4, the smallest path to a real gate is:

1. **Fix the key leak first** — pass the key to Aider through the environment rather than
   the argv, or drop the Aider backend. Reason 1 is a blocker, not a preference, and it is
   the one item here that should be settled whatever the milestone decision.
2. Decide the backend question — most likely default `backend="tack"` and make Aider an
   explicit opt-in, since a machine-dependent default is the worst of the three options.
3. Expose `--backend` on `tack build` so the choice is visible and pinnable.
4. Give `_execute_phase_with_aider` its first test.
5. Do a live-model run of `tack build specs/` and record the transcript, as
   `docs/v1.{0,1,2}-gate.md` each do.
6. Rename this file to `docs/v1.4-gate.md` and put v1.4 on the roadmap between v1.3 and D1.
