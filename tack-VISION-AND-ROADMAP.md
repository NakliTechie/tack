# Tack — Vision & Roadmap

**Tack** is a portable coding-agent harness: the reasoning loop that drives a model through *plan → edit → verify → iterate → learn* toward passing tests. The name is the thesis — you can't sail straight into the wind, you converge on the target through repeated angled corrections. Tack can't one-shot a fix; it *tacks* toward green, correcting against ground truth each pass.

**Track:** NakliTechie research. Not commercial — not chasing the billion-dollar frontier harnesses. The goal is a good loop, learning, and one genuinely novel deployment. Default exit = discard; graduates only if a shape warrants it.

**Shape:** an environment-agnostic core behind three adapter seams. Built and tuned on a bare Linux dev box (fast iteration); deployed unchanged to constrained targets. The first novel target is **Karkhana** (browser-emulated Linux VM, zero-server, keys-never-in-VM) — but Karkhana is *a* deployment, not the project. Tack is the artifact.

---

## 1. Why engine-first

A harness is *tuned*, not designed — you find the iteration cap, compaction trigger, doom-loop threshold, and feedback format by running it hundreds of times and watching where it derails. Native, that loop is seconds. Inside a VM, every iteration pays a boot/serial/bridge tax *and* you can't tell a harness bug from an emulation artifact — debugging two systems at once, paced by the slow one.

So: build and tune native; deploy behind adapters.

**The payoff:** the abstractions a constrained target forces — swappable LLM transport, control channel, execution+FS — are exactly the seams that make a harness portable to *anything* (CI container, remote box, disposable VM, someone else's sandbox). The constraint, treated as an interface boundary, **hardens** Tack instead of nerfing it. Any nerf is then localized to an adapter and *visible*.

## 2. The bet (scoped honestly)

A good harness closes most of the gap between a cheap model and a frontier model **on verifiable tasks** — iteration-against-ground-truth beats raw IQ when ground truth is checkable. Coding is the canonical verifiable task.

- **Parity holds:** verifiable tasks (make this failing test pass). Cheap model + closed loop + real exit codes → frontier-class results.
- **Parity does NOT hold:** judgment tasks (is this architecture good?). Weak self-evaluator plateaus → escalate to frontier model.
- **Consequence:** cheap-by-default, frontier-on-escalation, ground-truth-as-arbiter. The boundary is a visible feature.

Anchor: mini-SWE-agent reaches >74% SWE-bench in ~100 lines — harness lift is large and model-size-independent.

**SWE-bench is an instrument, not a scoreboard.** Native run = loop-quality number. Same harness in a constrained deployment = the tax, measured as a delta. "Did the constraint nerf it?" becomes a number.

## 3. Architecture — core + three adapter seams

The core never knows which adapter is underneath.

| Seam | Interface (all the core sees) | Native adapter | Karkhana adapter |
|---|---|---|---|
| **LLM transport** | `complete(messages, opts) → response` | direct HTTPS, BYOK | file→fetch bridge, key injected browser-side, never in VM |
| **Control** | `cancel()`, `inject_task(t)` | stdin / signal / socket | serial console (Aj writes invisible post-boot) |
| **Execution + FS** | `run(cmd)→{out,err,exit}`; `read/write/edit(path)` | subprocess + real FS | in-VM bash + 9P-mounted FSA workspace |

Core (adapter-agnostic): 6-phase ReAct loop · 4 tools (read/write/edit/bash) · context engine (plan, conventions, compaction) · verification · safety/economics (cap, doom-loop, git-per-step) · two-layer learning. Tack's own state lives in **`.tack/`** in the workspace (real FS native; FSA-backed in Karkhana).

## 4. Locked decisions (do not relitigate)

1. **Sandbox-trust, not per-action gates.** Per-action approval is fatigue theater. Dangerous-command flag opt-in, OFF by default. (Sandbox = whatever the adapter runs in.)
2. **Self-extension, not a plugin ecosystem.** Agent writes its own bash tools to `.tack/bin/`. No ecosystem to host.
3. **Promotion-via-verification is the trust model.** Self-written tool starts *provisional*; outputs verified against ground truth before *promoted*. The untrusted author is the agent itself — true even with zero sharing.
4. **Learning is LOCAL.** No sharing transport, server, or telemetry. Two layers, on-device. Public dissemination = manual curation by the operator.
5. **Git-per-step.** Undo = `git reset`. Real git in every adapter; zero new browser surface.
6. **Keys never enter the VM.** A Karkhana-adapter invariant; preserved.
7. **Build & tune native first; deploy behind adapters.** One environment variable at a time.
8. **Prove the loop with the API brain before any local brain.** The local model is an adapter capability, not the loop.

## 5. Two-layer learning (local)

- **User-level (per-workspace):** conventions file, learned tools in `.tack/bin/`, repo playbook. Travels with the folder.
- **System-level (per-device):** cross-workspace playbook + self-knowledge (what works / anti-patterns that caused doom-loops). Flattens the curve — a new workspace boots already knowing common moves.
- **Public layer:** not a system feature. Operator hand-ports proven patterns. Methodology-share, not telemetry.

Learning is filesystem-based, so it's **portable across adapters** by construction — same `.tack/` whether native or in-VM.

## 6. Roadmap

Engine milestones built native (fast loop). Deployment to a constrained target is its own milestone, sequenced after the loop is good.

### v1.0 — Closed loop · native adapter · API brain
Core: 6-phase loop, 4 tools (ACI-disciplined feedback), context engine (plan + conventions + compaction), verification (run project test → exit code + stderr → loop back), safety/economics (cap, doom-loop, dangerous-cmd flag off, git-per-step). Native adapter only. API brain.
**Gate:** failing test → plan, edit real files, run test, read failure, fix, green, commit, stop — within cap, every step undoable. **Plus a SWE-bench-lite baseline number.**

### v1.1 — Self-extension + local learning (native)
Agent writes CLIs to `.tack/bin/` (provisional→verified→promoted); user-level + system-level playbooks; anti-pattern recording.
**Gate:** agent solves a task using a tool it wrote earlier; a known anti-pattern is avoided.

### v1.2 — Frontier escalation + observability (native)
Cheap-default → frontier-on-escalation (trigger: doom-loop or detected judgment task). Trace: step/plan/exit-code/iteration; per-step git log + revert.
**Gate:** a stuck cheap run escalates and completes; trace is legible.

### D1 — Karkhana deployment (the novel target)
Depends on Karkhana platform integrity (Handoff §2): Alpine+Python image as cached boot target; writes verified to land in FSA-backed workspace; serial control wired. Write the Karkhana adapter for all three seams; deploy the **unchanged core**.
**Gate:** v1.0 closed-loop gate passes inside Karkhana; report native-vs-Karkhana delta on the same task set.

### v1.3 — Local brain (per-adapter capability)
Native: Ollama/LM Studio endpoint. Karkhana: Transformers.js + WebGPU, Gemma 4 E4B, `<tool_call>` XML dual-mode parser (LocalMind pattern). Core unchanged — only the LLM-transport adapter differs.
**Gate:** closed-loop gate passes with a local brain, no API key — measured in both adapters.

### Future (own specs when reached)
- **Crate-backed workspace** — workspace over cloud storage; follows you cross-device; agent runs against a folder you're not in front of (bridge toward autonomous/Hermes). Where browser-side git may finally earn its place.
- **Owned network relay** — replace the public `wss://relay.widgetry.org/` with the Bridge primitive doing WS-to-TCP. Urgent once the agent must `apt/pip/npm install` mid-task.
- **MCP `ask_agent`** — expose the loop to external agents via Karkhana's Service Worker. The agent-face.
- **Multi-agent / Hermes-class** — planner/evaluator as distinct processes; trigger-driven runs. Coding (single agent) is the simpler first target.

## 7. Honest costs

- **Relaxes single-file-first — deliberately.** The portfolio is deployment-shape-first; Tack builds logic decoupled from shape, then wraps it. Correct *here* because the artifact is a reasoning loop, not a UI. Not a license for tools where shape is the moat.
- **Standalone harnesses are a crowded field** (Pi, mini-SWE-agent, OpenCode, Aider) — no shape-moat on quality alone. **Defensibility lives in the Karkhana deployment**: browser-native, zero-server, workshop-in-a-tab. Build the engine in the open where it's fast; the thing worth showing runs in the browser.
- **Research posture:** value = tech-literacy compounding + a deployment nobody else builds + portable seams as a reusable asset. Not market share.

## 8. Positioning
Aligned with Pi (primitives-not-opinions, malleable-as-clay, self-extending); sandbox-trusting, local-learning. The differentiator isn't the harness — it's that the *same* harness runs unchanged inside a browser tab with no server and no key exposure. The adapters are the contribution.
