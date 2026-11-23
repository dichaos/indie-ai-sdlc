#!/usr/bin/env python3
"""Antigravity PreToolUse Lifecycle Hook: Physical Tree-Sitter AST Gatekeeper.

Registered in .agents/hooks.json to intercept `write_file` and `edit_file` BEFORE
any C# or TypeScript/TSX file touches disk.

Contract (Antigravity PreToolUse):
- Reads camelCase JSON payload from stdin containing `toolCall.name` and `toolCall.args`.
- Outputs JSON on stdout:
    {"decision": "allow"}
  or
    {"decision": "deny", "reason": "<exact AST violation diagnostic>"}
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

MCP_DIR = Path(__file__).resolve().parents[1] / "mcp"
if str(MCP_DIR) not in sys.path:
    sys.path.insert(0, str(MCP_DIR))

from ast_parser import audit_source_guardrails


def evaluate_hook_payload(payload: dict) -> dict:
    tool_call = payload.get("toolCall", {})
    tool_name = tool_call.get("name", "")
    args = tool_call.get("args", {})

    file_path = str(args.get("Path") or args.get("path") or "")
    if not file_path.endswith((".cs", ".ts", ".tsx")):
        return {"decision": "allow"}

    if tool_name == "write_file":
        candidate_code = str(args.get("Content") or args.get("content") or "")
    elif tool_name == "edit_file":
        target = str(args.get("Target") or "")
        replacement = str(args.get("Replacement") or "")
        p = Path(file_path)
        if not p.is_file() or not target:
            return {"decision": "allow"}
        existing = p.read_text(encoding="utf-8", errors="replace")
        candidate_code = existing.replace(target, replacement)
    else:
        return {"decision": "allow"}

    report = audit_source_guardrails(file_path, candidate_code)
    if report["passed"]:
        return {"decision": "allow"}

    reason = "AST Pre-Write Hook Blocked Save:\n- " + "\n- ".join(report["violations"])
    return {"decision": "deny", "reason": reason}


def main() -> int:
    raw = sys.stdin.read().strip()
    if not raw:
        print(json.dumps({"decision": "allow"}))
        return 0

    try:
        payload = json.loads(raw)
        result = evaluate_hook_payload(payload)
    except Exception as exc:
        # Fail-open on malformed hook input so the IDE never wedges, while surfacing diagnostics
        result = {"decision": "allow", "reason": f"AST hook skipped due to parser input error: {exc}"}

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
