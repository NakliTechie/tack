# director — status notes (not a gate)

`docs/v1.0-gate.md`, `v1.1-gate.md` and `v1.2-gate.md` each record a gate's evidence.
This document deliberately does not follow that pattern, because the director has no gate
to record. It sets down what the director is, what it demonstrably does, and the one
remaining thing standing between it and a real gate.

## What it is

`tack.director.build_from_specs()` — the outer loop that makes "hand it spec docs and it
builds" work. It reads `*.md` from a spec directory, asks the LLM to decompose them into a
phased plan, executes each phase **through Tack's own `run_task` loop**, checkpoints to
`.tack/director-state.json` after every phase (so a crash or Ctrl-C is resumable), and
reports per-phase results.

```sh
uv run tack build specs/            # fresh build
uv run tack build specs/ --resume   # resume from checkpoint
```

It sits as a separate module above the core (`src/tack/director.py`), importing
`tack.core.loop` and `tack.adapters.base`; nothing under `src/tack/core/` imports it back,
so the rule that the core reaches only for the three adapter seams is intact.

There is exactly one execution path. An earlier version had a second — an Aider subprocess
selected by auto-detection — which was **deleted on 2026-07-28** (see below). What's left
is the director driving Tack's own engine, nothing else.

## What is actually demonstrated

Reproduce: `uv run python examples/demo_director.py` (no API key needed — scripted brain).
Excerpted, `…` marking elisions:

```
[director] phase 01-fix-add: Fix the add function
[director] ✓ phase 01-fix-add done in 3 attempt(s) — verified
[director] phase 02-verify-clean: Verify final state
[director] ✓ phase 02-verify-clean done in 1 attempt(s) — verified
[director] all phases done — 2 completed, 0 failed
[director] build finished — 2/2 phases passed (0 failed) in Ns
  ✓ 01-fix-add Fix the add function: completed (3t)
  ✓ 02-verify-clean Verify final state: completed (1t)
…
overall   : ✓ PASS
phases    : 2 (2 passed)
```

So: multi-phase decomposition, per-phase execution through Tack's loop, per-phase
verification, and the completion report all work against a scripted brain. 18 tests in
`tests/test_director.py` cover spec ingestion, plan generation, dependency ordering, and
checkpoint/resume.

## Why this is not `docs/v1.4-gate.md`

**One reason, now that the Aider backend is gone: it has never been run against a live
model, and has no gate log.** Every other gate doc records mechanics proven against a
scripted brain *and* names the live run it still owes; the director has the former and has
never had the latter. That run is key-blocked, like the v1.0 A11 baseline it would sit
next to.

That is the whole case. It is worth being precise about what *changed* here, because until
2026-07-28 the case against was much longer.

## What the Aider deletion removed

The director used to default to shelling each phase out to an `aider` subprocess, choosing
that over Tack's own loop by auto-detecting whether `aider` was on `PATH`. That carried
three objections that were **architectural, not just "unproven"** — and all three died
with the backend:

1. **Key-into-VM.** `_execute_phase_with_aider` put the API key on the aider argv
   (`--openai-api-key`) and handed it to `execfs.run()`, which under the Karkhana adapter
   is in-VM bash — so the key crossed into the VM, against the locked "Keys never enter
   the VM" invariant (`AGENTS.md:22`, `tack-VISION-AND-ROADMAP.md:50`, `tack-HANDOFF.md:83`).
2. **Machine-dependent engine.** Auto-detection meant `tack build` ran a different agent
   depending on what happened to be installed, with no CLI flag to pin it.
3. **Can't ride into the target.** Aider is an external runtime dependency, against the
   zero-dependency rule that lets the unchanged core drop into the Alpine+Python Karkhana
   VM at D1.

It also had **zero test coverage** despite being the default, and — being a
whole-task-per-attempt subprocess — produced nothing usable for the trajectory log
(Batch T), which is the actual keystone. Deleting it (−274 lines) collapsed the director
to its honest shape and moved it materially *closer* to gate-able: what blocked it was
mostly the backend, and the backend is gone.

## Also fixed earlier on 2026-07-28

Committed while repairing the director's landing, before the deletion:

- `tack "task" --verify <cmd>` — restored; `--verify` had moved into the `build` subparser
  only, so single-task mode rejected it.
- `tack build specs/` — **was unreachable from a real shell.** `main()` tested
  `argv[0] == "build"` before resolving `argv` from `sys.argv`, and the console-script
  entry calls `main()` with `argv=None`. No test exercised the CLI `build` route at all —
  `test_director.py` calls `build_from_specs()` directly — so the suite stayed green while
  the subcommand did not exist.
- `build_parser` — restored as a public alias after being renamed to a private name.

## The path to v1.4, if you want it

With the backend gone, one substantive step remains, plus a rename:

1. Do a live-model run of `tack build specs/` and record the transcript, as
   `docs/v1.{0,1,2}-gate.md` each do. (Key-blocked, alongside the A11 baseline.) This is
   the only real work left.
2. Rename this file to `docs/v1.4-gate.md` and put v1.4 on the roadmap between v1.3 and D1.

Until that run happens it stays exploratory — but now for the ordinary reason (unproven
against a live model), not an architectural one.
