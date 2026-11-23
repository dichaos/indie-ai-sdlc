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
├── install.py                                        # One-command installer (agents, skills, hooks, MCP & SRE automation)
├── requirements.txt                                  # Starter kit dependencies (mcp, tree-sitter, scikit-learn, diff-cover, pytest)
├── src/
│   ├── antigravity/                                  # Ready-to-copy Antigravity Command Centre configs, agents & skills
│   │   ├── GEMINI.md                                 # Master Stage 0-4 workspace contract
│   │   ├── hooks.json                                # PreToolUse AST hook config
│   │   ├── mcp_config.json                           # stdio MCP registration template
│   │   ├── agents/                                   # 7 standalone subagent prompt files
│   │   │   ├── qa-bdd-spec-agent.md                  # QA agent recommending & drafting Gherkin BDD specs
│   │   │   ├── triad-enricher-agent.md               # Triad 1/3: Read-only RAG grounding & root-cause planner
│   │   │   ├── triad-fixer-agent.md                  # Triad 2/3: AST-guarded implementation & scoped BDD steps
│   │   │   ├── triad-evaluator-agent.md              # Triad 3/3: Deterministic verification & escalation gatekeeper
│   │   │   ├── sre-anomaly-detector-agent.md         # SRE 1/3: Prometheus Golden Signals anomaly detector
│   │   │   ├── sre-error-log-agent.md                # SRE 2/3: Loki error-log analyst & #ai-ignore filter
│   │   │   └── sre-slow-query-agent.md               # SRE 3/3: PostgreSQL pg_stat_statements slow-query optimizer
│   │   └── skills/
│   │       ├── ai-sdlc/SKILL.md                      # One-line master pipeline ("Use MyFeature.md through my AI-SDLC")
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

### 2. One-Command Install Into Your Project (Files + MCP + Periodic SRE Automation)
Run **`install.py`** once against your project folder—it automatically installs `GEMINI.md`, all 7 `.agents/agents/*.md` files, all 4 `.agents/skills/*/SKILL.md` skills, OS-patched `.agents/hooks.json`, `ai-automations/`, registers `codebase-rag` in `~/.gemini/config/mcp_config.json`, **and** installs the periodic SRE Antigravity Automation:

```bash
# 1. Create your project virtualenv and install starter kit dependencies
mkdir my-project && cd my-project
git init
python3 -m venv .venv
# macOS / Linux: source .venv/bin/activate   |   Windows: .venv\Scripts\Activate.ps1
pip install -r /ABS/PATH/TO/indie-ai-sdlc/requirements.txt

# 2. Run the one-command installer (adds all .md files, hooks, MCP & periodic SRE automation)
python /ABS/PATH/TO/indie-ai-sdlc/install.py \
  --target . \
  --install-sre-automation \
  --timezone Europe/London \
  --cron "*/30 * * * *"
```

Then open `my-project` in **Antigravity**:
- Confirm `codebase-rag` is connected under **Additional Options (`...`) > MCP Servers**.
- Enable **`Periodic SRE Healer (my-project)`** in Antigravity's **Automations** dashboard when you are ready for background SRE monitoring.

---

## Step 2: Running the Entire AI-SDLC with One Line in Antigravity

Drop your project idea or feature description into any Markdown file (for example, `MyFeature.md`) and type **one line** in Antigravity:

```text
Use MyFeature.md through my AI-SDLC
```

Antigravity automatically activates `.agents/skills/ai-sdlc/SKILL.md` and drives `MyFeature.md` end-to-end—**pausing to ask you for input at every Human Gate**:
1. **Stage 0 $\rightarrow$ Human Gate 0:** Generates/updates `docs/prd.md`, `docs/adr/001-architecture-and-stack.md`, and `docs/backlog.md`, then asks you to approve before any code is written.
2. **Stage 1 (Automatic):** Grounds every agent via `< 8ms` `codebase-rag` MCP and physically blocks sloppy writes via `.agents/hooks.json`.
3. **Stage 2A $\rightarrow$ Human Gate 1:** Spawns `qa-bdd-spec-agent.md` to draft plain-English Gherkin scenarios, asks for your approval/refinements, and locks the `.feature` SHA-256 hash.
4. **Stage 2B (Autonomous Dev Triad, max 5 cycles):** Runs `triad-enricher-agent.md` $\rightarrow$ `triad-fixer-agent.md` $\rightarrow$ `triad-evaluator-agent.md` until 100% green.
5. **Stage 2C $\rightarrow$ Human Gate 2:** Shows the verified `git diff` + Evaluator report and asks for your approval before committing to Git.

### All Command Centre Shortcuts

| Stage / Action | Simple Prompt in Antigravity |
| :--- | :--- |
| **Full Pipeline (Stage 0 $\rightarrow$ Gate 2)** | `Use MyFeature.md through my AI-SDLC` |
| **Dev Triad Only (Gate 1 $\rightarrow$ Gate 2)** | `Run dev-triad on Feature 02` |
| **On-Demand SRE Audit** | `Run sre-healer` *(or enable the installed periodic automation)* |
| **3-Minute Local DevSecOps Gate** | `Run devsecops-gate` |
| **Teach Living Memory (`#ai-pin` / `#ai-ignore`)** | `Record #ai-pin: <rule> — Rationale: <why>` |

---

## Step 3: Custom SRE Agents + 3 Independent Antigravity Automations

All three SRE specialists live cleanly as **Custom Agents** under `.agents/agents/`, and passing `--install-sre-automation` to `install.py` installs **three independent scheduled Antigravity Automations**—one per Custom SRE Agent, each with its own isolated `lastExecutionTimeUtc` checkpoint file so they **never race each other** and run at the right operational cadence:

| Antigravity Automation | Custom Agent Executed | Default Cadence | Isolated State Checkpoint |
| :--- | :--- | :--- | :--- |
| **`SRE Anomaly Detector (<project>)`** | `.agents/agents/sre-anomaly-detector-agent.md` | Every 30 min (`*/30 * * * *`) | `ai-automations/state/sre-anomaly-state.json` |
| **`SRE Error Log Analyst (<project>)`** | `.agents/agents/sre-error-log-agent.md` | Every 30 min (`*/30 * * * *`) | `ai-automations/state/sre-error-log-state.json` |
| **`SRE Slow Query Optimizer (<project>)`** | `.agents/agents/sre-slow-query-agent.md` | Every 6 hours (`0 */6 * * *`) | `ai-automations/state/sre-slow-query-state.json` |

### 1. Start the Local Observability Stack
```bash
docker compose -f ai-automations/observability/docker-compose.observability.yml up -d
```
- Prometheus: `http://localhost:9090`
- Loki: `http://localhost:3100`
- Grafana: `http://localhost:3000` (`admin` / `local-dev-admin`)

### 2. Enable in Antigravity Automations Dashboard
Open Antigravity's **Automations** dashboard and enable whichever of the three SRE automations you want running in the background. Because each SRE agent is also a standalone Custom Agent, you can still invoke any of them on demand (e.g., `"Run sre-slow-query-agent"` or `"Run sre-healer"`).

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
