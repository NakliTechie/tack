# Tack — Landscape, Harness Audit & Distillation

**Purpose:** Survey the open-source coding-agent and autonomous-agent field, audit the harness techniques each one contributes, and distill Tack — a harness that fits NakliTechie's shape (single-file, zero-server, primitives-not-opinions, agent-face). Driven by the Karkhana closed-loop work — this catalog is the "do it once, properly" alternative to discovering harness patterns iteratively.

**Provenance note:** Built entirely from published sources (project docs, papers, author essays, Anthropic's open harness engineering writeups). The leaked Claude Code source was deliberately NOT used — contaminated provenance is disqualifying for anything that may go commercial, and the techniques are documented openly anyway.

---

## Part 1 — The Landscape

### Tier A — Reference harnesses to study closely

| Project | License | Shape | Why it matters for us |
|---|---|---|---|
| **Pi** (badlogic/pi-mono) | MIT (core) | Minimal terminal agent, 4 tools, sub-1k-token system prompt, self-extending | **Closest prior art to NakliTechie philosophy.** Primitives not opinions; agent extends itself rather than installing plugins. The harness to beat/learn from. |
| **SWE-agent / mini-SWE-agent** | MIT | Autonomous issue-solver; ACI concept | **The ACI thesis** (agents are a new class of end-user needing purpose-built interfaces) is the single most important design idea in the field. mini variant: >74% SWE-bench in ~100 lines. |
| **OpenHands** (All Hands AI) | MIT | Autonomous platform; event-stream architecture; Docker sandbox; multi-agent | Production autonomous shape. Event stream + sandbox isolation + multi-agent delegation. The Hermes-class reference. |
| **Aider** | Apache-2.0 | Git-native interactive terminal pair-programmer | Best-in-class **git discipline** and **repo-map** context selection. Surgical edit formats. |
| **OpenCode** (sst) | MIT | Provider-agnostic TUI, ~165k stars, de facto default | The mainstream baseline; client/server split; 75+ providers; plan+execute agents. What "normal" looks like. |

### Tier B — Worth a targeted look for specific techniques

| Project | License | Single technique to harvest |
|---|---|---|
| **Cline** | MIT | Plan/Act mode separation; in-editor diff approval UX |
| **Goose** (Linux Foundation) | Apache-2.0 | Extension/recipe system; general automation beyond code |
| **Codex CLI** (OpenAI) | Apache-2.0 | Default shell sandboxing; restricted execution model |
| **Continue** | Apache-2.0 | Context provider abstraction (pluggable context sources) |
| **Crush** (Charm) | FSL→MIT | TUI rendering quality; session UX |
| **Terminus** | — | Radical ACI: only sends keystrokes to tmux, reads VT sequences — topped TerminalBench. Proves minimal interface can win. |

### Tier C — Autonomous / orchestration layer (Hermes-class)

| Project | Shape | Technique to harvest |
|---|---|---|
| **OpenHands Cloud** | Trigger→sandbox→agent→PR orchestration | The "agent is a piece of the loop, not the loop" architecture |
| **Hive** (aden-hive) | Multi-agent harness, graph-based, self-evolving | Session isolation, checkpoint crash recovery, cost enforcement, intervention nodes |
| **Tembo-style background platforms** | Signal-driven (Sentry/Linear/Slack → agent run) | Trigger ownership; the orchestration layer that *wraps* a coding agent |
| **OpenClaw** (built on Pi) | Personal assistant via RPC over Pi | Self-managing agent that writes its own bash/CLI tools per task |

### Field dynamics worth knowing (context, not technique)
- The center of gravity in 2026 is "frontier model + managed harness." Open harnesses (OpenCode, Pi, Aider, Goose) hold the BYOK/local-model/provider-agnostic niche — **exactly NakliTechie's niche.**
- Ecosystem is volatile: Gemini CLI retired, Roo Code archived, Goose handed to Linux Foundation, Pi acquired by Earendil 67 days after a blog endorsement. Governance/licensing churn is the norm — argues for owning your harness rather than depending on one.
- Licensing matters if we ever commercialize: MIT (OpenCode, Pi-core, OpenHands, SWE-agent, Cline) is clean to embrace-and-extend; FSL/AGPL (Crush, Warp) needs care.

---

## Part 2 — Harness Technique Audit

The cross-project distillation of what a harness actually *does*, grouped by subsystem. This is the menu we choose from.

### 2.1 The core loop (ReAct, refined)
Six phases seen across mature harnesses (arxiv terminal-agent paper, Anthropic harness post):
1. **Pre-check + compaction** — is context near full? compact before thinking.
2. **Think** — reason about next action.
3. **Self-critique** — review the planned action before executing (cheap, catches obvious errors).
4. **Act** — emit tool call.
5. **Tool execution** — dispatch to handler, capture result.
6. **Post-process** — fold result into context, decide continue/stop.

### 2.2 Context engineering (the highest-leverage subsystem)
- **Filesystem as memory** — the agent's working memory lives in files (plan.md, AGENTS.md), not just context. Each iteration starts clean and reads prior state from disk. *This is the primitive that turns single-session into multi-session.*
- **Progressive compaction** — multi-stage summarization as the window fills; never let the API error. "Context rot": quality degrades as window fills, so manage it actively.
- **Dynamic context pull** — Cursor's evolution: stop front-loading static context, give the agent tools to fetch context as it works (repo map, semantic search, file reads on demand).
- **Repo map** (Aider) — a compressed structural map of the codebase so the agent knows what exists without reading everything.
- **AGENTS.md / CLAUDE.md standard** — project conventions injected every session start; agent can edit it → crude continual learning.

### 2.3 The Agent-Computer Interface (ACI) — SWE-agent's core thesis
> Agents are a new class of end-user. A raw Linux shell was designed for humans. Purpose-built commands and feedback formats dramatically outperform raw shell access.
- **LM-centric commands** — not `sed`/`awk`, but `edit`, `view`, `search` designed for how a model thinks.
- **Feedback format discipline** — structured, concise tool output (truncate noise, surface the signal). Bad ACI feedback = context rot.
- **Guardrails in the interface** — e.g. edit command that lints before applying and rejects malformed edits, so the model gets immediate correction.

### 2.4 Planning & decomposition
- **Plan file on disk** — decompose goal → ordered steps, written to disk, updated as steps complete.
- **Plan/Act separation** (Cline) — distinct planning phase before execution; can require human approval at the plan boundary.
- **Planner/generator/evaluator split** — Anthropic explicit: separate generation from evaluation into distinct agents. Self-evaluation skews positive (agents grade their own work too kindly).

### 2.5 Verification & feedback loops
- **Self-verification via test suite** — hooks run a predefined test suite; failures loop back as error text. (Karkhana's payoff — real Linux = real exit codes.)
- **Criteria-based review** — when no test exists, model reviews output against explicit written criteria.
- **Error-text-as-context** — the actual stderr/exit code fed back is the closed-loop signal.

### 2.6 Safety & loop control (the "don't let it go insane" layer)
From the arxiv harness breakdown — independent layers:
- **Approval gating** — human confirms dangerous ops. *(But see Pi's counter-argument below.)*
- **Dangerous-command detection** — pattern-match destructive commands pre-execution.
- **Stale-read detection** — agent acting on outdated file state.
- **Doom-loop detection** — same error/action repeated N times → stop.
- **Iteration cap** — hard ceiling on turns.
- **Cooperative cancellation** — clean stop mid-run.
- **Per-step undo via git snapshots** — every step is a commit; bad step = `git reset`.

**The Pi counter-argument (important tension to resolve):** Pi runs "YOLO mode" by default — no approval gates. Argument: approval fatigue makes users either disable gates or mindlessly approve → security theater. Pi's answer is sandbox isolation instead of per-action approval. **This is a real fork:** gate-per-action (Claude Code/Cline) vs sandbox-and-let-it-run (Pi/OpenHands/SWE-agent). For Karkhana, the VM *is* the sandbox — which points toward the Pi/sandbox model, not per-action gates.

### 2.7 Tools — the minimal set
Convergent finding across minimal harnesses: **4 tools suffice** — `read`, `write`, `edit`, `bash`. Pi proves it; Terminus proves even less (just keystrokes) can top a benchmark. Everything else is composable from bash. Implication: don't build 20 tools; build 4 good ones + let the agent write its own.

### 2.8 Extensibility model (the philosophical divide)
- **Plugin/MCP model** — download someone's extension. Problem (Pi's critique): MCP tools must load into system context at session start; can't hot-reload without trashing cache.
- **Self-extension model** (Pi) — agent writes its own tools/CLIs on demand. "Software malleable like clay." You don't download an extension; you ask the agent to build one, or point it at an existing one to copy-and-modify.
- **Hybrid** — support extensions but default to self-extension.

### 2.9 Multi-session / continual learning
- **Shift-handoff problem** (Anthropic) — each session starts with no memory; need to bridge the gap. Compaction alone is insufficient.
- **Strategy memory / playbook** — persistent record of what worked, read at session start.
- **Session storage** — sessions.db or equivalent; resumable.
- **Self-authored issue tracker** (Pi/Mom) — agent maintains its own local to-do list.

### 2.10 Autonomous-specific (Hermes-class, beyond coding)
- **Trigger ownership** — orchestration layer owns the signal (Sentry alert, Linear ticket, cron) → invokes agent → owns the PR. Agent is a component in a distributed system.
- **Session isolation** — each run its own container/sandbox.
- **Checkpoint crash recovery** — resume from last good state.
- **Cost enforcement + timeouts** — hard budget per run.
- **Intervention nodes** — pause for human input with configurable timeout/escalation.
- **Self-tool-installation** — agent installs jq/git/etc. itself in its sandbox (Mom pattern).

---

## Part 3 — Distillation: A NakliTechie Agent Harness

### 3.1 The shape constraint (what makes ours different)
Every existing harness assumes a real OS with a real shell and (usually) a server or cloud. Ours is built to run **both** on a bare Linux dev box (where it's tuned, because iteration is fast) **and** inside a browser-emulated Linux VM (Karkhana — the novel, zero-server, keys-never-in-VM deployment). The harness core is environment-agnostic and talks only to three adapter seams (LLM transport, control, execution+FS); Karkhana is the most-constrained adapter, not the project. Treating the constraint as an interface boundary rather than a host is what *hardens* the agent (portable to CI, remote box, disposable VM) instead of nerfing it.

**Philosophical alignment is with Pi, not Claude Code.** Pi's "primitives not opinions / malleable as clay / agent extends itself" is the same worldview as NakliTechie's. Sandbox-trusting (the sandbox is whatever the adapter runs in), local-learning, ACI-disciplined.

**Research track, not a competitor.** Not chasing the leaderboard — SWE-bench is a measuring instrument (loop quality native; deployment tax as the native-vs-Karkhana delta). Value = tech-literacy compounding + a deployment nobody else builds + portable seams as a reusable asset.

### 3.2 What we ADOPT

| Technique | Source | Why it fits |
|---|---|---|
| **4-tool minimal set** (read/write/edit/bash) | Pi, Terminus | Matches single-file constraint; less to build, less to break; bash composes the rest |
| **ACI feedback discipline** | SWE-agent | Structured, truncated tool output is critical when context is scarce and the brain may be a small local model |
| **Filesystem-as-memory** (plan.md, AGENTS.md) | Anthropic, Pi | Karkhana already has a real persistent FS — this is nearly free, and it's the multi-session unlock |
| **Self-verification via real test suite** | Anthropic, SWE-agent | Karkhana's whole reason to exist — real Linux = real exit codes |
| **Error-text-as-context loop** | universal | The closed loop |
| **Doom-loop detection + iteration cap** | arxiv harness | Cheap, essential, pure agent-side software |
| **Git-per-step undo (in-VM)** | arxiv harness | Real git in the VM; zero new browser surface |
| **Sandbox-trust safety model** (not per-action gates) | Pi, OpenHands | The VM *is* the sandbox; per-action approval would be the fatigue theater Pi warns about |
| **Self-extension over plugins** | Pi | Agent writes its own bash tools; matches "no plugin ecosystem to host" |
| **Progressive compaction** | Anthropic, Cursor | Mandatory once tasks exceed one window; small local models have small windows → urgent |

### 3.3 What we ADAPT (technique is right; the **Karkhana adapter** changes the mechanism — the native adapter keeps the standard one)

These are adapter concerns, not core concerns. The core calls the standard interface; the Karkhana adapter swaps the mechanism behind it.

| Technique | Standard / native mechanism | Karkhana-adapter mechanism |
|---|---|---|
| **Control channel** (cancel, inject task) | stdin / signal / socket | **Serial console** — Aj writes invisible post-boot in Karkhana's 9P-root |
| **LLM call** | Direct HTTPS from agent | **File→fetch bridge** — agent writes request to file, browser fetches, key injected browser-side, never in VM |
| **Multi-session storage** | `.tack/` on real FS | **FSA-backed `.tack/`** — survives reload, follows the folder; Crate-backed later for cross-device |
| **Local-model tool calls** | native tool-calling API (Ollama) | **`<tool_call>` XML parsing** — WebGPU Gemma emits text blocks, not OpenAI tool_calls (LocalMind parser) |
| **Planner/evaluator split** | two processes/containers | **One agent, two passes** initially (full split deferred) — process isolation is expensive in a single VM |

### 3.4 What we DEFER or REJECT

| Technique | Verdict | Reason |
|---|---|---|
| MCP-as-primary-extension | **Defer** | Pi's critique (cache-trashing on reload) + we already expose MCP *outward* (Service Worker) — inward MCP is Future, not a v1.x line |
| Multi-agent orchestration | **Defer** | Hermes-class; coding agent is the simpler first target (you said this). One agent first. Future track. |
| Cloud sandbox per run | **Reject (for core)** | Violates zero-server. The VM is the sandbox. Lives only in a future commercial/Crate-backed track. |
| Per-action approval gates | **Reject (as default)** | Sandbox-trust model instead. Optional toggle for the nervous, off by default. |
| Repo-map semantic index | **Defer** | Valuable (Aider) but heavy; v1.0 uses bash `grep`/`find` via ACI, semantic map is a later v1.x/Future call |
| 20-tool kitchen sink | **Reject** | 4 tools + self-extension. Permanent. |

### 3.5 Proposed architecture (the distilled harness)

```
NakliTechie Agent Harness  (env-agnostic core + adapters; native dev + Karkhana deploy)
│
├─ Core loop (ReAct, 6-phase)
│    pre-check/compact → think → self-critique → act → execute → post-process
│
├─ Tools (4)        read · write · edit · bash      ← ACI-disciplined feedback
│    └─ self-extension: agent writes new CLIs to .tack/bin/
│
├─ Context engine
│    ├─ plan.md           (decomposition, updated per step)
│    ├─ AGENTS.md         (project conventions, injected each session)
│    ├─ playbook.md       (strategy memory across sessions)
│    └─ progressive compaction (multi-stage, window-aware)
│
├─ Verification
│    └─ run project's own test cmd → capture exit code + stderr → loop back
│
├─ Safety / loop control
│    ├─ iteration cap
│    ├─ doom-loop detection (repeated error/action)
│    ├─ dangerous-command flag (optional gate, off by default)
│    └─ git-per-step → undo = git reset
│
├─ Session state → .tack/  (real FS native; FSA-backed in Karkhana; Crate later)
│
└─ THREE ADAPTER SEAMS  (the only env-specific code)
     ├─ LLM transport   native: HTTPS BYOK      │ Karkhana: file→fetch, key browser-side
     ├─ Control         native: stdin/signal    │ Karkhana: serial console
     └─ Execution+FS    native: subprocess+FS   │ Karkhana: in-VM bash + 9P/FSA
```

### 3.6 The two design forks — RESOLVED
1. **Safety model → sandbox-trust (locked).** The VM is the sandbox; per-action gates are the fatigue theater Pi documents. Dangerous-command flag opt-in, OFF by default.
2. **Extension model → self-extension (locked).** Agent writes bash tools to `.tack/bin/`; MCP-in deferred. No ecosystem to host.

### 3.7 Learning model — RESOLVED: LOCAL only
- **Two layers, both on-device:** user-level (per-workspace: AGENTS.md, learned tools, repo playbook) + system-level (per-device: cross-workspace playbook + self-knowledge of what works / anti-patterns).
- **No sharing transport.** No server (betrayal shape), no git-substrate, no mesh — for now. Audience self-selected against broadcasting agent activity; opt-in-shared would ship a feature most would never toggle.
- **Public dissemination is manual curation by the operator** — proven patterns hand-ported to public docs/pattern files. Methodology-share, not telemetry.
- **Promotion-via-verification still required even with zero sharing** — because the untrusted author is the agent itself. A cheap model self-extending can write a subtly-broken tool and lean on it for 40 turns. Provisional → verified-against-ground-truth → promoted is the code review the human isn't doing.

### 3.8 The economic engine (frontier-parity thesis, scoped)
- **Cheap-by-default, frontier-on-escalation, ground-truth-as-arbiter.**
- Parity holds on **verifiable tasks** (test passes or doesn't) — iteration against ground truth beats raw IQ. Does NOT hold on **judgment tasks** (architecture/API taste) — weak self-evaluator plateaus below frontier → escalate.
- Doom-loop detection + iteration cap are **economic** features here, not just safety: a cheap-model doom-loop can cost more than one frontier call. "Cheap" is only cheap if the loop is short and self-terminating.
- Lean on the test suite as evaluator over model self-assessment wherever ground truth exists (self-eval skew is worse on small models).

### 3.7 Relationship to the Karkhana closed-loop outline
This framework *is* the harness layer of that outline's Phase 1, specified properly. The outline says "build a closed loop"; this says "here is the distilled-from-the-field design of that loop, and here's what to adopt/adapt/reject and why." Phase 0 (platform integrity) is unchanged and still precedes all of this.

---

## Part 4 — What still needs the deep dive (Research handoff candidates)
This catalog is built from docs, papers, and author essays. The next level — reading the *actual harness source* of each Tier-A project — is where a Research task earns its keep. Specifically:
- **Pi (badlogic/pi-mono)** — read the actual core loop + the 4 tool implementations + the self-extension mechanism. This is the most important single read; it's our closest cousin.
- **SWE-agent** — read the ACI command definitions and feedback formatting code (the `edit`/`view` tools specifically).
- **mini-SWE-agent** — the ~100-line version; if it hits 74% SWE-bench, its loop is the irreducible core. Read it whole.
- **OpenHands** — read the event-stream + sandbox isolation code (for the eventual Hermes/autonomous track, not v1).
- **Anthropic Agent SDK** — the published compaction implementation specifically.

Each is a 1–3 hour source read. Five of them = a clean Research task. Bring the findings back and we tighten Part 3 into a build-ready harness spec.
