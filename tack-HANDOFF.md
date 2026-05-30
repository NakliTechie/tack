# Tack — Agent Handoff

**For:** the implementing coding agent (Claude Code). **Companion:** `tack-VISION-AND-ROADMAP.md`. **Reasoning:** `tack-harness-catalog-and-distillation.md`.

**Build order (non-negotiable):** core + **native adapter** first, tuned on a bare Linux dev box. The Karkhana adapter + its platform-integrity work (§2) come *after* the loop is good (milestone D1). Do not start inside Karkhana — you'd debug the harness and the emulator at once.

**Governing rule:** the core is environment-agnostic and talks only to the three adapter interfaces (§1). Nothing target-specific leaks into the core. If you're writing serial/9P/file-bridge logic in the loop, stop — it belongs in an adapter. Tack's state lives in **`.tack/`** in the workspace.

---

## 1. The three adapter seams (define these first)

| Seam | Interface (all the core sees) | Native adapter | Karkhana adapter (built at D1) |
|---|---|---|---|
| LLM transport | `complete(messages, opts) → response` | direct HTTPS, BYOK | file→fetch bridge; key injected browser-side, never in VM |
| Control | `cancel()`, `inject_task(t)` | stdin / signal / unix socket | serial console only (Aj writes invisible post-boot) |
| Execution + FS | `run(cmd)→{stdout,stderr,exit}`; `read/write/edit(path)` | subprocess + real FS | in-VM bash + 9P-mounted FSA workspace |

Write the core against these. Write the native adapter. Defer the Karkhana adapter to D1.

## 2. Karkhana platform integrity (PREREQUISITE for D1 ONLY — not for v1.0)

Karkhana-specific; do at deployment, not before. Listed here because it's easy to mis-sequence.

### 2.1 Commit Alpine+Python as cached boot target
Close the Buildroot-vs-Alpine fork (Karkhana's ROADMAP ships Buildroot 6.8 no-Python; its NEXT-SESSION runs Alpine 3.18 + Python 3.11). Build Alpine bzImage via Docker (`tools/docker/alpine/`): python3, pip, sqlite3, coreutils, **git**. Replace image URL; cache in IndexedDB.
**Gate:** fresh cached boot → Alpine shell with python3, git, pip on PATH.

### 2.2 Workspace-write integrity (job zero for D1)
Agent working dir must be FSA-backed workspace; writes hit the real host folder. Fix chmod/execute-bit timing (9P drops execute bits; serial chmod races visibility).
**Gate (mount-is-real):** agent writes file → appears in host folder on disk → edit on host → visible in VM. Bidirectional.

### Two facts to confirm against the Karkhana repo before the port
1. Current agent + bridge source (the Python heredoc + JS `executeRequest`/`executeLocal`, inlined in `index.html`) — the Karkhana adapter is a diff against these.
2. When the existing agent wrote a file: did it land in the picked host folder, or only in the VM? Cosmetic-sidebar-bug vs job-zero-mount-broken hinges on this.

## 3. v1.0 — Closed loop (native adapter, API brain)

Native adapter only. API brain (e.g. GPT-4o-mini path). No local model (v1.3). No Karkhana (D1).

### 3.1 Core loop — 6-phase ReAct
`pre-check/compact → think → self-critique → act → execute → post-process`. Multi-turn; state persists within a task.

### 3.2 Tools — exactly 4
`read`, `write`, `edit`, `bash`, all via the Execution+FS adapter. ACI-disciplined feedback: structured, truncated, signal-not-noise. Do NOT add a 5th — bash composes the rest; the agent self-extends (v1.1).

### 3.3 Context engine
- `.tack/plan.md` — goal → ordered steps; updated per step; re-read each turn.
- `AGENTS.md` — project conventions injected each session start.
- Progressive compaction — multi-stage; never let the LLM call error on context.

### 3.4 Verification (the whole point)
Run the project's own verify command via the exec adapter (`pytest`, `python3 main.py`, …). Discover: read `.tack/verify` if present; else infer; else ask. Capture stdout + stderr + **exit code**. exit 0 → advance; non-zero → feed the actual error text into the next turn. This feedback IS the loop.

### 3.5 Safety / economics
- **Iteration cap** — hard ceiling; stop + report.
- **Doom-loop detection** — same error/action N times → stop. (Cheap-model doom-loop can cost more than one frontier call — economic, not just safety.)
- **Dangerous-command flag** — pattern-match destructive cmds pre-execution. Default OFF (sandbox-trust); opt-in.
- **Git-per-step** — commit per step via exec adapter; bad step → `git reset --hard`.

### 3.6 Control
Via the Control adapter: `cancel()`, `inject_task()`. Native = stdin/signal/socket. Do NOT assume serial in the core.

**v1.0 GATE:** failing test → plan, edit real files, run test, read failure, fix, green, commit, stop — within cap, every step undoable, watched end to end. **Plus:** run SWE-bench-lite (or a small fixed task set) and record the pass number — the baseline the D1 tax is measured against.

## 4. D1 — Karkhana deployment
Complete §2. Implement the Karkhana adapter for all three seams (§1, right column). Deploy the **unchanged core** — if the core needs editing to run in Karkhana, the seam abstraction failed; fix the seam, not the core. In-browser surfacing minimum: stream agent output to terminal/sidebar; reuse existing Karkhana dark scheme/toasts/panels (no new design language).
**Gate:** v1.0 closed-loop gate passes inside Karkhana; report native-vs-Karkhana delta on the same task set.

## 5. Persistence rules
- ALLOW: `.tack/` for plan, playbooks, session state, learned tools (real FS native; FSA-backed in Karkhana). localStorage for BYOK keys is a Karkhana-adapter detail, browser-side only.
- FORBID: keys inside the VM; any browser storage API inside artifact-rendered code; a file-drop control channel in Karkhana (serial only).

## 6. Hard NOT-to-do rules
1. Do NOT build inside Karkhana first. Native + tuned, then deploy.
2. Do NOT leak serial/9P/file-bridge specifics into the core. Adapters only.
3. Do NOT touch Karkhana's emulator, 9P bridge, FSA layer, key-isolation, or MCP-out — they work.
4. Do NOT build a file-drop browser→VM control channel. Serial only (Karkhana adapter).
5. Do NOT introduce a local model in v1.0. API brain first; one variable at a time.
6. Do NOT add tools beyond the 4. Self-extension (v1.1) covers the rest.
7. Do NOT add per-action approval gates as default. Sandbox-trust.
8. Do NOT auto-trust agent-self-written tools — provisional→verified→promoted (v1.1).
9. Keys NEVER enter the VM.
10. Do NOT use any leaked proprietary source. Clean-room only.

## 7. Escalation protocol
Proceed autonomously on: internal naming, implementation choices, debugging, alternatives. Stop and ask ONLY for: locked-decision conflicts (Vision §4), new dependency needs, scope ambiguity that changes the product, expensive-to-reverse architecture. Gate on large chunks (per milestone), never step-by-step.

## 8. Gate artifacts
- **v1.0:** closed-loop recording/log + SWE-bench-lite number.
- **v1.1:** task solved with a self-written tool; anti-pattern avoided.
- **v1.2:** escalation trace.
- **2.1:** Alpine shell with python3+git+pip. **2.2:** bidirectional VM↔host file visibility.
- **D1:** Karkhana closed-loop log + native-vs-Karkhana tax delta.

## 9. Standing question
**What's the agent face?** The loop must be callable, not only interactive, so the future MCP `ask_agent` surface (external agents fire tasks at Tack) is cheap to add. Keep the core's entry point a function, not a REPL.
