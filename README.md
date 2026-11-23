# Local AI-SDLC Starter Kit (`indie-ai-sdlc`)

A 100% local, stack-agnostic starter kit that turns **Antigravity** into an autonomous AI-SDLC Command Centre—backed by in-memory Hybrid RAG (`< 8ms`), physical Tree-Sitter AST pre-write hooks (`< 12ms`), isolated subagent skills, local Prometheus/Loki SRE healing, and a 3-minute local Docker DevSecOps gate.

---

## Architecture Overview

This starter kit separates **LLM reasoning** from **deterministic engineering enforcement**:

- **Antigravity (Command Centre)** owns workspace rules (`GEMINI.md`), progressive-disclosure Skills (`.agents/skills/*/SKILL.md`), and isolated subagents (`BDD Spec`, `Enricher`, `Fixer`, `SRE Triage`).
- **Local Scripts & Docker (£0.00 cloud cost)** own every deterministic gate:
  1. **Local Hybrid RAG (`src/mcp/hybrid_rag_mcp.py`)**: In-memory SQLite FTS5 (`OR`-tokenized BM25) + TF-IDF merged with Reciprocal Rank Fusion (RRF), automatic `mtime`-based re-indexing, and `#ai-pin` / `#ai-ignore` Living Memory over `stdio` MCP.
  2. **Physical Pre-Write AST Hook (`src/hooks/pre_write_ast_gate.py`)**: Wired into `.agents/hooks.json` (`PreToolUse` on `write_file|edit_file`) using UTF-8 byte-safe Tree-Sitter AST parsing to deny modularity, banned-import, layer-boundary, and direct-DB violations *before* files touch disk.
  3. **Deterministic Dev Triad Evaluator (`src/orchestration/triad_evaluator.py`)**: Verifies Human Gate 1 `.feature` SHA-256 locks (preventing test tampering), runs Tree-Sitter AST across modified files, and executes your project's build and BDD/unit test commands.
  4. **Crash-Safe Gapless SRE Collector (`src/orchestration/fetch_telemetry.py`)**: Queries local Prometheus, Loki, and PostgreSQL `pg_stat_statements` strictly for `[lastExecutionTimeUtc -> NOW]`, with explicit post-remediation `--advance-checkpoint` and 6-hour per-signature cooldowns.
  5. **3-Minute Local DevSecOps Gate (`src/orchestration/run_local_devsecops.py`)**: Runs ephemeral Docker `semgrep/semgrep` (OWASP Top 10 + custom rules), `zaproxy/zap-stable` (`zap-api-scan.py` against OpenAPI), and `diff-cover` ($\ge 90\%$ differential coverage on changed lines).

---

## Repository Layout

```text
indie-ai-sdlc/
├── README.md
├── LICENSE
├── requirements.txt                                  # Starter kit dependencies (mcp, tree-sitter, scikit-learn, diff-cover, pytest)
├── src/
│   ├── antigravity/                                  # Ready-to-copy Antigravity Command Centre configs, agents & skills
│   │   ├── GEMINI.md                                 # Master Stage 0-4 workspace contract (copy to project root)
│   │   ├── hooks.json                                # PreToolUse AST hook config (copy to .agents/hooks.json)
│   │   ├── mcp_config.json                           # stdio MCP registration (merge into ~/.gemini/config/mcp_config.json)
│   │   ├── agents/                                   # Standalone subagent prompt files (copy to .agents/agents/)
│   │   │   ├── qa-bdd-spec-agent.md                  # QA agent recommending & drafting Gherkin BDD specs
│   │   │   ├── triad-enricher-agent.md               # Triad 1/3: Read-only RAG grounding & root-cause planner
│   │   │   ├── triad-fixer-agent.md                  # Triad 2/3: AST-guarded implementation & scoped BDD steps
│   │   │   ├── triad-evaluator-agent.md              # Triad 3/3: Deterministic verification & escalation gatekeeper
│   │   │   ├── sre-anomaly-detector-agent.md         # SRE 1/3: Prometheus Golden Signals anomaly detector
│   │   │   ├── sre-error-log-agent.md                # SRE 2/3: Loki error-log analyst & #ai-ignore filter
│   │   │   └── sre-slow-query-agent.md               # SRE 3/3: PostgreSQL pg_stat_statements slow-query optimizer
│   │   └── skills/
│   │       ├── dev-triad/SKILL.md                    # Bounded Dev Triad coordinator referencing agents/*.md
│   │       ├── sre-healer/SKILL.md                   # Branch-gated SRE coordinator referencing sre-*.md
│   │       └── devsecops-gate/SKILL.md               # Local DevSecOps & #ai-pin / #ai-ignore Living Memory runbook
│   ├── mcp/
│   │   ├── hybrid_rag_mcp.py                         # Auto-refreshing SQLite FTS5 + TF-IDF stdio MCP server
│   │   └── ast_parser.py                             # UTF-8-safe Tree-Sitter AST guardrail engine
│   ├── hooks/
│   │   └── pre_write_ast_gate.py                     # Antigravity PreToolUse hook physically denying bad writes
│   ├── orchestration/
│   │   ├── triad_evaluator.py                        # Gate-1 SHA-256 lock + AST + build/test evaluator
│   │   ├── fetch_telemetry.py                        # Cross-platform crash-safe Prometheus/Loki/PG collector
│   │   └── run_local_devsecops.py                    # Cross-platform Semgrep + ZAP OpenAPI + diff-cover runner
│   ├── observability/
│   │   ├── docker-compose.observability.yml          # Local Prometheus + Loki + Grafana + postgres-exporter
│   │   └── prometheus.yml                            # Scrape config for API /metrics & PostgreSQL
│   └── rules/
│       └── custom-architecture.yml                   # Semgrep custom rules (device auth scope + integer milliwatts)
└── tests/
    └── test_starter_kit.py                           # Verification suite for AST, hooks, RAG, locks & checkpointing
```

---

## Quick Start

### 1. Prerequisites
- Git, Docker Desktop / Docker Engine, and Antigravity
- Python 3.11+ (used for the local MCP server, hooks, and deterministic evaluators)
- **RAM**: 16 GB minimum (32 GB recommended if running Docker observability + Postgres + Semgrep/ZAP concurrently)

### 2. Install & Verify the Starter Kit
```bash
git clone https://github.com/dichaos/indie-ai-sdlc.git
cd indie-ai-sdlc

python3 -m venv .venv
# macOS / Linux:
source .venv/bin/activate
# Windows (PowerShell):
# .venv\Scripts\Activate.ps1

pip install -r requirements.txt
pytest -v
```
All 7 verification tests should pass (`AST rules`, `UTF-8 byte offsets`, `PreToolUse deny/allow`, `Hybrid RAG OR-search + #ai-pin + auto-refresh`, `Gate-1 SHA-256 tamper detection`, and `crash-safe telemetry checkpointing`).

### 3. Bootstrap Your Own Project Workspace
Create a fresh project repository and copy the starter kit into place:

```bash
mkdir my-project && cd my-project
git init
mkdir -p .agents/skills docs/adr docs/decisions ai-automations
```

1. **Workspace Rules:** Copy `src/antigravity/GEMINI.md` to `my-project/GEMINI.md`.
2. **Hooks, Agents & Skills:** Copy `src/antigravity/hooks.json`, `src/antigravity/agents/`, and `src/antigravity/skills/` into `my-project/.agents/`.
3. **Deterministic Scripts & Docker Configs:** Copy `src/mcp/`, `src/hooks/`, `src/orchestration/`, `src/observability/`, and `src/rules/` into `my-project/ai-automations/`.
4. **Virtualenv in Project:** Create `.venv` inside `my-project/` and install `requirements.txt`. Update `.agents/hooks.json` to point to `../.venv/bin/python` (macOS/Linux) or `../.venv/Scripts/python.exe` (Windows).
5. **Register the Local MCP Server:** Merge `src/antigravity/mcp_config.json` into `~/.gemini/config/mcp_config.json` using **absolute paths** for your `.venv` executable, `hybrid_rag_mcp.py`, and `REPO_ROOT`.

### 4. Start Local Observability (Optional — Stage 3 SRE)
```bash
docker compose -f ai-automations/observability/docker-compose.observability.yml up -d
```
- Prometheus: `http://localhost:9090`
- Loki: `http://localhost:3100`
- Grafana: `http://localhost:3000` (`admin` / `homepulse-local`)

### 5. Run the Local DevSecOps Gate (Stage 4)
```bash
python ai-automations/orchestration/run_local_devsecops.py \
  --custom-rules ai-automations/rules/custom-architecture.yml \
  --openapi-url http://host.docker.internal:5000/openapi.json \
  --coverage-xml reports/coverage.cobertura.xml \
  --min-coverage 90
```

---

## License

MIT License — see [LICENSE](LICENSE) for details.
