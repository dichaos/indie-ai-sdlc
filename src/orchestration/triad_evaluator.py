#!/usr/bin/env python3
"""Deterministic Evaluator Harness for the Antigravity Dev Triad (HomePulse).

Called by Antigravity's `dev-triad` skill during the Evaluator step of each cycle.
Runs deterministic verification checks that LLMs must never self-report:
1. Verifies Gate-1 approved `.feature` files were NOT tampered with (SHA-256 lockfile).
2. Runs Tree-Sitter AST guardrails across all staged/modified `.cs`, `.ts`, `.tsx` files.
3. Executes the configured build and BDD/unit test commands.
4. Outputs structured JSON diagnostics for the Enricher subagent on failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

MCP_DIR = Path(__file__).resolve().parents[1] / "mcp"
if str(MCP_DIR) not in sys.path:
    sys.path.insert(0, str(MCP_DIR))

from ast_parser import audit_source_guardrails


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def lock_feature_spec(feature_path: Path, lock_path: Path) -> Dict[str, Any]:
    """Locks a Human Gate 1 approved .feature file so the Fixer cannot weaken it."""
    if not feature_path.is_file():
        raise FileNotFoundError(f"Feature file not found: {feature_path}")
    digest = sha256_file(feature_path)
    lock_data = {"feature_path": feature_path.as_posix(), "sha256": digest}
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(json.dumps(lock_data, indent=2), encoding="utf-8")
    return lock_data


def verify_feature_lock(lock_path: Path) -> List[str]:
    if not lock_path.is_file():
        return []
    lock_data = json.loads(lock_path.read_text(encoding="utf-8"))
    feature_path = Path(lock_data["feature_path"])
    if not feature_path.is_file():
        return [f"Gate-1 Integrity Violation: Approved feature file '{feature_path}' was deleted."]
    current_hash = sha256_file(feature_path)
    if current_hash != lock_data["sha256"]:
        return [
            f"Gate-1 Integrity Violation: '{feature_path}' was modified after Human Gate 1 approval. "
            "The Fixer agent must NEVER weaken or edit approved BDD scenarios."
        ]
    return []


def collect_modified_files(repo_root: Path) -> List[Path]:
    """Returns modified/untracked .cs, .ts, and .tsx files from git status."""
    res = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        return []
    paths: List[Path] = []
    for line in res.stdout.splitlines():
        if len(line) < 4:
            continue
        rel = line[3:].strip().strip('"')
        if " -> " in rel:
            rel = rel.split(" -> ")[-1].strip()
        full = repo_root / rel
        if full.is_file() and full.suffix in (".cs", ".ts", ".tsx"):
            paths.append(full)
    return paths


def run_evaluation(
    repo_root: Path,
    lock_path: Path | None = None,
    build_cmd: str = "",
    test_cmd: str = "",
    explicit_files: List[Path] | None = None,
) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "all_green": False,
        "gate1_integrity_passed": True,
        "ast_passed": True,
        "build_passed": True,
        "tests_passed": True,
        "violations": [],
        "build_output": "",
        "test_output": "",
    }

    # 1. Verify Human Gate 1 .feature immutability
    if lock_path is not None:
        lock_errors = verify_feature_lock(lock_path)
        if lock_errors:
            report["gate1_integrity_passed"] = False
            report["violations"].extend(lock_errors)
            return report

    # 2. Tree-Sitter AST Audit across candidate files
    target_files = explicit_files if explicit_files is not None else collect_modified_files(repo_root)
    for fpath in target_files:
        try:
            rel = fpath.resolve().relative_to(repo_root.resolve()).as_posix()
        except ValueError:
            rel = fpath.as_posix()
        code = fpath.read_text(encoding="utf-8", errors="replace")
        ast_res = audit_source_guardrails(rel, code)
        if not ast_res["passed"]:
            report["ast_passed"] = False
            report["violations"].extend(ast_res["violations"])

    if not report["ast_passed"]:
        return report

    # 3. Compile check (if provided)
    if build_cmd:
        build_res = subprocess.run(build_cmd, shell=True, cwd=repo_root, capture_output=True, text=True)
        report["build_output"] = (build_res.stdout + "\n" + build_res.stderr)[-2000:].strip()
        if build_res.returncode != 0:
            report["build_passed"] = False
            return report

    # 4. Unit & BDD test execution (if provided)
    if test_cmd:
        test_res = subprocess.run(test_cmd, shell=True, cwd=repo_root, capture_output=True, text=True)
        report["test_output"] = (test_res.stdout + "\n" + test_res.stderr)[-2500:].strip()
        if test_res.returncode != 0:
            report["tests_passed"] = False
            return report

    report["all_green"] = True
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="HomePulse Deterministic Dev Triad Evaluator")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd(), help="Repository root path")
    parser.add_argument("--lock-feature", type=Path, help="Lock a Gate-1 approved .feature file and exit")
    parser.add_argument("--lock-file", type=Path, default=Path(".agents/triad-gate1.lock.json"))
    parser.add_argument("--build-cmd", type=str, default="", help="Build command (e.g. 'dotnet build --configuration Release')")
    parser.add_argument("--test-cmd", type=str, default="", help="Test command (e.g. 'dotnet test --no-build --filter SolarPowerDiversion')")
    args = parser.parse_args()

    if args.lock_feature:
        data = lock_feature_spec(args.lock_feature, args.lock_file)
        print(json.dumps({"status": "locked", **data}, indent=2))
        return 0

    report = run_evaluation(
        repo_root=args.repo_root,
        lock_path=args.lock_file if args.lock_file.is_file() else None,
        build_cmd=args.build_cmd,
        test_cmd=args.test_cmd,
    )
    print(json.dumps(report, indent=2))
    return 0 if report["all_green"] else 1


if __name__ == "__main__":
    sys.exit(main())
