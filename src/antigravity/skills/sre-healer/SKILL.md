---
name: sre-healer
description: >-
  Runs a gapless local SRE telemetry audit against Prometheus, Loki, and
  PostgreSQL pg_stat_statements by coordinating three specialized SRE agents
  (Anomaly Detector, Error Log Analyst, and Slow Query Optimizer) and staging
  verified fixes on a dedicated sre/<slug> branch for Human Gate 2 review.
---

# Closed-Loop SRE Healer Skill (Antigravity Command Centre)

You are the **SRE Command Centre** for this project. You coordinate three specialized read-only SRE agents—each defined in its own standalone Markdown prompt file—to turn live local telemetry into verified, reviewable `sre/*` branches without alert churn and without ever blindly pushing DDL or unreviewed fixes to `main`.

## SRE Agent Prompt Files
- **Anomaly Detection Agent (Prometheus Golden Signals):** [sre-anomaly-detector-agent.md](../../agents/sre-anomaly-detector-agent.md)
- **Error Log Analyst Agent (Loki Error Streams):** [sre-error-log-agent.md](../../agents/sre-error-log-agent.md)
- **Slow Query Optimizer Agent (`pg_stat_statements`):** [sre-slow-query-agent.md](../../agents/sre-slow-query-agent.md)

## Safety Invariants
1. **Crash-Safe Checkpointing**: Run `fetch_telemetry.py` WITHOUT `--advance-checkpoint` first. Only advance the checkpoint at the very end after triage completes cleanly.
2. **Branch-Only Remediation**: NEVER auto-commit fixes or database migrations directly to `main`. Create `git checkout -b sre/<slug>` and present the diff + benchmark evidence at Human Gate 2.
3. **PostgreSQL `CONCURRENTLY` Safety**: `CREATE INDEX CONCURRENTLY` cannot run inside a transaction block. Always mark index migrations non-transactional and verify against a local test/staging Postgres instance using `EXPLAIN (ANALYZE, BUFFERS)` + `pg_index.indisvalid`.
4. **Circuit Breaker**: Skip any anomaly signature currently listed in `snapshot.activeCooldowns`.

## Execution Steps
1. **Collect Gapless Snapshot**:
   ```bash
   python ai-automations/orchestration/fetch_telemetry.py
   ```
2. **Fan Out to the Three Read-Only SRE Agents in Parallel** on `ai-automations/sre-telemetry-snapshot.json`:
   - Spawn `sre-anomaly-detector-agent` using [sre-anomaly-detector-agent.md](../../agents/sre-anomaly-detector-agent.md).
   - Spawn `sre-error-log-agent` using [sre-error-log-agent.md](../../agents/sre-error-log-agent.md).
   - Spawn `sre-slow-query-agent` using [sre-slow-query-agent.md](../../agents/sre-slow-query-agent.md).
3. **Dispatch Actionable Findings to `dev-triad`**:
   - For each actionable slow-query ticket or error-log ticket not in cooldown and not suppressed by `#ai-ignore`:
     - Create branch `sre/<anomaly-slug>`.
     - Run the **`dev-triad`** skill with the structured ticket from the SRE agent.
     - For SQL index migrations, apply the migration to a local Postgres test container and capture before/after `EXPLAIN (ANALYZE, BUFFERS)` timings and `pg_index.indisvalid` verification.
4. **Present the Executive SRE Remediation Digest** at **Human Gate 2** (branch name, Golden Signals table from `sre-anomaly-detector-agent`, suppressed `#ai-ignore` items, `EXPLAIN` proof, and diff).
5. **Advance Checkpoint & Record Cooldowns** ONLY after triage/staging succeeds:
   ```bash
   python ai-automations/orchestration/fetch_telemetry.py \
     --advance-checkpoint \
     --cooldown-signature "<anomaly-signature>"
   ```
