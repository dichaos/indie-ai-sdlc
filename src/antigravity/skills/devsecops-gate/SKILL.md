---
name: devsecops-gate
description: >-
  Runs the 3-minute local Docker DevSecOps gate (Semgrep SAST with custom
  project rules, OWASP ZAP OpenAPI scan, and diff-cover >= 90% differential coverage),
  routes findings into dev-triad, and persists human #ai-pin / #ai-ignore review
  comments into Living Memory via record_rag_decision.
---

# Local DevSecOps & Living Memory Skill

## Mode 1 — 3-Minute Local DevSecOps Gate
1. Ensure your application is running locally (`http://localhost:5000`) and Cobertura coverage XML has been generated (`reports/coverage.cobertura.xml`).
2. Execute the deterministic local gate:
   ```bash
   python ai-automations/orchestration/run_local_devsecops.py \
     --custom-rules ai-automations/rules/custom-architecture.yml \
     --openapi-url http://host.docker.internal:5000/openapi.json \
     --coverage-xml reports/coverage.cobertura.xml \
     --min-coverage 90
   ```
3. Inspect the JSON report:
   - **SAST (`semgrep/semgrep`)**: Catches OWASP Top 10 flaws AND custom architectural/security rules from `custom-architecture.yml`.
   - **DAST (`zaproxy/zap-stable` `zap-api-scan.py`)**: Uses your app's live OpenAPI spec to detect missing security headers (`Content-Security-Policy`, `X-Frame-Options`), permissive CORS, and unauthenticated API responses.
   - **Differential Coverage (`diff-cover`)**: Verifies `>= 90%` line coverage on newly added/modified lines vs `main`.
4. If `"all_passed": false`, package each finding into a remediation ticket for the **`dev-triad`** skill (creating a security regression test first), then re-run `run_local_devsecops.py` until `"all_passed": true`.

## Mode 2 — Recording Living Memory (`#ai-pin` / `#ai-ignore`)
Whenever the human reviewer posts a comment tagged `#ai-pin` or `#ai-ignore`:
1. Call MCP tool `record_rag_decision(tag_type, target, rule_summary, rationale)` on `codebase-rag`.
2. Confirm the created file in `docs/decisions/` and the updated chunk count.
3. To retire an obsolete rule later, set `- **Status**: Superseded` in that markdown file—`codebase-rag` automatically excludes superseded rules on its next mtime refresh.
