---
name: ai-sdlc
description: >-
  Master end-to-end AI-SDLC pipeline skill. Activate whenever the user asks to
  run or use a Markdown feature/idea file through the AI-SDLC (e.g., "Use
  MyFeature.md through my AI-SDLC" or "Run docs/MyFeature.md through my AI-SDLC").
  Takes the input file from Stage 0 (Architecture & PRD) through Human Gate 0,
  QA BDD Spec & Human Gate 1 (SHA-256 lock), the Bounded Dev Triad loop
  (Enricher -> Fixer -> Evaluator, max 5 cycles), and Human Gate 2 (diff signoff).
---

# Master AI-SDLC End-to-End Pipeline Skill (Antigravity Command Centre)

When the user says:
> *"Use `MyFeature.md` through my AI-SDLC"* (or *"Run `<path>.md` through my AI-SDLC"*)

Execute the complete lifecycle below in order, **always pausing to ask the user for explicit input at every Human Gate** (use `ask_question` when available, or stop and wait for their reply).

---

## Stage 0 — Architecture & Specification Gate (Human Gate 0)
1. Read the user's input file (e.g., `MyFeature.md`).
2. Call `search_hybrid_rag` on `codebase-rag` to check whether `docs/prd.md`, `docs/adr/001-architecture-and-stack.md`, and `docs/backlog.md` already exist.
3. **DO NOT write application source code yet.**
   - If this is a new project, create `docs/prd.md`, `docs/adr/001-architecture-and-stack.md`, and `docs/backlog.md` from `MyFeature.md`.
   - If `docs/` already exists, update `docs/prd.md` and `docs/backlog.md` (and add a new ADR in `docs/adr/` if new architectural decisions are introduced) to incorporate `MyFeature.md`.
4. **🛑 PAUSE AT HUMAN GATE 0 — Ask the User for Input:**
   Present a concise summary of the created/updated blueprint files and ask the user:
   - **Approve & proceed to Stage 2 (QA BDD Spec)**
   - **Request changes to the architecture / PRD / backlog**
   - **Abort pipeline**
   Do NOT proceed until the user explicitly approves.

---

## Stage 1 — Local Memory Grounding & Physical AST Guardrails (Automatic)
- All downstream subagents query `codebase-rag` (`search_hybrid_rag` & `get_canonical_exemplar`) before planning or coding.
- Every `write_file` / `edit_file` is physically guarded by `.agents/hooks.json` (`pre_write_ast_gate.py`).

---

## Stage 2A — QA BDD Specification & Human Gate 1
1. Load `.agents/agents/qa-bdd-spec-agent.md` and spawn the **QA & BDD Spec Subagent** with `MyFeature.md` and the approved `docs/` context.
2. Present the drafted Gherkin `.feature` file and its edge-case summary directly to the user.
3. **🛑 PAUSE AT HUMAN GATE 1 — Ask the User for Input:**
   Ask the user:
   - **Approve BDD spec, lock SHA-256 hash & start the Dev Triad**
   - **Refine / add edge cases to the BDD spec** (if chosen, record any reusable rule via `record_rag_decision`, revise the `.feature` file, and re-ask Gate 1)
   - **Abort pipeline**
4. Once approved, **lock the `.feature` hash** so the Fixer can never weaken tests:
   ```bash
   python ai-automations/orchestration/triad_evaluator.py \
     --lock-feature tests/features/<FeatureName>.feature
   ```

---

## Stage 2B — Bounded Autonomous Dev Triad Loop (Max 5 Cycles)
Repeat for `cycle = 1..5`:
1. **Enricher Subagent (Read-Only):** Spawn using `.agents/agents/triad-enricher-agent.md`, passing the locked `.feature` path and any `last_failure_diagnostics` from the previous cycle. Receives a JSON implementation plan.
2. **Fixer Subagent (Write-Enabled):** Spawn using `.agents/agents/triad-fixer-agent.md`, passing the Enricher's JSON plan and locked `.feature` path.
3. **Evaluator Subagent (Deterministic Gatekeeper):** Spawn using `.agents/agents/triad-evaluator-agent.md` to execute `triad_evaluator.py` with the build and test commands from `docs/adr/001-architecture-and-stack.md`.
4. If `"all_green": true`, exit the loop and proceed to **Human Gate 2**.
5. If `"all_green": false` and `cycle < 5`, pass `last_failure_diagnostics` to the Enricher for Cycle `cycle + 1`.
6. If Cycle 5 fails, write `reports/triad/escalation-report.md` and **STOP** to ask the user for guidance.

---

## Stage 2C — Verified Diff Signoff (Human Gate 2)
1. Run `git diff --stat` and `git diff` and summarize:
   - Autonomous Triad cycles used
   - Gate-1 `.feature` SHA-256 integrity status & Tree-Sitter AST audit status
   - Build & BDD/unit test results
2. **🛑 PAUSE AT HUMAN GATE 2 — Ask the User for Input:**
   Ask the user:
   - **Approve diff & commit to Git**
   - **Request revisions (re-enter Triad loop with feedback & optionally record `#ai-pin`)**
   - **Abort (leave changes uncommitted in working tree)**
3. Only after explicit user approval, commit cleanly to Git.
