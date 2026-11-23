#!/usr/bin/env python3
"""Cross-Platform 3-Minute Local DevSecOps Gate.

Runs four deterministic security & verification checks locally for £0.00:
1. SAST: Ephemeral Docker `semgrep/semgrep` (OWASP Top 10 + custom architecture rules).
2. SCA (Package Vulnerability Scan): Ephemeral Docker `aquasec/trivy` (universal lockfile
   scanner across ecosystems) PLUS an optional stack-specific `sca_command` configured in
   `ai-automations/rules/devsecops.config.json` or `--sca-cmd`.
3. DAST: Ephemeral Docker `zaproxy/zap-stable` running `zap-api-scan.py` against OpenAPI spec.
4. Differential Coverage: `diff-cover` enforcing >= 90% coverage on newly added/modified lines.

Emits a single JSON summary on stdout that Antigravity's `devsecops-gate` skill reads.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List


def load_devsecops_config(config_path: Path) -> Dict[str, Any]:
    """Loads optional per-project DevSecOps overrides (e.g., native package audit command)."""
    if config_path.is_file():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    return {}


def run_semgrep(repo_root: Path, custom_rules: Path) -> Dict[str, Any]:
    cmd = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{repo_root.resolve()}:/src:ro",
        "semgrep/semgrep",
        "semgrep",
        "scan",
        "--config",
        "p/owasp-top-ten",
        "--config",
        "p/security-audit",
    ]
    if custom_rules.is_file():
        rel_rules = custom_rules.resolve().relative_to(repo_root.resolve()).as_posix()
        cmd.extend(["--config", f"/src/{rel_rules}"])
    cmd.extend(["--error", "--json", "/src"])

    res = subprocess.run(cmd, capture_output=True, text=True)
    findings: List[Dict[str, Any]] = []
    try:
        parsed = json.loads(res.stdout)
        findings = [
            {
                "rule_id": r.get("check_id"),
                "path": r.get("path"),
                "line": r.get("start", {}).get("line"),
                "severity": r.get("extra", {}).get("severity"),
                "message": r.get("extra", {}).get("message"),
            }
            for r in parsed.get("results", [])
        ]
    except json.JSONDecodeError:
        pass

    return {
        "passed": res.returncode == 0,
        "finding_count": len(findings),
        "findings": findings[:25],
        "stderr": res.stderr[-800:].strip() if res.returncode != 0 else "",
    }


def run_sca(
    repo_root: Path,
    sca_cmd: str = "",
    severity: str = "HIGH,CRITICAL",
    use_trivy: bool = True,
) -> Dict[str, Any]:
    """Runs Software Composition Analysis (vulnerable dependency check).

    Uses universal ephemeral Docker `aquasec/trivy` by default and optionally runs a
    project-configured native package-audit command (`sca_command`).
    """
    result: Dict[str, Any] = {
        "passed": True,
        "trivy": {"skipped": not use_trivy, "passed": True, "vulnerabilities": []},
        "native_audit": {"skipped": not bool(sca_cmd), "passed": True},
    }

    if use_trivy:
        cmd = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{repo_root.resolve()}:/src:ro",
            "aquasec/trivy",
            "fs",
            "--scanners",
            "vuln",
            "--severity",
            severity,
            "--exit-code",
            "1",
            "--format",
            "json",
            "/src",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        vulns: List[Dict[str, Any]] = []
        try:
            parsed = json.loads(res.stdout)
            for target in parsed.get("Results", []):
                for v in target.get("Vulnerabilities") or []:
                    vulns.append(
                        {
                            "target": target.get("Target"),
                            "pkg": v.get("PkgName"),
                            "installed": v.get("InstalledVersion"),
                            "fixed": v.get("FixedVersion", ""),
                            "severity": v.get("Severity"),
                            "cve": v.get("VulnerabilityID"),
                        }
                    )
        except json.JSONDecodeError:
            pass

        trivy_passed = res.returncode == 0
        result["trivy"] = {
            "passed": trivy_passed,
            "vulnerability_count": len(vulns),
            "vulnerabilities": vulns[:25],
            "stderr": res.stderr[-800:].strip() if not trivy_passed else "",
        }
        if not trivy_passed:
            result["passed"] = False

    if sca_cmd:
        native_res = subprocess.run(sca_cmd, shell=True, cwd=repo_root, capture_output=True, text=True)
        native_passed = native_res.returncode == 0
        result["native_audit"] = {
            "command": sca_cmd,
            "passed": native_passed,
            "output": (native_res.stdout + "\n" + native_res.stderr)[-1500:].strip(),
        }
        if not native_passed:
            result["passed"] = False

    return result


def run_zap_api_scan(repo_root: Path, openapi_url: str, reports_dir: Path) -> Dict[str, Any]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_file = reports_dir / "zap-api-report.json"

    cmd = ["docker", "run", "--rm"]
    # Linux Docker Engine requires explicit host-gateway mapping for host.docker.internal
    if platform.system().lower() == "linux":
        cmd.extend(["--add-host=host.docker.internal:host-gateway"])

    cmd.extend(
        [
            "-v",
            f"{reports_dir.resolve()}:/zap/wrk",
            "zaproxy/zap-stable",
            "zap-api-scan.py",
            "-t",
            openapi_url,
            "-f",
            "openapi",
            "-J",
            "zap-api-report.json",
        ]
    )

    res = subprocess.run(cmd, capture_output=True, text=True)
    alerts: List[Dict[str, Any]] = []
    if report_file.is_file():
        try:
            zap_data = json.loads(report_file.read_text(encoding="utf-8"))
            for site in zap_data.get("site", []):
                for alert in site.get("alerts", []):
                    alerts.append(
                        {
                            "name": alert.get("name"),
                            "riskdesc": alert.get("riskdesc"),
                            "count": alert.get("count"),
                            "solution": alert.get("solution", "")[:240],
                        }
                    )
        except json.JSONDecodeError:
            pass

    high_or_med = [a for a in alerts if a.get("riskdesc", "").startswith(("High", "Medium"))]
    return {
        "passed": len(high_or_med) == 0 and res.returncode in (0, 2),
        "high_medium_count": len(high_or_med),
        "alerts": alerts[:25],
        "report_path": report_file.as_posix(),
    }


def run_diff_coverage(
    repo_root: Path,
    coverage_xml: Path,
    compare_branch: str = "main",
    min_percent: int = 90,
) -> Dict[str, Any]:
    if not coverage_xml.is_file():
        return {
            "passed": False,
            "error": f"Coverage XML not found at '{coverage_xml}'. Run your test suite with Cobertura coverage first.",
        }

    cmd = [
        sys.executable,
        "-m",
        "diff_cover.diff_cover_tool",
        str(coverage_xml),
        "--compare-branch",
        compare_branch,
        "--fail-under",
        str(min_percent),
    ]
    res = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True)
    return {
        "passed": res.returncode == 0,
        "min_percent": min_percent,
        "output": (res.stdout + "\n" + res.stderr)[-1500:].strip(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="3-Minute Local DevSecOps Gate (SAST + SCA + DAST + Diff-Cover)")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path, default=Path("ai-automations/rules/devsecops.config.json"))
    parser.add_argument("--custom-rules", type=Path, default=Path("ai-automations/rules/custom-architecture.yml"))
    parser.add_argument("--openapi-url", default="http://host.docker.internal:5000/openapi.json")
    parser.add_argument("--coverage-xml", type=Path, default=Path("reports/coverage.cobertura.xml"))
    parser.add_argument("--compare-branch", default="main")
    parser.add_argument("--min-coverage", type=int, default=90)
    parser.add_argument("--sca-cmd", default="", help="Optional stack-specific package audit command")
    parser.add_argument("--sca-severity", default="HIGH,CRITICAL", help="Trivy severity threshold")
    parser.add_argument("--skip-sca", action="store_true")
    parser.add_argument("--skip-trivy", action="store_true")
    parser.add_argument("--skip-dast", action="store_true")
    parser.add_argument("--skip-coverage", action="store_true")
    args = parser.parse_args()

    cfg = load_devsecops_config(args.config)
    effective_sca_cmd = args.sca_cmd or str(cfg.get("sca_command", "")).strip()
    effective_severity = str(cfg.get("sca_severity", args.sca_severity))

    reports_dir = args.repo_root / "reports"
    summary: Dict[str, Any] = {
        "sast": run_semgrep(args.repo_root, args.custom_rules),
        "sca": {"skipped": True, "passed": True}
        if args.skip_sca
        else run_sca(
            args.repo_root,
            sca_cmd=effective_sca_cmd,
            severity=effective_severity,
            use_trivy=not args.skip_trivy,
        ),
        "dast": {"skipped": True, "passed": True}
        if args.skip_dast
        else run_zap_api_scan(args.repo_root, args.openapi_url, reports_dir),
        "diff_coverage": {"skipped": True, "passed": True}
        if args.skip_coverage
        else run_diff_coverage(args.repo_root, args.coverage_xml, args.compare_branch, args.min_coverage),
    }
    summary["all_passed"] = all(
        section.get("passed", False)
        for section in (summary["sast"], summary["sca"], summary["dast"], summary["diff_coverage"])
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
