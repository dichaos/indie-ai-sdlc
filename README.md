# Local AI-SDLC Starter Kit (`indie-ai-sdlc`)

A 100% local, stack-agnostic starter kit that turns **Antigravity** into an autonomous **AI-SDLC Command Centre**—backed by in-memory Hybrid RAG (`< 8ms`), physical Tree-Sitter AST pre-write hooks (`< 12ms`), isolated subagent skills, periodic self-healing SRE automations, and a 3-minute local Docker DevSecOps gate.

---

## Architecture Overview

This starter kit separates **LLM reasoning** from **deterministic engineering enforcement**:

- **Antigravity (Command Centre)** owns workspace rules (`GEMINI.md`), progressive-disclosure Skills (`.agents/skills/*/SKILL.md`), isolated subagents (`.agents/agents/*.md`), and recurring background **Automations** (`/automation`).
- **Local Scripts & Docker (£0.00 cloud cost)** own every deterministic gate:
  1. **Local Hybrid RAG (`src/mcp/hybrid_rag_mcp.py`)**: In-memory SQLite FTS5 (`OR`-tokenized BM25) + TF-IDF merged with Reciprocal Rank Fusion (RRF), automatic `mtime`-based re-indexing, and `#ai-pin` / `#ai-ignore` Living Memory over `stdio` MCP.
  2. **Physical Pre-Write AST Hook (`src/hooks/pre_write_ast_gate.py`)**: Wired into `.agents/hooks.json` (`PreToolUse` on `write_file|edit_file`) using UTF-8 byte-safe Tree-Sitter AST parsing to deny modularity, banned-import, layer-boundary, and direct-DB violations *before* files touch disk.
  3. **Deterministic Dev Triad Evaluator (`src/orchestration/triad_evaluator.py`)**: Verifies Human Gate 1 `.feature` SHA-256 locks (preventing test tampering), runs Tree-Sitter AST across modified files, and executes your project's build and BDD/unit test commands.
  4. **Crash-Safe Gapless SRE Collector (`src/orchestration/fetch_telemetry.py`)**: Queries local Prometheus, Loki, and PostgreSQL `pg_stat_statements` strictly from **`lastExecutionTimeUtc -> NOW`** persisted in `ai-automations/sre-agent-state.json`, with explicit post-remediation `--advance-checkpoint` and 6-hour per-signature cooldowns.
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
│       └── custom-architecture.yml                   # Semgrep custom rules (auth scope + precision/domain rules)
└── tests/
    └── test_starter_kit.py                           # Verification suite for AST, hooks, RAG, locks & checkpointing
```

---

## Step 1: Install & Verify Antigravity Setup

### Prerequisites
- **Antigravity** (IDE or CLI, signed in with your Google AI Pro account)
- **Git** & **Docker Desktop / Docker Engine**
- **Python 3.11+** (powers the local MCP server, AST hook, and deterministic evaluators)
- **RAM**: 16 GB minimum (32 GB recommended when running observability + database + Semgrep/ZAP concurrently)

### 1. Clone & Verify the Starter Kit
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
All 7 tests should pass before you copy the kit into your project.

### 2. Wire Antigravity Into Your Project Workspace
Create (or open) your target project folder and copy the starter kit into the exact directories Antigravity auto-discovers:

```bash
mkdir my-project && cd my-project
git init
mkdir -p .agents/skills .agents/agents docs/adr docs/decisions ai-automations
```

1. **Always-On Workspace Contract (`GEMINI.md`):**
   Copy `src/antigravity/GEMINI.md` to `my-project/GEMINI.md`. Antigravity walks up to `.git` and loads `GEMINI.md` automatically in every session.
2. **Pre-Write AST Hook, Agents & Skills (`.agents/`):**
   Copy `src/antigravity/hooks.json`, `src/antigravity/agents/`, and `src/antigravity/skills/` into `my-project/.agents/`.
3. **Deterministic Helpers (`ai-automations/`):**
   Copy `src/mcp/`, `src/hooks/`, `src/orchestration/`, `src/observability/`, and `src/rules/` into `my-project/ai-automations/`.
4. **Create a Project Virtualenv & Update `.agents/hooks.json`:**
   Install `requirements.txt` inside `my-project/.venv`, then verify `.agents/hooks.json` points `command` at your `.venv` Python binary (`../.venv/bin/python` on macOS/Linux, or `../.venv/Scripts/python.exe` on Windows).
5. **Register the `codebase-rag` MCP Server Globally:**
   Merge `src/antigravity/mcp_config.json` into `~/.gemini/config/mcp_config.json` using **absolute paths**:
   ```json
   {
     "mcpServers": {
       "codebase-rag": {
         "command": "/ABS/PATH/TO/my-project/.venv/bin/python",
         "args": ["/ABS/PATH/TO/my-project/ai-automations/mcp/hybrid_rag_mcp.py"],
         "env": {
           "REPO_ROOT": "/ABS/PATH/TO/my-project"
         }
       }
     }
   }
   ```
6. **Confirm Discovery in Antigravity:**
   Open `my-project` in Antigravity and check **Additional Options (`...`) > MCP Servers** to confirm `codebase-rag` is connected (`search_hybrid_rag`, `get_canonical_exemplar`, `validate_code_against_guardrails`, `record_rag_decision`).

---

## Step 2: Running the Entire AI-SDLC from Antigravity (Command Centre)

Once wired up, you drive **every stage of the SDLC** directly from the Antigravity chat/CLI—never manually gluing scripts together:

| SDLC Stage | Exact Prompt to Type in Antigravity | What Antigravity Coordinates Automatically |
| :--- | :--- | :--- |
| **Stage 0: Architecture & Backlog** | `Execute Stage 0 from GEMINI.md for a new project called "<Name>". Here is the problem: <describe problem & constraints>. Pause at Human Gate 0.` | Generates `docs/prd.md`, `docs/adr/001-architecture-and-stack.md`, and `docs/backlog.md`, then halts for your `"approve"`. |
| **Stage 1: Memory & AST Guardrails** | *(Automatic on every turn)* | Agents query `codebase-rag` (`< 8ms`, auto-refreshing on file changes), while `.agents/hooks.json` physically denies any non-compliant `write_file`/`edit_file` before disk write. |
| **Stage 2: Autonomous Feature Build** | `Run the dev-triad skill for Feature 01 from docs/backlog.md.` | Spawns `qa-bdd-spec-agent.md` $\rightarrow$ pauses at **Human Gate 1** $\rightarrow$ locks `.feature` SHA-256 $\rightarrow$ loops `triad-enricher-agent.md` $\rightarrow$ `triad-fixer-agent.md` $\rightarrow$ `triad-evaluator-agent.md` (max 5 cycles) $\rightarrow$ pauses at **Human Gate 2** for diff signoff & commit. |
| **Stage 3: Self-Healing SRE Audit** | `Run the sre-healer skill against our running local stack.` *(or scheduled via `/automation` — see Step 3)* | Collects gapless `[lastExecutionTimeUtc -> NOW]` telemetry $\rightarrow$ fans out in parallel to `sre-anomaly-detector-agent.md`, `sre-error-log-agent.md`, and `sre-slow-query-agent.md` $\rightarrow$ stages fixes on `sre/*` branch $\rightarrow$ pauses at **Human Gate 2** $\rightarrow$ advances checkpoint. |
| **Stage 4A: 3-Min Local DevSecOps** | `Run the devsecops-gate skill before merging.` | Runs `run_local_devsecops.py` (Semgrep SAST + OWASP ZAP OpenAPI + `diff-cover >= 90%`) and feeds any finding back into `dev-triad`. |
| **Stage 4B: Living Memory** | `Record this in Living Memory via devsecops-gate: #ai-pin Target: "<Topic>" Rule: "<Rule>" Rationale: "<Why>"` | Calls `record_rag_decision`, writes `docs/decisions/<tag>-<slug>.md`, and re-indexes RAM in `< 2s` for all future subagents. |

---

## Step 3: Scheduling Periodic SRE Agents via Antigravity `/automation`

To make the three SRE agents (`sre-anomaly-detector-agent.md`, `sre-error-log-agent.md`, `sre-slow-query-agent.md`) monitor your running app **automatically on a recurring schedule**:

### 1. Start the Local Observability Stack
```bash
docker compose -f ai-automations/observability/docker-compose.observability.yml up -d
```
- Prometheus: `http://localhost:9090`
- Loki: `http://localhost:3100`
- Grafana: `http://localhost:3000` (`admin` / `local-dev-admin`)

### 2. Create the Recurring Automation Inside Antigravity
In your project workspace inside Antigravity, type:

```text
/automation
```

Antigravity's interactive automation wizard will ask you for:
1. **Cadence:** Choose **Hourly** (or **Custom cron schedule**, e.g., `*/30 * * * *` for every 30 minutes).
2. **Timezone / Time:** Confirm your local IANA timezone (e.g., `Europe/London`).
3. **Self-Contained Task Prompt:** Paste this exact prompt:

```text
Open the repository at /ABS/PATH/TO/my-project and execute the `sre-healer` skill (`.agents/skills/sre-healer/SKILL.md`):

1. Run `python ai-automations/orchestration/fetch_telemetry.py` WITHOUT `--advance-checkpoint` so telemetry is collected strictly from `lastExecutionTimeUtc` in `ai-automations/sre-agent-state.json` up to NOW (or the last 30m on cold start).
2. Fan out in parallel to `.agents/agents/sre-anomaly-detector-agent.md`, `.agents/agents/sre-error-log-agent.md`, and `.agents/agents/sre-slow-query-agent.md` against `ai-automations/sre-telemetry-snapshot.json`.
3. Suppress any signature matching an active `#ai-ignore` rule in `codebase-rag` or listed in `activeCooldowns`.
4. For any actionable latency breach, slow SQL query, or unhandled Loki error, create a dedicated `sre/<slug>` Git branch and dispatch `dev-triad` to stage a verified fix and regression test (NEVER commit directly to `main`).
5. Output the Executive SRE Remediation Digest (highlighting any `sre/*` branches ready for Human Gate 2 review).
6. Only after steps 1-5 succeed cleanly, run `python ai-automations/orchestration/fetch_telemetry.py --advance-checkpoint` (passing `--cooldown-signature <sig>` for any ticketed anomaly) so the next scheduled run resumes from this exact UTC timestamp forward.
```

### How Gapless Timestamp Tracking Works Across Scheduled Runs
Each Antigravity `/automation` trigger launches a **brand-new conversation with no memory of prior runs**. `ai-automations/sre-agent-state.json` bridges those runs cleanly:

```json
{
  "version": "1.0.0",
  "lastExecutionTimeUtc": "2026-11-23T09:00:00.000000Z",
  "runsCount": 14,
  "environment": "home-local",
  "lastExecutionWindow": {
    "startUtc": "2026-11-23T08:30:00.000000Z",
    "endUtc": "2026-11-23T09:00:00.000000Z"
  },
  "cooldowns": {
    "slow_query:orders": "2026-11-23T15:00:00.000000Z"
  }
}
```

- **Run `N` starts:** `fetch_telemetry.py` reads `lastExecutionTimeUtc` and queries Prometheus, Loki (nanosecond `start`/`end` bounds), and `pg_stat_statements` strictly for **`[lastExecutionTimeUtc -> NOW]`**.
- **If Run `N` crashes mid-way:** `sre-agent-state.json` is **untouched**, so Run `N+1` automatically covers the missed window with zero blind spots.
- **When Run `N` finishes cleanly:** `--advance-checkpoint` writes `lastExecutionTimeUtc = windowEndUtc` and records 6-hour cooldowns for ticketed signatures. Run `N+1` starts from that exact timestamp forward—**zero gaps, zero duplicate tickets**.

---

## License

MIT License — see [LICENSE](LICENSE) for details.
