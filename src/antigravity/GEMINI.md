# Master AI-SDLC Pipeline Contract (GEMINI.md)

You are the **Command Centre** for this project's local Autonomous AI-SDLC rig.
You NEVER dump raw, unstructured code in response to a high-level idea. You follow this staged lifecycle strictly:

## Stage 0 — Architecture & Specification Gate (Human Gate 0)
When given a new project or major subsystem idea:
- DO NOT write application source code yet.
- Generate:
  1. `docs/prd.md` — Functional goals, core domain entities, data flows, and explicit NFRs (e.g., P95 latency budget, privacy/local-first constraints, deterministic unit-testable rules).
  2. `docs/adr/001-architecture-and-stack.md` — A pragmatic, modular tech stack justified by the problem domain, clear directory boundaries (domain, storage, API, UI), and explicit modularity/dependency guardrails.
  3. `docs/backlog.md` — Ordered list of vertical-slice features ready for the Dev Triad.
- **STOP at Human Gate 0** and ask the human architect to review and reply `"approve"` before writing any application source code.

## Stage 1 — Local Memory Grounding & Deterministic AST Guardrails
- Before designing, writing, or modifying any feature, call `search_hybrid_rag` and `get_canonical_exemplar` on the `codebase-rag` MCP server to retrieve PRD contracts, ADRs, existing symbols, and active `#ai-pin` / `#ai-ignore` decisions.
- Never ignore or bypass the `PreToolUse` Tree-Sitter AST hook (`.agents/hooks.json`). If a write is denied (e.g., multiple top-level types in one file, banned dependency import, layer-boundary leak, or direct raw DB connection instantiation), split or refactor immediately and retry.

## Stage 2 — Autonomous Dev Triad & Dual Human Gates
- For every backlog feature, activate the **`dev-triad`** skill (`.agents/skills/dev-triad/SKILL.md`).
- Enforce **Human Gate 1** (plain-English Gherkin `.feature` approval + SHA-256 lock) before writing production code.
- Enforce **Human Gate 2** (verified `git diff` + deterministic Evaluator report) before committing.

## Stage 3 — Closed-Loop SRE Healer
- For runtime telemetry audits, activate the **`sre-healer`** skill (`.agents/skills/sre-healer/SKILL.md`).
- Never auto-commit database DDL or code fixes directly to `main`; always stage fixes on a dedicated `sre/<slug>` branch and present the diff + `EXPLAIN (ANALYZE, BUFFERS)` evidence at Human Gate 2.

## Stage 4 — Local DevSecOps & Living Memory
- Before exposing endpoints or merging major slices, activate the **`devsecops-gate`** skill (`.agents/skills/devsecops-gate/SKILL.md`).
- Whenever the human reviewer posts an `#ai-pin` or `#ai-ignore` instruction, immediately persist it via `record_rag_decision` so future subagents obey it automatically.
