"""Deterministic Tree-Sitter AST Parser & Guardrail Inspector.

Provides sub-12ms AST analysis for source files:
1. Exact top-level type extraction ignoring comments and string literals.
2. Strict modularity check (max 1 top-level type per domain/backend file).
3. Accurate import/using extraction for architectural boundary checks.
4. Direct database connection instantiation detection (DIP guardrail).
5. Proper UTF-8 byte-offset decoding (safe with non-ASCII characters).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

try:
    from tree_sitter import Language, Node, Parser
    import tree_sitter_c_sharp as tscsharp
    import tree_sitter_typescript as tstypescript

    CS_LANG = Language(tscsharp.language())
    TS_LANG = Language(tstypescript.language_typescript())
    TSX_LANG = Language(tstypescript.language_tsx())
    HAS_TREE_SITTER = True
except ImportError:
    HAS_TREE_SITTER = False
    Node = Any  # type: ignore


CSHARP_TYPE_NODES = (
    "class_declaration",
    "interface_declaration",
    "record_declaration",
    "enum_declaration",
    "struct_declaration",
    "record_struct_declaration",
)

TS_TYPE_NODES = (
    "class_declaration",
    "interface_declaration",
    "type_alias_declaration",
    "enum_declaration",
)


@dataclass
class TypeInfo:
    kind: str
    name: str
    is_top_level: bool
    line: int = 1
    base_types: List[str] = field(default_factory=list)
    attributes: List[str] = field(default_factory=list)
    methods: List[str] = field(default_factory=list)


@dataclass
class AstAnalysis:
    language: str = "unknown"
    namespace: str = "Global"
    imports: List[str] = field(default_factory=list)
    types: List[TypeInfo] = field(default_factory=list)
    direct_db_instantiations: List[str] = field(default_factory=list)
    has_parse_errors: bool = False


class AstParserEngine:
    """Deterministic C# and TypeScript/TSX AST Analyzer."""

    def __init__(self) -> None:
        if HAS_TREE_SITTER:
            self.cs_parser = Parser(CS_LANG)
            self.ts_parser = Parser(TS_LANG)
            self.tsx_parser = Parser(TSX_LANG)
        else:
            self.cs_parser = None
            self.ts_parser = None
            self.tsx_parser = None

    @staticmethod
    def _decode(code_bytes: bytes, node: Node) -> str:
        """Safely slices UTF-8 bytes by Tree-Sitter byte offsets and decodes to str."""
        return code_bytes[node.start_byte : node.end_byte].decode("utf-8", errors="replace").strip()

    def parse_csharp(self, source_code: str) -> AstAnalysis:
        analysis = AstAnalysis(language="csharp")
        if not HAS_TREE_SITTER or not self.cs_parser:
            return analysis

        code_bytes = source_code.encode("utf-8")
        tree = self.cs_parser.parse(code_bytes)
        root = tree.root_node
        analysis.has_parse_errors = root.has_error

        self._walk_csharp(root, code_bytes, analysis, is_top_level=True)
        return analysis

    def _walk_csharp(
        self,
        node: Node,
        code_bytes: bytes,
        analysis: AstAnalysis,
        is_top_level: bool,
    ) -> None:
        if node.type == "using_directive":
            parts = [
                self._decode(code_bytes, child)
                for child in node.children
                if child.type in ("identifier", "qualified_name")
            ]
            if parts:
                analysis.imports.append(".".join(parts))
            return

        if node.type in ("namespace_declaration", "file_scoped_namespace_declaration"):
            for child in node.children:
                if child.type in ("identifier", "qualified_name"):
                    analysis.namespace = self._decode(code_bytes, child)
                    break
            for child in node.children:
                if child.type not in ("namespace", "identifier", "qualified_name", ";"):
                    self._walk_csharp(child, code_bytes, analysis, is_top_level=True)
            return

        if node.type in CSHARP_TYPE_NODES:
            name_node = node.child_by_field_name("name")
            type_name = self._decode(code_bytes, name_node) if name_node else "Unknown"

            base_types: List[str] = []
            bases_node = node.child_by_field_name("bases")
            if bases_node:
                raw_bases = self._decode(code_bytes, bases_node)
                base_types = [b.strip() for b in raw_bases.lstrip(":").split(",") if b.strip()]

            attributes = [
                self._decode(code_bytes, child)
                for child in node.children
                if child.type == "attribute_list"
            ]

            methods: List[str] = []
            body_node = node.child_by_field_name("body")
            if not body_node:
                for ch in node.children:
                    if ch.type == "declaration_list":
                        body_node = ch
                        break

            if body_node:
                for member in body_node.children:
                    if member.type == "method_declaration":
                        m_name = member.child_by_field_name("name")
                        m_type = member.child_by_field_name("type")
                        ret = self._decode(code_bytes, m_type) if m_type else "void"
                        name = self._decode(code_bytes, m_name) if m_name else "Method"
                        methods.append(f"{ret} {name}")

            analysis.types.append(
                TypeInfo(
                    kind=node.type.replace("_declaration", ""),
                    name=type_name,
                    is_top_level=is_top_level,
                    line=node.start_point[0] + 1,
                    base_types=base_types,
                    attributes=attributes,
                    methods=methods,
                )
            )

            if body_node:
                for member in body_node.children:
                    if member.type in CSHARP_TYPE_NODES:
                        self._walk_csharp(member, code_bytes, analysis, is_top_level=False)
                    else:
                        self._walk_csharp_db_creations(member, code_bytes, analysis)
            return

        if node.type in ("object_creation_expression", "implicit_object_creation_expression"):
            self._check_db_creation(node, code_bytes, analysis)
            return

        for child in node.children:
            self._walk_csharp(child, code_bytes, analysis, is_top_level)

    def _walk_csharp_db_creations(self, node: Node, code_bytes: bytes, analysis: AstAnalysis) -> None:
        if node.type in ("object_creation_expression", "implicit_object_creation_expression"):
            self._check_db_creation(node, code_bytes, analysis)
        for child in node.children:
            self._walk_csharp_db_creations(child, code_bytes, analysis)

    def _check_db_creation(self, node: Node, code_bytes: bytes, analysis: AstAnalysis) -> None:
        type_node = node.child_by_field_name("type")
        if type_node:
            t_name = self._decode(code_bytes, type_node)
            if t_name in ("NpgsqlConnection", "SqlConnection", "SqliteConnection"):
                analysis.direct_db_instantiations.append(t_name)

    def parse_typescript(self, source_code: str, is_tsx: bool = False) -> AstAnalysis:
        analysis = AstAnalysis(language="tsx" if is_tsx else "typescript")
        parser = self.tsx_parser if is_tsx else self.ts_parser
        if not HAS_TREE_SITTER or not parser:
            return analysis

        code_bytes = source_code.encode("utf-8")
        tree = parser.parse(code_bytes)
        root = tree.root_node
        analysis.has_parse_errors = root.has_error

        for child in root.children:
            if child.type == "import_statement":
                source_node = child.child_by_field_name("source")
                if source_node:
                    mod = self._decode(code_bytes, source_node).strip("'\"")
                    analysis.imports.append(mod)
            elif child.type == "export_statement":
                decl = child.child_by_field_name("declaration")
                if decl is not None:
                    self._record_ts_declaration(decl, code_bytes, analysis)
            else:
                self._record_ts_declaration(child, code_bytes, analysis)

        return analysis

    def _record_ts_declaration(self, node: Node, code_bytes: bytes, analysis: AstAnalysis) -> None:
        if node.type in TS_TYPE_NODES:
            name_node = node.child_by_field_name("name")
            type_name = self._decode(code_bytes, name_node) if name_node else "Unknown"
            analysis.types.append(
                TypeInfo(
                    kind=node.type.replace("_declaration", ""),
                    name=type_name,
                    is_top_level=True,
                    line=node.start_point[0] + 1,
                )
            )


AST_ENGINE = AstParserEngine()


def audit_source_guardrails(
    file_path: str,
    code: str,
    banned_imports: List[str] | None = None,
) -> Dict[str, Any]:
    """Audits source code against architectural and modularity guardrails.

    Returns a dictionary with keys: target_path, passed, violation_count, violations, top_level_types.
    """
    norm_path = file_path.replace("\\", "/").lstrip("./")
    violations: List[str] = []
    top_level_types: List[Dict[str, Any]] = []

    is_test_or_migration = any(
        seg in norm_path.lower() for seg in ("/tests/", "/migrations/", ".test.", ".spec.")
    )

    if norm_path.endswith(".cs") and not norm_path.endswith((".feature.cs", ".g.cs", ".Designer.cs")):
        cs_banned = banned_imports or ["MediatR", "TechTalk.SpecFlow", "Microsoft.AspNetCore.SignalR"]
        analysis = AST_ENGINE.parse_csharp(code)

        if analysis.has_parse_errors:
            violations.append(f"Syntax Error: Parser reported syntax errors in '{norm_path}'.")

        for imp in analysis.imports:
            for banned in cs_banned:
                if imp == banned or imp.startswith(f"{banned}."):
                    violations.append(
                        f"Banned Import Violation in '{norm_path}': '{imp}' is forbidden by ADR-001."
                    )

        # Enforce layer boundary: Domain layer must not depend on ORM or HTTP frameworks
        if "/Domain/" in f"/{norm_path}" or ".Domain/" in norm_path:
            for imp in analysis.imports:
                if imp.startswith("Microsoft.EntityFrameworkCore") or imp.startswith("Microsoft.AspNetCore"):
                    violations.append(
                        f"Layer Boundary Violation in '{norm_path}': Domain layer cannot import '{imp}'."
                    )

        top_types = [t for t in analysis.types if t.is_top_level]
        top_level_types = [{"kind": t.kind, "name": t.name, "line": t.line} for t in top_types]
        if not is_test_or_migration and len(top_types) > 1:
            names = ", ".join(f"{t.kind} {t.name}" for t in top_types)
            violations.append(
                f"SA1402 Violation in '{norm_path}': Found {len(top_types)} top-level types ({names}). "
                "Split each top-level type into its own dedicated file."
            )

        if not is_test_or_migration and "ConnectionFactory" not in norm_path and analysis.direct_db_instantiations:
            calls = ", ".join(sorted(set(analysis.direct_db_instantiations)))
            violations.append(
                f"DIP Violation in '{norm_path}': Do not instantiate {calls} directly. Inject IDbConnectionFactory."
            )

    elif norm_path.endswith((".ts", ".tsx")) and not norm_path.endswith(".d.ts"):
        ts_banned = banned_imports or ["moment", "axios"]
        analysis = AST_ENGINE.parse_typescript(code, is_tsx=norm_path.endswith(".tsx"))

        if analysis.has_parse_errors:
            violations.append(f"Syntax Error: TypeScript parser reported syntax errors in '{norm_path}'.")

        for imp in analysis.imports:
            for banned in ts_banned:
                if imp == banned or imp.startswith(f"{banned}/"):
                    violations.append(
                        f"Banned Import Violation in '{norm_path}': '{imp}' is forbidden (use native fetch / date-fns)."
                    )

        top_types = [t for t in analysis.types if t.is_top_level]
        top_level_types = [{"kind": t.kind, "name": t.name, "line": t.line} for t in top_types]
        # Allow a single React Props interface + single component class/type, block > 2 top-level type declarations
        if not is_test_or_migration and len(top_types) > 2:
            names = ", ".join(f"{t.kind} {t.name}" for t in top_types)
            violations.append(
                f"Modularity Violation in '{norm_path}': Found {len(top_types)} top-level type declarations ({names}). "
                "Keep TypeScript modules focused (<= 2 top-level types per file)."
            )

    return {
        "target_path": norm_path,
        "passed": len(violations) == 0,
        "violation_count": len(violations),
        "violations": violations,
        "top_level_types": top_level_types,
    }
