#!/usr/bin/env python3
"""One-Command Installer for the Local AI-SDLC Starter Kit (Antigravity Command Centre).

Installs all Custom Agent Markdown files, skills, hooks, GEMINI.md, deterministic Python/Docker
helpers, MCP server registration, and (optionally) 3 dedicated periodic Antigravity SRE Automations
(one per Custom SRE Agent, each with its own isolated timestamp checkpoint to prevent race conditions).

Usage:
    # Install the AI-SDLC pipeline into your project:
    python install.py --target /path/to/my-project

    # Install the pipeline AND all 3 periodic SRE Automations:
    python install.py --target /path/to/my-project --install-sre-automation --timezone Europe/London
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List


KIT_ROOT = Path(__file__).resolve().parent
SRC_ROOT = KIT_ROOT / "src"


def venv_python_path(project_dir: Path) -> Path:
    if sys.platform == "win32":
        return project_dir / ".venv" / "Scripts" / "python.exe"
    return project_dir / ".venv" / "bin" / "python"


def relative_hook_python() -> str:
    if sys.platform == "win32":
        return "../.venv/Scripts/python.exe"
    return "../.venv/bin/python"


def copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def merge_mcp_config(
    gemini_config_dir: Path,
    project_dir: Path,
    python_exe: Path,
    server_name: str = "codebase-rag",
) -> Path:
    mcp_config_path = gemini_config_dir / "mcp_config.json"
    gemini_config_dir.mkdir(parents=True, exist_ok=True)

    if mcp_config_path.is_file():
        try:
            data: Dict[str, Any] = json.loads(mcp_config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    else:
        data = {}

    servers = data.setdefault("mcpServers", {})
    servers[server_name] = {
        "command": python_exe.as_posix(),
        "args": [(project_dir / "ai-automations" / "mcp" / "hybrid_rag_mcp.py").as_posix()],
        "env": {
            "REPO_ROOT": project_dir.as_posix(),
        },
    }

    mcp_config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return mcp_config_path


def install_sre_sidecars(
    gemini_config_dir: Path,
    project_dir: Path,
    cron_expr: str = "*/30 * * * *",
    slow_query_cron_expr: str = "0 */6 * * *",
    timezone_iana: str = "UTC",
) -> List[Dict[str, str]]:
    """Installs 3 independent Antigravity Automations, each invoking its Custom SRE Agent with an isolated state file."""
    project_slug = re.sub(r"[^a-z0-9]+", "-", project_dir.name.lower()).strip("-") or "project"
    abs_project = project_dir.resolve().as_posix()
    fetch_script = (project_dir.resolve() / "ai-automations" / "orchestration" / "fetch_telemetry.py").as_posix()

    sre_jobs = [
        {
            "key": "anomaly",
            "sidecar_id": f"sre-anomaly-{project_slug}",
            "display_name": f"SRE Anomaly Detector ({project_dir.name})",
            "agent_file": ".agents/agents/sre-anomaly-detector-agent.md",
            "agent_name": "sre-anomaly-detector-agent",
            "cron": cron_expr,
            "state_file": "ai-automations/state/sre-anomaly-state.json",
            "snapshot_file": "ai-automations/state/sre-anomaly-snapshot.json",
            "focus": "Prometheus Golden Signals (P95 latency, HTTP 5xx rate, DB connections)",
        },
        {
            "key": "error-logs",
            "sidecar_id": f"sre-error-logs-{project_slug}",
            "display_name": f"SRE Error Log Analyst ({project_dir.name})",
            "agent_file": ".agents/agents/sre-error-log-agent.md",
            "agent_name": "sre-error-log-agent",
            "cron": cron_expr,
            "state_file": "ai-automations/state/sre-error-log-state.json",
            "snapshot_file": "ai-automations/state/sre-error-log-snapshot.json",
            "focus": "Loki error/critical log streams deduplicated against #ai-ignore rules",
        },
        {
            "key": "slow-queries",
            "sidecar_id": f"sre-slow-queries-{project_slug}",
            "display_name": f"SRE Slow Query Optimizer ({project_dir.name})",
            "agent_file": ".agents/agents/sre-slow-query-agent.md",
            "agent_name": "sre-slow-query-agent",
            "cron": slow_query_cron_expr,
            "state_file": "ai-automations/state/sre-slow-query-state.json",
            "snapshot_file": "ai-automations/state/sre-slow-query-snapshot.json",
            "focus": "PostgreSQL pg_stat_statements queries exceeding PRD latency budget",
        },
    ]

    installed: List[Dict[str, str]] = []
    for job in sre_jobs:
        sidecar_dir = gemini_config_dir / "sidecars" / job["sidecar_id"]
        sidecar_dir.mkdir(parents=True, exist_ok=True)
        sidecar_path = sidecar_dir / "sidecar.json"

        raw_cron = job["cron"]
        schedule_str = raw_cron if raw_cron.startswith(("CRON_TZ=", "TZ=")) else f"CRON_TZ={timezone_iana} {raw_cron}"

        prompt = (
            f"Open the repository at {abs_project} and run Custom Agent `{job['agent_name']}` "
            f"defined in `{job['agent_file']}`: "
            f"1. Run `python {fetch_script} --state-file {job['state_file']} --output {job['snapshot_file']}` "
            "WITHOUT `--advance-checkpoint` so telemetry is collected strictly from `lastExecutionTimeUtc` up to NOW. "
            f"2. Execute `{job['agent_file']}` against `{job['snapshot_file']}` focusing on {job['focus']}. "
            "3. Suppress any anomaly matching an active `#ai-ignore` rule in `codebase-rag` or listed in `activeCooldowns`. "
            "4. For any actionable finding, create a dedicated `sre/<slug>` branch and dispatch `dev-triad` to stage a "
            "verified fix for Human Gate 2 review (NEVER commit directly to `main`). "
            f"5. Only after steps 1-4 succeed cleanly, run `python {fetch_script} --state-file {job['state_file']} "
            f"--output {job['snapshot_file']} --advance-checkpoint` (passing `--cooldown-signature <sig>` for ticketed anomalies) "
            "so the next scheduled run resumes from this exact UTC timestamp forward."
        )

        sidecar_data = {
            "builtin": "schedule",
            "args": [
                schedule_str,
                "agentapi",
                "new-conversation",
                "--",
                prompt,
            ],
            "restart_policy": "always",
            "display_name": job["display_name"],
            "description": (
                f"Periodic automation invoking Custom Agent '{job['agent_name']}' for {project_dir.name} "
                f"on schedule '{schedule_str}' with isolated checkpoint '{job['state_file']}'."
            ),
            "agent_permissions": {
                "workspace_uris": [project_dir.resolve().as_uri()],
                "access_grants": [
                    "mcp(codebase-rag/search_hybrid_rag)",
                    "mcp(codebase-rag/get_canonical_exemplar)",
                    "mcp(codebase-rag/validate_code_against_guardrails)",
                ],
            },
        }

        sidecar_path.write_text(json.dumps(sidecar_data, indent=2) + "\n", encoding="utf-8")
        installed.append(
            {
                "agent": job["agent_name"],
                "display_name": job["display_name"],
                "schedule": schedule_str,
                "state_file": job["state_file"],
                "sidecar_path": sidecar_path.as_posix(),
            }
        )

    return installed


def install_kit(
    target_dir: Path,
    gemini_config_dir: Path,
    install_sre_automation: bool = False,
    cron_expr: str = "*/30 * * * *",
    slow_query_cron_expr: str = "0 */6 * * *",
    timezone_iana: str = "UTC",
    skip_mcp_config: bool = False,
) -> Dict[str, Any]:
    target = target_dir.resolve()
    target.mkdir(parents=True, exist_ok=True)
    (target / "docs" / "adr").mkdir(parents=True, exist_ok=True)
    (target / "docs" / "decisions").mkdir(parents=True, exist_ok=True)

    # 1. Copy GEMINI.md to project root
    shutil.copy2(SRC_ROOT / "antigravity" / "GEMINI.md", target / "GEMINI.md")

    # 2. Copy .agents/ (7 Custom Agents, 4 Command Skills, and OS-patched hooks.json)
    agents_root = target / ".agents"
    agents_root.mkdir(parents=True, exist_ok=True)
    copy_tree(SRC_ROOT / "antigravity" / "agents", agents_root / "agents")
    copy_tree(SRC_ROOT / "antigravity" / "skills", agents_root / "skills")

    hooks_data = json.loads((SRC_ROOT / "antigravity" / "hooks.json").read_text(encoding="utf-8"))
    py_rel = relative_hook_python()
    hooks_data["ast-pre-write-gatekeeper"]["PreToolUse"][0]["hooks"][0]["command"] = (
        f"{py_rel} ../ai-automations/hooks/pre_write_ast_gate.py"
    )
    (agents_root / "hooks.json").write_text(json.dumps(hooks_data, indent=2) + "\n", encoding="utf-8")

    # 3. Copy ai-automations/ deterministic scripts, rules, and observability Docker Compose
    auto_root = target / "ai-automations"
    auto_root.mkdir(parents=True, exist_ok=True)
    (auto_root / "state").mkdir(parents=True, exist_ok=True)
    for subdir in ("mcp", "hooks", "orchestration", "observability", "rules"):
        copy_tree(SRC_ROOT / subdir, auto_root / subdir)

    # 4. Register codebase-rag in ~/.gemini/config/mcp_config.json
    mcp_path = None
    if not skip_mcp_config:
        mcp_path = merge_mcp_config(gemini_config_dir, target, venv_python_path(target))

    # 5. Optionally install the 3 dedicated periodic SRE Antigravity Automations
    sre_sidecars: List[Dict[str, str]] = []
    if install_sre_automation:
        sre_sidecars = install_sre_sidecars(
            gemini_config_dir=gemini_config_dir,
            project_dir=target,
            cron_expr=cron_expr,
            slow_query_cron_expr=slow_query_cron_expr,
            timezone_iana=timezone_iana,
        )

    return {
        "target": target.as_posix(),
        "gemini_md": (target / "GEMINI.md").as_posix(),
        "agents_dir": (agents_root / "agents").as_posix(),
        "skills_dir": (agents_root / "skills").as_posix(),
        "hooks_json": (agents_root / "hooks.json").as_posix(),
        "mcp_config": mcp_path.as_posix() if mcp_path else None,
        "sre_sidecars": sre_sidecars,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Install Local AI-SDLC Starter Kit into a target project")
    parser.add_argument("--target", type=Path, required=True, help="Target project directory (e.g. ./my-project)")
    parser.add_argument(
        "--gemini-config-dir",
        type=Path,
        default=Path.home() / ".gemini" / "config",
        help="Antigravity global config directory (default: ~/.gemini/config)",
    )
    parser.add_argument(
        "--install-sre-automation",
        action="store_true",
        help="Install 3 dedicated periodic Antigravity Automations invoking the 3 Custom SRE Agents",
    )
    parser.add_argument("--cron", default="*/30 * * * *", help="Cron for Anomaly & Error Log SRE agents (default: '*/30 * * * *')")
    parser.add_argument("--slow-query-cron", default="0 */6 * * *", help="Cron for Slow Query Optimizer SRE agent (default: '0 */6 * * *')")
    parser.add_argument("--timezone", default="UTC", help="IANA timezone for SRE crons (e.g. 'Europe/London', 'America/New_York')")
    parser.add_argument("--skip-mcp-config", action="store_true", help="Do not modify ~/.gemini/config/mcp_config.json")
    args = parser.parse_args()

    result = install_kit(
        target_dir=args.target,
        gemini_config_dir=args.gemini_config_dir,
        install_sre_automation=args.install_sre_automation,
        cron_expr=args.cron,
        slow_query_cron_expr=args.slow_query_cron,
        timezone_iana=args.timezone,
        skip_mcp_config=args.skip_mcp_config,
    )

    print("\n✅ Local AI-SDLC Starter Kit installed successfully!")
    print(f"   - Workspace Rules:  {result['gemini_md']}")
    print(f"   - 7 Custom Agents:  {result['agents_dir']}")
    print(f"   - 4 Command Skills: {result['skills_dir']}")
    print(f"   - AST Pre-Write:    {result['hooks_json']}")
    if result["mcp_config"]:
        print(f"   - MCP Registered:   {result['mcp_config']} (server: codebase-rag)")
    if result["sre_sidecars"]:
        print("\n🕒 Installed 3 Independent SRE Automations (enable in Antigravity's Automations Dashboard):")
        for sc in result["sre_sidecars"]:
            print(f"   - {sc['display_name']}  [{sc['schedule']}]  -> {sc['sidecar_path']}")

    print("\nNext step: Open your project in Antigravity, drop your idea into `MyFeature.md`, and type:")
    print('   "Use MyFeature.md through my AI-SDLC"\n')
    return 0


if __name__ == "__main__":
    sys.exit(main())
