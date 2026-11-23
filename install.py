#!/usr/bin/env python3
"""One-Command Installer for the Local AI-SDLC Starter Kit (Antigravity Command Centre).

Installs all Markdown agent files, skills, hooks, GEMINI.md, deterministic Python/Docker
helpers, MCP server registration, and (optionally) the periodic Antigravity SRE Automation.

Usage:
    # Install the AI-SDLC pipeline into your project:
    python install.py --target /path/to/my-project

    # Install the pipeline AND schedule the periodic SRE Automation:
    python install.py --target /path/to/my-project --install-sre-automation --timezone Europe/London --cron "*/30 * * * *"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Dict


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


def install_sre_sidecar(
    gemini_config_dir: Path,
    project_dir: Path,
    cron_expr: str = "*/30 * * * *",
    timezone_iana: str = "UTC",
) -> tuple[Path, str]:
    project_slug = re.sub(r"[^a-z0-9]+", "-", project_dir.name.lower()).strip("-") or "project"
    sidecar_id = f"sre-healer-{project_slug}"
    display_name = f"Periodic SRE Healer ({project_dir.name})"

    sidecar_dir = gemini_config_dir / "sidecars" / sidecar_id
    sidecar_dir.mkdir(parents=True, exist_ok=True)
    sidecar_path = sidecar_dir / "sidecar.json"

    schedule_str = cron_expr if cron_expr.startswith(("CRON_TZ=", "TZ=")) else f"CRON_TZ={timezone_iana} {cron_expr}"
    abs_project = project_dir.resolve().as_posix()
    fetch_script = (project_dir.resolve() / "ai-automations" / "orchestration" / "fetch_telemetry.py").as_posix()

    prompt = (
        f"Open the repository at {abs_project} and execute the `sre-healer` skill "
        "(`.agents/skills/sre-healer/SKILL.md`): "
        f"1. Run `python {fetch_script}` WITHOUT `--advance-checkpoint` so telemetry is collected strictly from "
        "`lastExecutionTimeUtc` in `ai-automations/sre-agent-state.json` up to NOW (or last 30m on cold start). "
        "2. Fan out in parallel to `.agents/agents/sre-anomaly-detector-agent.md`, "
        "`.agents/agents/sre-error-log-agent.md`, and `.agents/agents/sre-slow-query-agent.md`. "
        "3. Suppress any anomaly matching an active `#ai-ignore` rule in `codebase-rag` or listed in `activeCooldowns`. "
        "4. For any actionable latency breach, slow SQL query, or unhandled Loki error, create a dedicated `sre/<slug>` "
        "branch and dispatch `dev-triad` to stage a verified fix (NEVER commit directly to `main`). "
        "5. Output the Executive SRE Remediation Digest highlighting any `sre/*` branches ready for Human Gate 2 review. "
        f"6. Only after steps 1-5 succeed cleanly, run `python {fetch_script} --advance-checkpoint` "
        "(passing `--cooldown-signature <sig>` for any ticketed anomaly) so the next run resumes from this exact UTC timestamp forward."
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
        "display_name": display_name,
        "description": (
            f"Runs gapless Prometheus/Loki/PostgreSQL SRE triage for {project_dir.name} "
            f"on schedule '{schedule_str}', advancing lastExecutionTimeUtc only after clean completion."
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
    return sidecar_path, display_name


def install_kit(
    target_dir: Path,
    gemini_config_dir: Path,
    install_sre_automation: bool = False,
    cron_expr: str = "*/30 * * * *",
    timezone_iana: str = "UTC",
    skip_mcp_config: bool = False,
) -> Dict[str, Any]:
    target = target_dir.resolve()
    target.mkdir(parents=True, exist_ok=True)
    (target / "docs" / "adr").mkdir(parents=True, exist_ok=True)
    (target / "docs" / "decisions").mkdir(parents=True, exist_ok=True)

    # 1. Copy GEMINI.md to project root
    shutil.copy2(SRC_ROOT / "antigravity" / "GEMINI.md", target / "GEMINI.md")

    # 2. Copy .agents/ (agents/*.md, skills/*/SKILL.md, and OS-patched hooks.json)
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
    for subdir in ("mcp", "hooks", "orchestration", "observability", "rules"):
        copy_tree(SRC_ROOT / subdir, auto_root / subdir)

    # 4. Register codebase-rag in ~/.gemini/config/mcp_config.json
    mcp_path = None
    if not skip_mcp_config:
        mcp_path = merge_mcp_config(gemini_config_dir, target, venv_python_path(target))

    # 5. Optionally install the periodic SRE Antigravity Automation sidecar
    sidecar_path = None
    sidecar_display_name = None
    if install_sre_automation:
        sidecar_path, sidecar_display_name = install_sre_sidecar(
            gemini_config_dir=gemini_config_dir,
            project_dir=target,
            cron_expr=cron_expr,
            timezone_iana=timezone_iana,
        )

    return {
        "target": target.as_posix(),
        "gemini_md": (target / "GEMINI.md").as_posix(),
        "agents_dir": (agents_root / "agents").as_posix(),
        "skills_dir": (agents_root / "skills").as_posix(),
        "hooks_json": (agents_root / "hooks.json").as_posix(),
        "mcp_config": mcp_path.as_posix() if mcp_path else None,
        "sre_sidecar": sidecar_path.as_posix() if sidecar_path else None,
        "sre_display_name": sidecar_display_name,
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
        help="Also install the periodic SRE Healer Antigravity Automation sidecar",
    )
    parser.add_argument("--cron", default="*/30 * * * *", help="Cron expression for periodic SRE (default: '*/30 * * * *')")
    parser.add_argument("--timezone", default="UTC", help="IANA timezone for SRE cron (e.g. 'Europe/London', 'America/New_York')")
    parser.add_argument("--skip-mcp-config", action="store_true", help="Do not modify ~/.gemini/config/mcp_config.json")
    args = parser.parse_args()

    result = install_kit(
        target_dir=args.target,
        gemini_config_dir=args.gemini_config_dir,
        install_sre_automation=args.install_sre_automation,
        cron_expr=args.cron,
        timezone_iana=args.timezone,
        skip_mcp_config=args.skip_mcp_config,
    )

    print("\n✅ Local AI-SDLC Starter Kit installed successfully!")
    print(f"   - Workspace Rules:  {result['gemini_md']}")
    print(f"   - 7 Agent Prompts:  {result['agents_dir']}")
    print(f"   - 4 Command Skills: {result['skills_dir']}")
    print(f"   - AST Pre-Write:    {result['hooks_json']}")
    if result["mcp_config"]:
        print(f"   - MCP Registered:   {result['mcp_config']} (server: codebase-rag)")
    if result["sre_sidecar"]:
        print(f"   - SRE Automation:   {result['sre_sidecar']}")
        print(f"\n👉 Enable '{result['sre_display_name']}' in Antigravity's Automations Dashboard.")

    print("\nNext step: Open your project in Antigravity, drop your idea into `MyFeature.md`, and type:")
    print('   "Use MyFeature.md through my AI-SDLC"\n')
    return 0


if __name__ == "__main__":
    sys.exit(main())
