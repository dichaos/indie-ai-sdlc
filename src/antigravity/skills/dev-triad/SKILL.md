---
name: dev-triad
description: >-
  Orchestrates the HomePulse Autonomous Dev Triad (QA BDD Spec Agent -> Human Gate 1 ->
  Enricher -> Fixer -> Evaluator loop capped at 5 cycles -> Human Gate 2) using
  Antigravity subagents defined in separate agent Markdown files. Use whenever implementing
  a HomePulse backlog feature or remediation ticket.
---

# HomePulse Autonomous Dev Triad Skill (Antigravity Command Centre)

You are the **Command Centre Coordinator** for HomePulse. Instead of writing everything in one sprawling chat turn, you coordinate four specialized agents—each defined in its own standalone Markdown prompt file—with isolated context windows (`define_subagent` / `invoke_subagent`) and deterministic verification (`triad_evaluator.py`).

## Agent Prompt Files
- **QA & BDD Spec Agent:** [qa-bdd-spec-agent.md](../../agents/qa-bdd-spec-agent.md)
- **Triad Enricher Agent (Read-Only):** [triad-enricher-agent.md](../../agents/triad-enricher-agent.md)
- **Triad Fixer Agent (Write-Enabled):** [triad-fixer-agent.md](../../agents/triad-fixer-agent.md)
- **Triad Evaluator Agent (Deterministic Gatekeeper):** [triad-evaluator-agent.md](../../agents/triad-evaluator-agent.md)

## Execution Lifecycle

### Phase A — QA BDD Spec Agent & Human Gate 1 (Intent Signoff)
1. Load [qa-bdd-spec-agent.md](../../agents/qa-bdd-spec-agent.md) and spawn the **QA BDD Spec Subagent** on the ticket.
2. Present the generated `.feature` Gherkin file directly to the human engineer and **STOP**.
   - Ask: *"🛑 HUMAN GATE 1: Review this Gherkin spec. Reply `approve` to lock it and start the Triad loop, or give refinement notes."*
   - If the human provides refinements, record any reusable rule via `record_rag_decision`, revise the `.feature` file, and re-present.
3. Once approved, **lock the `.feature` file hash** so the Fixer can never weaken tests:
   ```bash
   python ai-automations/orchestration/triad_evaluator.py \
     --lock-feature tests/features/<FeatureName>.feature
   ```

### Phase B — Bounded Autonomous Triad Loop (Max 5 Cycles)
Repeat for `cycle = 1..5`:
1. **Enricher Subagent** (`EnableWriteTools: false`): Load [triad-enricher-agent.md](../../agents/triad-enricher-agent.md), passing the approved `.feature` path and any `last_failure_diagnostics` from the previous cycle. Produces a concise JSON impact plan.
2. **Fixer Subagent** (`EnableWriteTools: true`): Load [triad-fixer-agent.md](../../agents/triad-fixer-agent.md), passing the Enricher's JSON plan and the locked `.feature` path. Every file write is physically intercepted by `.agents/hooks.json` (`pre_write_ast_gate.py`).
3. **Evaluator Subagent**: Load [triad-evaluator-agent.md](../../agents/triad-evaluator-agent.md) and execute `triad_evaluator.py` with the build and test commands defined in `docs/adr/001-architecture-and-stack.md`:
   ```bash
   python ai-automations/orchestration/triad_evaluator.py \
     --build-cmd "<your-project-build-command>" \
     --test-cmd "<your-project-bdd-test-command>"
   ```
4. Inspect the Evaluator verdict:
   - If `"all_green": true`, exit the loop and proceed to Phase C.
   - If `"all_green": false`, pass `last_failure_diagnostics` to the Enricher for Cycle `N + 1`.
5. **Escalation Cap:** If Cycle 5 still fails, **HALT**. Emit `reports/triad/escalation-report.md` summarizing the 5 attempts and exact blocking failure, and ask the human engineer for guidance.

### Phase C — Human Gate 2 (Verified Diff Signoff)
1. Run `git diff --stat` and `git diff` and present a concise summary (cycles taken, AST audit result, test counts, and diff).
2. **STOP** and ask the human: *"🛑 HUMAN GATE 2: Approve this verified diff for commit? (`approve` / `revise` / `abort`)"*.
3. Only after explicit approval, commit cleanly to Git.
