"""Verification suite for the IndieBuilder-AI-SDLC HomePulse Starter Kit."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src" / "mcp"))
sys.path.insert(0, str(REPO_ROOT / "src" / "hooks"))
sys.path.insert(0, str(REPO_ROOT / "src" / "orchestration"))

from ast_parser import audit_source_guardrails  # noqa: E402
from fetch_telemetry import advance_checkpoint, fetch_snapshot, load_state  # noqa: E402
from hybrid_rag_mcp import HybridRagEngine  # noqa: E402
from pre_write_ast_gate import evaluate_hook_payload  # noqa: E402
from triad_evaluator import lock_feature_spec, run_evaluation  # noqa: E402


def test_csharp_ast_blocks_sa1402_and_handles_utf8_offsets() -> None:
    # Leading multi-byte UTF-8 characters (£, —, emoji) verify byte-offset decoding works cleanly
    bad_cs = """// Cost savings: £189.99/yr — HomePulse ☀️
namespace HomePulse.Domain.Models;

public record SensorReading(string DeviceId, long PowerMilliwatts);
public enum SensorMetricType { Watts, Celsius }
"""
    res = audit_source_guardrails("src/HomePulse.Domain/Models/SensorReading.cs", bad_cs)
    assert res["passed"] is False
    assert any("SA1402 Violation" in v for v in res["violations"])
    names = [t["name"] for t in res["top_level_types"]]
    assert names == ["SensorReading", "SensorMetricType"]


def test_csharp_ast_blocks_banned_imports_and_direct_db() -> None:
    bad_cs = """using MediatR;
using Npgsql;
namespace HomePulse.Infrastructure;
public class BadRepo {
    public void Open() { var c = new NpgsqlConnection("Host=localhost"); }
}
"""
    res = audit_source_guardrails("src/HomePulse.Infrastructure/BadRepo.cs", bad_cs)
    assert res["passed"] is False
    assert any("MediatR" in v for v in res["violations"])
    assert any("DIP Violation" in v for v in res["violations"])


def test_typescript_ast_blocks_banned_imports_and_too_many_types() -> None:
    bad_tsx = """import axios from 'axios';
export interface Props { watts: number; }
export type Mode = 'Standby' | 'SolarEco';
export enum AlertLevel { Low, High }
export const Banner = () => <div>Eco</div>;
"""
    res = audit_source_guardrails("src/HomePulse.Web/src/components/Banner.tsx", bad_tsx)
    assert res["passed"] is False
    assert any("axios" in v for v in res["violations"])
    assert any("Modularity Violation" in v for v in res["violations"])


def test_pre_write_hook_denies_bad_write_and_allows_clean_write() -> None:
    deny_payload = {
        "toolCall": {
            "name": "write_file",
            "args": {
                "Path": "src/HomePulse.Domain/Models/SensorReading.cs",
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
                "Path": "src/HomePulse.Domain/Models/SensorReading.cs",
                "Content": "namespace HomePulse.Domain.Models;\npublic record SensorReading(string Id, long Milliwatts);\n",
            },
        }
    }
    assert evaluate_hook_payload(allow_payload)["decision"] == "allow"


def test_hybrid_rag_multiword_search_living_memory_and_auto_refresh(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "prd.md").write_text(
        "## Sensor Payloads\nHomePulse records SensorReading with DeviceId and RecordedAtUtc.\n",
        encoding="utf-8",
    )

    engine = HybridRagEngine(tmp_path)
    # Multi-word query with words that do NOT all appear in the doc (would fail under naive FTS5 AND)
    hits = engine.search_hybrid("HomePulse SensorReading repository ADR boundaries", top_k=3)
    assert len(hits) >= 1
    assert "prd.md" in hits[0]["path"]

    # Record an #ai-pin decision and verify it surfaces at the top
    rec = engine.record_decision(
        tag_type="ai-pin",
        target="Energy Measurement Units",
        rule_summary="Always store power in integer milliwatts (long Milliwatts), never double.",
        rationale="Avoid floating-point rounding drift in daily utility tariff reconciliation.",
    )
    assert rec["status"] == "indexed"
    pin_hits = engine.search_hybrid("tariff estimator power energy milliwatts", top_k=3)
    assert any("ai-pin-energy-measurement-units.md" in h["path"] for h in pin_hits)

    # Create a brand new C# file on disk and verify auto-refresh indexes it automatically
    cs_dir = tmp_path / "src" / "HomePulse.Domain"
    cs_dir.mkdir(parents=True)
    time.sleep(0.02)
    (cs_dir / "SolarDiverterRuleEngine.cs").write_text(
        "namespace HomePulse.Domain;\npublic class SolarDiverterRuleEngine { public bool Evaluate() => true; }\n",
        encoding="utf-8",
    )
    code_hits = engine.search_hybrid("SolarDiverterRuleEngine", top_k=3)
    assert any("SolarDiverterRuleEngine.cs" in h["path"] for h in code_hits)


def test_triad_evaluator_detects_gate1_feature_tampering(tmp_path: Path) -> None:
    feature = tmp_path / "SolarPowerDiversion.feature"
    feature.write_text("Feature: SolarPowerDiversion\n  Scenario: Cloud dip\n", encoding="utf-8")
    lock_file = tmp_path / "gate1.lock.json"

    lock_feature_spec(feature, lock_file)
    ok = run_evaluation(repo_root=tmp_path, lock_path=lock_file, explicit_files=[])
    assert ok["all_green"] is True

    # Simulate a Fixer agent cheating by editing the approved .feature spec
    feature.write_text("Feature: SolarPowerDiversion\n  Scenario: Trivial\n", encoding="utf-8")
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
        cooldown_signatures=["slow_query:energy_readings"],
    )
    assert updated["runsCount"] == 1
    assert "slow_query:energy_readings" in updated["cooldowns"]
    assert load_state(state_file)["lastExecutionTimeUtc"] == snap["windowEndUtc"]
