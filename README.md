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

- **v1.0** — Closed loop · native adapter · API brain (6-phase ReAct loop, 4 tools, context engine, verification, safety/economics)
- **v1.1** — Self-extension + local learning (agent writes its own CLIs to `.tack/bin/`)
- **v1.2** — Frontier escalation + observability
- **D1** — Karkhana deployment (the novel target)
- **v1.3** — Local brain (Ollama native; Transformers.js + WebGPU in Karkhana)

## Handoff documents

This repo was scaffolded from a three-document handoff pack:

- **[tack-HANDOFF.md](tack-HANDOFF.md)** — the implementing agent's brief: adapter seams, v1.0 spec, gates, hard NOT-to-do rules, escalation protocol.
- **[tack-VISION-AND-ROADMAP.md](tack-VISION-AND-ROADMAP.md)** — why engine-first, the parity bet, locked decisions, milestone roadmap, honest costs.
- **[tack-harness-catalog-and-distillation.md](tack-harness-catalog-and-distillation.md)** — landscape survey of open-source coding-agent harnesses (Pi, SWE-agent, OpenHands, Aider, OpenCode…), technique audit, and the adopt/adapt/reject distillation that produced this design.

## Status

Scaffolded — design pack locked, no code yet. Next is **v1.0**: define the three adapter seams, write the core against them, write the native adapter, and drive a failing test to green within an iteration cap.
