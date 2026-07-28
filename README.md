# Tack

> A portable coding-agent harness: the reasoning loop that drives a model through *plan → edit → verify → iterate → learn* toward passing tests.

The name is the thesis — you can't sail straight into the wind, you converge on the target through repeated angled corrections. Tack can't one-shot a fix; it *tacks* toward green, correcting against ground truth each pass.

**Track:** NakliTechie research. Not commercial. The goal is a good loop, learning, and one genuinely novel deployment.

**Shape:** an environment-agnostic core behind **three adapter seams** (LLM transport · control · execution+FS). Built and tuned on a bare Linux dev box where iteration is fast; deployed *unchanged* to constrained targets. The first novel target is **Karkhana** (browser-emulated Linux VM, zero-server, keys-never-in-VM) — but Karkhana is *a* deployment, not the project. Tack is the artifact.

## Build order (non-negotiable)

Core + **native adapter** first, tuned on a bare Linux dev box. The Karkhana adapter and its platform-integrity work come *after* the loop is good (milestone D1). Do not start inside Karkhana — you'd debug the harness and the emulator at once.

## The three adapter seams

| Seam | Interface (all the core sees) | Native adapter | Karkhana adapter (D1) |
|---|---|---|---|
| LLM transport | `complete(messages, opts) → response` | direct HTTPS, BYOK | file→fetch bridge; key browser-side, never in VM |
| Control | `cancel()`, `inject_task(t)` | stdin / signal / unix socket | serial console only |
| Execution + FS | `run(cmd)→{stdout,stderr,exit}`; `read/write/edit(path)` | subprocess + real FS | in-VM bash + 9P-mounted FSA workspace |

Tack's own state lives in **`.tack/`** in the workspace.

## Roadmap

- **v1.0** — Closed loop · native adapter · API brain (6-phase ReAct loop, 4 tools, context engine, verification, safety/economics) — **built**
- **v1.1** — Self-extension + local learning (agent writes its own CLIs to `.tack/bin/`) — **built**
- **v1.2** — Frontier escalation + observability (cheap-default → frontier-on-stuck; legible trace) — **built**
- **D1** — Karkhana deployment (the novel target)
- **v1.3** — Local brain (Ollama native; Transformers.js + WebGPU in Karkhana)

### Exploratory — not a milestone

- **`director`** (`tack build specs/`) — an outer loop that decomposes spec documents into a phased build plan and drives each phase to green, with checkpoint/resume. Written 2026-06-12, committed 2026-07-28. It is **not** on the roadmap above and has **not** passed a gate. It picks its execution backend by auto-detection — an [Aider](https://github.com/Aider-AI/aider) subprocess when `aider` is on `PATH`, Tack's own `run_task` loop otherwise — which makes the engine behind `tack build` machine-dependent, leaves the default path untested, and puts the API key on the Aider argv handed to `execfs.run`, i.e. **into the VM** under the Karkhana adapter, against a locked invariant. Treat it as a spike pending a decision, not a feature. See **[docs/director-notes.md](docs/director-notes.md)**.

## Handoff documents

This repo was scaffolded from a three-document handoff pack:

- **[tack-HANDOFF.md](tack-HANDOFF.md)** — the implementing agent's brief: adapter seams, v1.0 spec, gates, hard NOT-to-do rules, escalation protocol.
- **[tack-VISION-AND-ROADMAP.md](tack-VISION-AND-ROADMAP.md)** — why engine-first, the parity bet, locked decisions, milestone roadmap, honest costs.
- **[tack-harness-catalog-and-distillation.md](tack-harness-catalog-and-distillation.md)** — landscape survey of open-source coding-agent harnesses (Pi, SWE-agent, OpenHands, Aider, OpenCode…), technique audit, and the adopt/adapt/reject distillation that produced this design.

## Status

**v1.0 built (native adapter, harness mechanics proven).** The closed loop runs end to end on a real broken project — failing `pytest` → read → edit → the loop's own verification flips green — over a real filesystem, subprocess, and git, every step committed and undoable. The live-model run and the SWE-bench-lite baseline number (A11) are deferred until a `BYOK` key is wired; everything else is implemented and tested.

```
src/tack/
├─ adapters/base.py     # the three seams (Protocols) — the only thing the core sees
├─ adapters/native.py   # native adapter: HTTPS BYOK · in-proc control · subprocess+FS
└─ core/
   ├─ loop.py           # 6-phase ReAct; run_task() is the callable entry (not a REPL)
   ├─ tools.py          # the 4 tools (read·write·edit·bash), ACI-disciplined feedback
   ├─ context.py        # .tack/plan.md + AGENTS.md injection + progressive compaction
   ├─ verify.py         # discover + run the project's check; exit code is the arbiter
   └─ safety.py         # iteration cap · doom-loop · dangerous-cmd flag · git-per-step
```

### Quickstart

```sh
uv sync --extra dev          # dev env (CPython 3.11, pytest, ruff)
uv run pytest                # the suite, incl. the closed-loop gate
uv run python examples/demo_closed_loop.py   # watch the loop fix a bug (no API key needed)

# against a real model (BYOK):
OPENAI_API_KEY=sk-... uv run tack "make the failing test pass"
```

Or call it as a function — the agent face is a function, not a REPL, so the future MCP `ask_agent` surface is a thin wrapper:

```python
from tack import run_task, Config
from tack.adapters.native import native_adapters

res = run_task("fix the bug in calc.py",
               native_adapters(workspace="."), workspace=".")
print(res.success, res.stop_reason, res.turns)
```

**v1.0, v1.1, and v1.2** are built and mechanics-proven — see the gate logs ([v1.0](docs/v1.0-gate.md), [v1.1](docs/v1.1-gate.md), [v1.2](docs/v1.2-gate.md)). Next is **D1** (the Karkhana browser-VM deployment — the novel target) or **v1.3** (local brain). The live-model validation and the SWE-bench-lite baseline (A11) wait on a BYOK key.

## License

[MIT](LICENSE) — the field default (Pi-core, OpenCode, OpenHands, SWE-agent all MIT), clean to embrace-and-extend if Tack ever graduates.
