"""Verification suite for the Local AI-SDLC Starter Kit."""

from __future__ import annotations

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src" / "mcp"))
sys.path.insert(0, str(REPO_ROOT / "src" / "hooks"))
sys.path.insert(0, str(REPO_ROOT / "src" / "orchestration"))

from ast_parser import audit_source_guardrails  # noqa: E402
from fetch_telemetry import advance_checkpoint, fetch_snapshot, load_state  # noqa: E402
from hybrid_rag_mcp import HybridRagEngine  # noqa: E402
from pre_write_ast_gate import evaluate_hook_payload  # noqa: E402
from triad_evaluator import lock_feature_spec, run_evaluation  # noqa: E402


def test_csharp_ast_blocks_multi_type_and_handles_utf8_offsets() -> None:
    # Leading multi-byte UTF-8 characters (£, —, emoji) verify byte-offset decoding works cleanly
    bad_cs = """// Cost savings: £189.99/yr — Starter Kit ✅
namespace App.Domain.Models;

public record OrderRecord(string OrderId, long TotalCents);
public enum OrderStatus { Pending, Confirmed }
"""
    res = audit_source_guardrails("src/Domain/Models/OrderRecord.cs", bad_cs)
    assert res["passed"] is False
    assert any("SA1402 Violation" in v for v in res["violations"])
    names = [t["name"] for t in res["top_level_types"]]
    assert names == ["OrderRecord", "OrderStatus"]


def test_csharp_ast_blocks_banned_imports_and_direct_db() -> None:
    bad_cs = """using MediatR;
using Npgsql;
namespace App.Infrastructure;
public class BadRepo {
    public void Open() { var c = new NpgsqlConnection("Host=localhost"); }
}
"""
    res = audit_source_guardrails("src/Infrastructure/BadRepo.cs", bad_cs)
    assert res["passed"] is False
    assert any("MediatR" in v for v in res["violations"])
    assert any("DIP Violation" in v for v in res["violations"])


def test_typescript_ast_blocks_banned_imports_and_too_many_types() -> None:
    bad_tsx = """import axios from 'axios';
export interface Props { count: number; }
export type Mode = 'Idle' | 'Active';
export enum AlertLevel { Low, High }
export const Banner = () => <div>Status</div>;
"""
    res = audit_source_guardrails("src/Web/src/components/Banner.tsx", bad_tsx)
    assert res["passed"] is False
    assert any("axios" in v for v in res["violations"])
    assert any("Modularity Violation" in v for v in res["violations"])


def test_pre_write_hook_denies_bad_write_and_allows_clean_write() -> None:
    deny_payload = {
        "toolCall": {
            "name": "write_file",
            "args": {
                "Path": "src/Domain/Models/OrderRecord.cs",
                "Content": "public class A {}\npublic class B {}\n",
            },
        }
    }
    deny_res = evaluate_hook_payload(deny_payload)
    assert deny_res["decision"] == "deny"
    assert "SA1402" in deny_res["reason"]

    allow_payload = {
        "toolCall": {
            "name": "write_file",
            "args": {
                "Path": "src/Domain/Models/OrderRecord.cs",
                "Content": "namespace App.Domain.Models;\npublic record OrderRecord(string Id, long TotalCents);\n",
            },
        }
    }
    assert evaluate_hook_payload(allow_payload)["decision"] == "allow"


def test_hybrid_rag_multiword_search_living_memory_and_auto_refresh(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "prd.md").write_text(
        "## Order Payloads\nThe platform records OrderRecord with OrderId and CreatedAtUtc.\n",
        encoding="utf-8",
    )

    engine = HybridRagEngine(tmp_path)
    # Multi-word query with words that do NOT all appear in the doc (would fail under naive FTS5 AND)
    hits = engine.search_hybrid("OrderRecord repository ADR boundaries", top_k=3)
    assert len(hits) >= 1
    assert "prd.md" in hits[0]["path"]

    # Record an #ai-pin decision and verify it surfaces at the top
    rec = engine.record_decision(
        tag_type="ai-pin",
        target="Monetary Precision",
        rule_summary="Always store currency amounts as 64-bit integer minor units (cents), never float.",
        rationale="Avoid floating-point rounding drift in ledger reconciliation.",
    )
    assert rec["status"] == "indexed"
    pin_hits = engine.search_hybrid("ledger billing currency cents", top_k=3)
    assert any("ai-pin-monetary-precision.md" in h["path"] for h in pin_hits)

    # Create a brand new source file on disk and verify auto-refresh indexes it automatically
    cs_dir = tmp_path / "src" / "Domain"
    cs_dir.mkdir(parents=True)
    time.sleep(0.02)
    (cs_dir / "PricingRuleEngine.cs").write_text(
        "namespace App.Domain;\npublic class PricingRuleEngine { public bool Evaluate() => true; }\n",
        encoding="utf-8",
    )
    code_hits = engine.search_hybrid("PricingRuleEngine", top_k=3)
    assert any("PricingRuleEngine.cs" in h["path"] for h in code_hits)


def test_triad_evaluator_detects_gate1_feature_tampering(tmp_path: Path) -> None:
    feature = tmp_path / "OrderCheckout.feature"
    feature.write_text("Feature: OrderCheckout\n  Scenario: Discount applied\n", encoding="utf-8")
    lock_file = tmp_path / "gate1.lock.json"

    lock_feature_spec(feature, lock_file)
    ok = run_evaluation(repo_root=tmp_path, lock_path=lock_file, explicit_files=[])
    assert ok["all_green"] is True

    # Simulate a Fixer agent cheating by editing the approved .feature spec
    feature.write_text("Feature: OrderCheckout\n  Scenario: Trivial\n", encoding="utf-8")
    tampered = run_evaluation(repo_root=tmp_path, lock_path=lock_file, explicit_files=[])
    assert tampered["all_green"] is False
    assert tampered["gate1_integrity_passed"] is False


def test_fetch_telemetry_crash_safe_checkpointing(tmp_path: Path) -> None:
    state_file = tmp_path / "sre-agent-state.json"
    snap_file = tmp_path / "snapshot.json"

    # Fetch against unreachable local ports (produces collectorErrors cleanly without crashing)
    snap = fetch_snapshot(
        state_path=state_file,
        snapshot_path=snap_file,
        prometheus_url="http://127.0.0.1:19991",
        loki_url="http://127.0.0.1:19992",
        pg_container="nonexistent-container",
    )
    assert snap_file.is_file()
    # Checkpoint MUST NOT have advanced yet (crash-safe)
    assert not state_file.exists()

    # Now advance checkpoint explicitly after remediation completes
    updated = advance_checkpoint(
        state_path=state_file,
        window_start_utc=snap["windowStartUtc"],
        window_end_utc=snap["windowEndUtc"],
        cooldown_signatures=["slow_query:orders"],
    )
    assert updated["runsCount"] == 1
    assert "slow_query:orders" in updated["cooldowns"]
    assert load_state(state_file)["lastExecutionTimeUtc"] == snap["windowEndUtc"]


def test_one_command_installer_sets_up_agents_skills_mcp_and_sre_automation(tmp_path: Path) -> None:
    import json

    sys.path.insert(0, str(REPO_ROOT))
    from install import install_kit  # noqa: E402

    project_dir = tmp_path / "sample-app"
    gemini_cfg = tmp_path / "gemini-config"

    res = install_kit(
        target_dir=project_dir,
        gemini_config_dir=gemini_cfg,
        install_sre_automation=True,
        cron_expr="*/30 * * * *",
        timezone_iana="Europe/London",
    )

    assert (project_dir / "GEMINI.md").is_file()
    assert (project_dir / ".agents" / "hooks.json").is_file()
    assert (project_dir / ".agents" / "skills" / "ai-sdlc" / "SKILL.md").is_file()
    assert len(list((project_dir / ".agents" / "agents").glob("*.md"))) == 7

    mcp_data = json.loads((gemini_cfg / "mcp_config.json").read_text(encoding="utf-8"))
    assert "codebase-rag" in mcp_data["mcpServers"]
    assert mcp_data["mcpServers"]["codebase-rag"]["env"]["REPO_ROOT"] == project_dir.resolve().as_posix()

    assert len(res["sre_sidecars"]) == 3
    schedules = {}
    state_files = set()
    for sc in res["sre_sidecars"]:
        sidecar_path = Path(sc["sidecar_path"])
        assert sidecar_path.is_file()
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        assert sidecar["builtin"] == "schedule"
        assert sidecar["restart_policy"] == "always"
        assert "--advance-checkpoint" in sidecar["args"][-1]
        schedules[sc["agent"]] = sidecar["args"][0]
        state_files.add(sc["state_file"])

    assert schedules["sre-anomaly-detector-agent"] == "CRON_TZ=Europe/London */30 * * * *"
    assert schedules["sre-error-log-agent"] == "CRON_TZ=Europe/London */30 * * * *"
    assert schedules["sre-slow-query-agent"] == "CRON_TZ=Europe/London 0 */6 * * *"
    assert len(state_files) == 3  # Isolated checkpoints prevent race conditions


def test_devsecops_sca_config_and_native_audit_override(tmp_path: Path) -> None:
    import json
    from run_local_devsecops import load_devsecops_config, run_sca  # noqa: E402

    cfg_file = tmp_path / "devsecops.config.json"
    cfg_file.write_text(
        json.dumps({"sca_severity": "CRITICAL", "sca_command": f"{sys.executable} -c \"print('ok')\""}),
        encoding="utf-8",
    )
    cfg = load_devsecops_config(cfg_file)
    assert cfg["sca_severity"] == "CRITICAL"

    ok_res = run_sca(tmp_path, sca_cmd=cfg["sca_command"], use_trivy=False)
    assert ok_res["passed"] is True
    assert ok_res["native_audit"]["passed"] is True

    fail_res = run_sca(tmp_path, sca_cmd=f"{sys.executable} -c \"import sys; sys.exit(1)\"", use_trivy=False)
    assert fail_res["passed"] is False
    assert fail_res["native_audit"]["passed"] is False
