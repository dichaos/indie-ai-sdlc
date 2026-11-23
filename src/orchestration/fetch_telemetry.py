#!/usr/bin/env python3
"""Cross-Platform Gapless SRE Telemetry Collector.

Queries local Prometheus, Loki, and PostgreSQL (`pg_stat_statements`) strictly for the
window `[lastExecutionTimeUtc -> NOW]` tracked in `sre-agent-state.json`.

Design Guarantees:
1. Cross-platform (macOS, Linux, Windows) using Python stdlib only (no external HTTP deps).
2. Crash-safe checkpointing: fetching telemetry does NOT advance the checkpoint.
   Call `--advance-checkpoint` ONLY after the SRE agent finishes triage/remediation.
3. Circuit-breaker cooldowns: tracks recently-ticketed anomaly signatures to prevent
   infinite remediation loops.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_STATE_PATH = Path("ai-automations/sre-agent-state.json")
DEFAULT_SNAPSHOT_PATH = Path("ai-automations/sre-telemetry-snapshot.json")


def parse_iso_utc(raw: str) -> datetime:
    cleaned = raw.replace("Z", "+00:00")
    dt = datetime.fromisoformat(cleaned)
    return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def load_state(state_path: Path) -> Dict[str, Any]:
    if state_path.is_file():
        try:
            return json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {
        "version": "1.0.0",
        "lastExecutionTimeUtc": None,
        "runsCount": 0,
        "environment": "home-local",
        "cooldowns": {},
    }


def resolve_window(state: Dict[str, Any], default_lookback_minutes: int = 30) -> tuple[datetime, datetime, bool]:
    now = datetime.now(timezone.utc)
    last_raw = state.get("lastExecutionTimeUtc")
    if last_raw:
        try:
            start = parse_iso_utc(last_raw)
            if start < now:
                return start, now, True
        except ValueError:
            pass
    return now - timedelta(minutes=default_lookback_minutes), now, False


def http_get_json(url: str, timeout: int = 6) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def query_prometheus(prometheus_url: str, lookback_seconds: int) -> tuple[Dict[str, Any], List[str]]:
    window = f"{max(lookback_seconds, 60)}s"
    queries = {
        "targets_up": "up",
        "api_p95_latency_ms": (
            f"histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[{window}])) by (le, route)) * 1000"
        ),
        "http_5xx_rate": f"sum(rate(http_requests_total{{status=~'5..'}}[{window}])) by (service, route)",
        "active_db_connections": "pg_stat_activity_count",
    }
    metrics: Dict[str, Any] = {}
    errors: List[str] = []
    for name, expr in queries.items():
        encoded = urllib.parse.urlencode({"query": expr})
        url = f"{prometheus_url.rstrip('/')}/api/v1/query?{encoded}"
        try:
            data = http_get_json(url)
            if data.get("status") == "success":
                metrics[name] = data.get("data", {}).get("result", [])
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            errors.append(f"Prometheus query '{name}' failed: {exc}")
    return metrics, errors


def query_loki(loki_url: str, start: datetime, end: datetime, limit: int = 200) -> tuple[List[Dict[str, Any]], List[str]]:
    start_ns = int(start.timestamp() * 1_000_000_000)
    end_ns = int(end.timestamp() * 1_000_000_000)
    params = urllib.parse.urlencode(
        {
            "query": '{app=~".+", level=~"error|critical"}',
            "start": str(start_ns),
            "end": str(end_ns),
            "limit": str(limit),
        }
    )
    url = f"{loki_url.rstrip('/')}/loki/api/v1/query_range?{params}"
    try:
        data = http_get_json(url)
        if data.get("status") == "success":
            return data.get("data", {}).get("result", []), []
        return [], [f"Loki non-success status: {data.get('status')}"]
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return [], [f"Loki query failed: {exc}"]


def query_pg_slow_statements(
    pg_container: str,
    pg_user: str,
    pg_db: str,
    threshold_ms: float = 350.0,
) -> tuple[List[Dict[str, Any]], List[str]]:
    """Queries local Docker PostgreSQL pg_stat_statements for queries exceeding PRD latency budget."""
    sql = (
        "SELECT json_agg(t) FROM ("
        "SELECT query, calls, round(mean_exec_time::numeric, 2) AS mean_ms, rows "
        "FROM pg_stat_statements "
        f"WHERE mean_exec_time >= {threshold_ms} "
        "ORDER BY mean_exec_time DESC LIMIT 10"
        ") t;"
    )
    cmd = ["docker", "exec", pg_container, "psql", "-U", pg_user, "-d", pg_db, "-t", "-A", "-c", sql]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        if res.returncode != 0:
            return [], [f"pg_stat_statements query failed: {res.stderr.strip()}"]
        raw = res.stdout.strip()
        if not raw or raw == "null":
            return [], []
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else [], []
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        return [], [f"pg_stat_statements unavailable: {exc}"]


def is_in_cooldown(state: Dict[str, Any], signature: str, now: datetime) -> bool:
    until_raw = state.get("cooldowns", {}).get(signature)
    if not until_raw:
        return False
    try:
        return now < parse_iso_utc(until_raw)
    except ValueError:
        return False


def advance_checkpoint(
    state_path: Path,
    window_end_utc: str,
    window_start_utc: str,
    cooldown_signatures: Optional[List[str]] = None,
    cooldown_hours: int = 6,
) -> Dict[str, Any]:
    """Commits the new gapless checkpoint ONLY after the SRE agent finishes processing."""
    state = load_state(state_path)
    now = parse_iso_utc(window_end_utc)
    state["lastExecutionTimeUtc"] = window_end_utc
    state["runsCount"] = int(state.get("runsCount", 0)) + 1
    state["lastExecutionWindow"] = {
        "startUtc": window_start_utc,
        "endUtc": window_end_utc,
    }
    cooldowns = state.setdefault("cooldowns", {})
    # Prune expired cooldowns
    active_cooldowns = {
        sig: exp for sig, exp in cooldowns.items() if not exp or now < parse_iso_utc(exp)
    }
    for sig in cooldown_signatures or []:
        active_cooldowns[sig] = (now + timedelta(hours=cooldown_hours)).isoformat().replace("+00:00", "Z")
    state["cooldowns"] = active_cooldowns

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return state


def fetch_snapshot(
    state_path: Path,
    snapshot_path: Path,
    prometheus_url: str = "http://localhost:9090",
    loki_url: str = "http://localhost:3100",
    pg_container: str = "app-postgres",
    pg_user: str = "postgres",
    pg_db: str = "appdb",
    slow_query_ms: float = 350.0,
    lookback_minutes: int = 30,
) -> Dict[str, Any]:
    state = load_state(state_path)
    start, end, is_continuous = resolve_window(state, default_lookback_minutes=lookback_minutes)
    duration_sec = max(int((end - start).total_seconds()), 1)

    metrics, prom_errors = query_prometheus(prometheus_url, duration_sec)
    loki_streams, loki_errors = query_loki(loki_url, start, end)
    slow_queries, pg_errors = query_pg_slow_statements(pg_container, pg_user, pg_db, slow_query_ms)

    snapshot = {
        "windowStartUtc": start.isoformat().replace("+00:00", "Z"),
        "windowEndUtc": end.isoformat().replace("+00:00", "Z"),
        "windowDurationSeconds": duration_sec,
        "isContinuousFromLastRun": is_continuous,
        "activeCooldowns": [
            sig for sig in state.get("cooldowns", {}) if is_in_cooldown(state, sig, end)
        ],
        "metrics": metrics,
        "lokiErrorStreams": loki_streams,
        "slowQueries": slow_queries,
        "collectorErrors": prom_errors + loki_errors + pg_errors,
    }

    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    return snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description="Gapless SRE Telemetry Collector")
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_SNAPSHOT_PATH)
    parser.add_argument("--prometheus-url", default="http://localhost:9090")
    parser.add_argument("--loki-url", default="http://localhost:3100")
    parser.add_argument("--pg-container", default="app-postgres")
    parser.add_argument("--pg-user", default="postgres")
    parser.add_argument("--pg-db", default="appdb")
    parser.add_argument("--slow-query-ms", type=float, default=350.0)
    parser.add_argument("--lookback-minutes", type=int, default=30)
    parser.add_argument(
        "--advance-checkpoint",
        action="store_true",
        help="Advance sre-agent-state.json using the window in --output snapshot (run AFTER remediation succeeds).",
    )
    parser.add_argument(
        "--cooldown-signature",
        action="append",
        default=[],
        help="Anomaly signature to place in cooldown so it is not re-ticketed immediately.",
    )
    args = parser.parse_args()

    if args.advance_checkpoint:
        if not args.output.is_file():
            print(json.dumps({"error": f"Snapshot file not found: {args.output}"}), file=sys.stderr)
            return 1
        snap = json.loads(args.output.read_text(encoding="utf-8"))
        updated = advance_checkpoint(
            state_path=args.state_file,
            window_start_utc=snap["windowStartUtc"],
            window_end_utc=snap["windowEndUtc"],
            cooldown_signatures=args.cooldown_signature,
        )
        print(json.dumps({"status": "checkpoint_advanced", "state": updated}, indent=2))
        return 0

    snapshot = fetch_snapshot(
        state_path=args.state_file,
        snapshot_path=args.output,
        prometheus_url=args.prometheus_url,
        loki_url=args.loki_url,
        pg_container=args.pg_container,
        pg_user=args.pg_user,
        pg_db=args.pg_db,
        slow_query_ms=args.slow_query_ms,
        lookback_minutes=args.lookback_minutes,
    )
    print(json.dumps(snapshot, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
