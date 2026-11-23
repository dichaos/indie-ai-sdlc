---
name: devsecops-gate
description: >-
  Runs Stage 4 DAST (via Custom Agent sec-dast-agent.md using OWASP ZAP OpenAPI
  scanning against the running local app), optionally re-runs SAST/SCA via
  sec-sast-sca-agent.md, routes findings into dev-triad, and persists human
  #ai-pin / #ai-ignore review comments into Living Memory via record_rag_decision.
---

# Stage 4 — Local DAST & Living Memory Skill

## Custom Security Agent Files
- **Inside-Triad Static Security & Library SCA Agent:** [sec-sast-sca-agent.md](../../agents/sec-sast-sca-agent.md) *(runs automatically inside `dev-triad` before Human Gate 2)*
- **Stage 4 Live DAST Agent:** [sec-dast-agent.md](../../agents/sec-dast-agent.md) *(runs against your live local app)*

## Mode 1 — Stage 4 DAST (Live Running Application)
1. Ensure your application is running locally (`http://localhost:5000`) and serving its OpenAPI spec (`http://host.docker.internal:5000/openapi.json`).
2. Load [sec-dast-agent.md](../../agents/sec-dast-agent.md) and spawn the **Stage 4 DAST Subagent** to execute:
   ```bash
   python ai-automations/orchestration/run_local_devsecops.py \
     --skip-sast --skip-sca --skip-coverage \
     --openapi-url http://host.docker.internal:5000/openapi.json
   ```
3. If `dast.passed` is `false`, feed the actionable alerts back into **`dev-triad`** (which adds a security regression test, applies the fix, re-runs full repo tests + SAST/SCA, and pauses at Human Gate 2), then re-run Stage 4 DAST until green.

## Mode 2 — On-Demand Full 4-Pillar Audit (SAST + SCA + DAST + Diff-Cover)
Run all four gates together anytime:
```bash
python ai-automations/orchestration/run_local_devsecops.py \
  --config ai-automations/rules/devsecops.config.json \
  --custom-rules ai-automations/rules/custom-architecture.yml \
  --openapi-url http://host.docker.internal:5000/openapi.json \
  --coverage-xml reports/coverage.cobertura.xml \
  --min-coverage 90
```

## Mode 3 — Recording Living Memory (`#ai-pin` / `#ai-ignore`)
Whenever the human reviewer posts a comment tagged `#ai-pin` or `#ai-ignore`:
1. Call MCP tool `record_rag_decision(tag_type, target, rule_summary, rationale)` on `codebase-rag`.
2. Confirm the created file in `docs/decisions/` and the updated chunk count.
3. To retire an obsolete rule later, set `- **Status**: Superseded` in that markdown file—`codebase-rag` automatically excludes superseded rules on its next mtime refresh.
