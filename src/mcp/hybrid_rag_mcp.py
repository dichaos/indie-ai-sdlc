#!/usr/bin/env python3
"""Local Zero-Cloud Hybrid RAG & AST Guardrail stdio MCP Server.

Runs locally over stdio inside Antigravity (registered in ~/.gemini/config/mcp_config.json).
Requires ZERO external API keys, vector databases, or cloud services:
- SQLite FTS5 (:memory:) BM25 lexical search (exact class, method, error signatures)
- scikit-learn TF-IDF (1-2 gram) cosine similarity (conceptual PRD/ADR search)
- Reciprocal Rank Fusion (RRF) with priority boosting for #ai-pin / #ai-ignore decisions
- Automatic mtime-based re-indexing when workspace files change
- Tree-Sitter AST pre-write guardrail validation
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    from mcp.server.mcpserver import MCPServer as FastMCP  # type: ignore

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

try:
    from ast_parser import AST_ENGINE, HAS_TREE_SITTER, audit_source_guardrails
except ImportError:
    from .ast_parser import AST_ENGINE, HAS_TREE_SITTER, audit_source_guardrails


REPO_ROOT = Path(
    os.environ.get("REPO_ROOT", str(Path(__file__).resolve().parents[2]))
).resolve()

PRUNED_DIRS = {
    "bin",
    "obj",
    "Migrations",
    "node_modules",
    "dist",
    "build",
    "test-results",
    ".git",
    ".venv",
    "venv",
    "__pycache__",
}

mcp = FastMCP("codebase-rag")


@dataclass
class KnowledgeChunk:
    chunk_id: str
    title: str
    category: str  # "decision-memory", "prd-specification", "architecture-doc", "code-symbol"
    rel_path: str
    content: str
    metadata: Dict[str, Any]


class HybridRagEngine:
    """In-memory SQLite FTS5 (BM25) + scikit-learn TF-IDF Hybrid RRF Engine with auto-refresh."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.chunks: List[KnowledgeChunk] = []
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.vectorizer: Optional[Any] = None
        self.tfidf_matrix: Optional[Any] = None
        self._file_fingerprint: Dict[str, float] = {}
        self.rebuild_index()

    def _discover_indexable_files(self) -> List[Tuple[Path, str]]:
        """Collects docs, decisions, root rules, and source files with their categories."""
        files: List[Tuple[Path, str]] = []

        for root_doc in ("GEMINI.md", "AGENTS.md", "README.md"):
            p = self.repo_root / root_doc
            if p.is_file():
                files.append((p, "architecture-doc"))

        docs_dir = self.repo_root / "docs"
        if docs_dir.is_dir():
            for md_file in sorted(docs_dir.rglob("*.md")):
                rel = md_file.relative_to(self.repo_root).as_posix()
                if rel.startswith("docs/decisions/"):
                    files.append((md_file, "decision-memory"))
                elif md_file.name.lower() == "prd.md":
                    files.append((md_file, "prd-specification"))
                else:
                    files.append((md_file, "architecture-doc"))

        src_dir = self.repo_root / "src"
        if src_dir.is_dir():
            for root, dirs, fnames in os.walk(src_dir):
                dirs[:] = [d for d in dirs if d not in PRUNED_DIRS and not d.startswith(".")]
                for fname in sorted(fnames):
                    if fname.endswith((".cs", ".ts", ".tsx")) and not fname.endswith(
                        (".g.cs", ".Designer.cs", ".d.ts")
                    ):
                        files.append((Path(root) / fname, "code-symbol"))

        # Index repository tests & BDD .feature files so QA & Enricher agents can read all existing tests
        tests_dir = self.repo_root / "tests"
        if tests_dir.is_dir():
            for root, dirs, fnames in os.walk(tests_dir):
                dirs[:] = [d for d in dirs if d not in PRUNED_DIRS and not d.startswith(".")]
                for fname in sorted(fnames):
                    fpath = Path(root) / fname
                    if fname.endswith(".feature"):
                        files.append((fpath, "test-spec"))
                    elif fname.endswith((".cs", ".ts", ".tsx", ".py")) and not fname.endswith((".feature.cs", ".g.cs")):
                        files.append((fpath, "test-suite"))

        return files

    def _compute_fingerprint(self, files: List[Tuple[Path, str]]) -> Dict[str, float]:
        fp: Dict[str, float] = {}
        for path, _ in files:
            try:
                fp[path.relative_to(self.repo_root).as_posix()] = path.stat().st_mtime
            except OSError:
                continue
        return fp

    def refresh_if_changed(self) -> bool:
        """Automatically rebuilds the in-memory index if any tracked file was added, edited, or deleted."""
        files = self._discover_indexable_files()
        current_fp = self._compute_fingerprint(files)
        if current_fp != self._file_fingerprint:
            self.rebuild_index(files=files, fingerprint=current_fp)
            return True
        return False

    def rebuild_index(
        self,
        files: Optional[List[Tuple[Path, str]]] = None,
        fingerprint: Optional[Dict[str, float]] = None,
    ) -> None:
        """Rebuilds SQLite FTS5 and TF-IDF indices in RAM."""
        if files is None:
            files = self._discover_indexable_files()
        if fingerprint is None:
            fingerprint = self._compute_fingerprint(files)

        self._file_fingerprint = fingerprint
        self.chunks.clear()

        cur = self.conn.cursor()
        cur.execute("DROP TABLE IF EXISTS fts_chunks;")
        cur.execute(
            "CREATE VIRTUAL TABLE fts_chunks "
            "USING fts5(chunk_id, title, category, rel_path, content, tokenize='porter');"
        )

        for path, category in files:
            if category == "code-symbol":
                self._index_code_symbol(path)
            else:
                self._index_markdown_file(path, category=category)

        for chunk in self.chunks:
            cur.execute(
                "INSERT INTO fts_chunks (chunk_id, title, category, rel_path, content) VALUES (?, ?, ?, ?, ?);",
                (chunk.chunk_id, chunk.title, chunk.category, chunk.rel_path, chunk.content),
            )
        self.conn.commit()

        if HAS_SKLEARN and self.chunks:
            corpus = [f"{c.title}\n{c.rel_path}\n{c.content}" for c in self.chunks]
            self.vectorizer = TfidfVectorizer(
                analyzer="word",
                ngram_range=(1, 2),
                max_features=12000,
                lowercase=True,
            )
            self.tfidf_matrix = self.vectorizer.fit_transform(corpus)
        else:
            self.vectorizer = None
            self.tfidf_matrix = None

    def _index_markdown_file(self, path: Path, category: str) -> None:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        rel_path = path.relative_to(self.repo_root).as_posix()
        split_pattern = r"(?m)^(?=#{2,3}\s+)" if category == "prd-specification" else r"(?m)^(?=##\s+)"
        sections = re.split(split_pattern, text)
        for idx, sec in enumerate(sections):
            sec = sec.strip()
            if not sec:
                continue
            first_line = sec.splitlines()[0].lstrip("# ").strip()
            meta: Dict[str, Any] = {"file": rel_path}
            if "#ai-pin" in text.lower():
                meta["tag"] = "ai-pin"
            elif "#ai-ignore" in text.lower():
                meta["tag"] = "ai-ignore"
            if "status: superseded" in text.lower():
                meta["superseded"] = True
            self.chunks.append(
                KnowledgeChunk(
                    chunk_id=f"{rel_path}#sec{idx}",
                    title=f"{path.name}: {first_line[:90]}",
                    category=category,
                    rel_path=rel_path,
                    content=sec[:4000],
                    metadata=meta,
                )
            )

    def _index_code_symbol(self, path: Path) -> None:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        rel_path = path.relative_to(self.repo_root).as_posix()

        if HAS_TREE_SITTER:
            if path.suffix == ".cs":
                analysis = AST_ENGINE.parse_csharp(text)
            else:
                analysis = AST_ENGINE.parse_typescript(text, is_tsx=path.suffix == ".tsx")
            type_summaries = [
                f"{t.kind} {t.name}" + (f" : {', '.join(t.base_types)}" if t.base_types else "")
                for t in analysis.types
            ]
            all_methods = [m for t in analysis.types for m in t.methods]
            summary = (
                f"File: {rel_path} (Tree-Sitter AST: {analysis.language})\n"
                f"Namespace: {analysis.namespace}\n"
                f"Imports: {', '.join(analysis.imports[:15])}\n"
                f"Declared Types: {', '.join(type_summaries) or path.stem}\n"
                f"Methods: {', '.join(all_methods[:15])}\n"
            )
            self.chunks.append(
                KnowledgeChunk(
                    chunk_id=rel_path,
                    title=f"{analysis.namespace}.{path.stem}",
                    category="code-symbol",
                    rel_path=rel_path,
                    content=summary,
                    metadata={"language": analysis.language, "types": [t.name for t in analysis.types]},
                )
            )

    def search_hybrid(self, query: str, category: str = "all", top_k: int = 5) -> List[Dict[str, Any]]:
        """Executes Reciprocal Rank Fusion (RRF) over SQLite FTS5 BM25 + TF-IDF Cosine Similarity."""
        self.refresh_if_changed()
        if not self.chunks:
            return []

        rrf_scores: Dict[int, float] = {}
        chunk_idx_by_id = {c.chunk_id: i for i, c in enumerate(self.chunks)}

        # 1. Lexical BM25 via SQLite FTS5 (explicit OR across tokens so multi-word queries work)
        tokens = [re.sub(r"[^\w]", "", tok) for tok in query.split()]
        tokens = [t for t in tokens if len(t) >= 2]
        if tokens:
            fts_query = " OR ".join(f'"{t}"*' for t in tokens[:12])
            try:
                cur = self.conn.cursor()
                cur.execute(
                    "SELECT chunk_id, bm25(fts_chunks) AS score "
                    "FROM fts_chunks WHERE fts_chunks MATCH ? ORDER BY score LIMIT 30;",
                    (fts_query,),
                )
                for rank, (cid, _) in enumerate(cur.fetchall(), start=1):
                    idx = chunk_idx_by_id.get(cid)
                    if idx is not None:
                        rrf_scores[idx] = rrf_scores.get(idx, 0.0) + 1.0 / (60 + rank)
            except sqlite3.Error:
                pass

        # 2. Conceptual Sparse Vector Search via TF-IDF Cosine Similarity
        if HAS_SKLEARN and self.vectorizer is not None and self.tfidf_matrix is not None:
            q_vec = self.vectorizer.transform([query])
            sims = cosine_similarity(q_vec, self.tfidf_matrix).flatten()
            for rank, idx in enumerate(sims.argsort()[::-1][:30], start=1):
                if sims[idx] > 0.01:
                    rrf_scores[int(idx)] = rrf_scores.get(int(idx), 0.0) + 1.0 / (60 + rank)

        # 3. Priority boost for active #ai-pin / #ai-ignore Living Memory decisions
        q_tokens = {t.lower() for t in tokens if len(t) >= 3}
        for idx, chunk in enumerate(self.chunks):
            if chunk.metadata.get("superseded"):
                rrf_scores.pop(idx, None)
                continue
            if chunk.category == "decision-memory" and idx in rrf_scores:
                content_lower = chunk.content.lower()
                overlap = sum(1 for t in q_tokens if t in content_lower)
                if overlap > 0:
                    rrf_scores[idx] += 0.05 * min(overlap, 4)

        results: List[Dict[str, Any]] = []
        for idx in sorted(rrf_scores.keys(), key=lambda i: rrf_scores[i], reverse=True):
            chunk = self.chunks[idx]
            if category != "all" and chunk.category != category:
                continue
            results.append(
                {
                    "id": chunk.chunk_id,
                    "title": chunk.title,
                    "category": chunk.category,
                    "path": chunk.rel_path,
                    "rrf_score": round(rrf_scores[idx], 5),
                    "content": chunk.content,
                }
            )
            if len(results) >= max(1, min(top_k, 15)):
                break

        return results

    def record_decision(
        self,
        tag_type: str,
        target: str,
        rule_summary: str,
        rationale: str,
    ) -> Dict[str, Any]:
        """Persists a human #ai-pin or #ai-ignore decision into docs/decisions/ and re-indexes RAM."""
        clean_tag = tag_type.strip().lstrip("#").lower()
        if clean_tag not in ("ai-pin", "ai-ignore"):
            raise ValueError("tag_type must be 'ai-pin' or 'ai-ignore'.")

        decisions_dir = self.repo_root / "docs" / "decisions"
        decisions_dir.mkdir(parents=True, exist_ok=True)

        slug = re.sub(r"[^a-z0-9]+", "-", target.lower()).strip("-") or "decision"
        file_path = decisions_dir / f"{clean_tag}-{slug}.md"

        markdown_content = (
            f"# {clean_tag.upper()}: {target}\n\n"
            f"- **Tag**: `#{clean_tag}`\n"
            f"- **Status**: Active\n"
            f"- **Recorded**: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n"
            f"- **Rule**: {rule_summary}\n\n"
            f"## Engineering Rationale\n"
            f"{rationale}\n"
        )
        file_path.write_text(markdown_content, encoding="utf-8")

        self.rebuild_index()
        return {
            "status": "indexed",
            "tag": f"#{clean_tag}",
            "file": file_path.relative_to(self.repo_root).as_posix(),
            "total_chunks": len(self.chunks),
        }


ENGINE = HybridRagEngine(REPO_ROOT)


@mcp.tool()
def search_hybrid_rag(query: str, category: str = "all", top_k: int = 5) -> str:
    """Searches project PRD, ADRs, Living Memory decisions (#ai-pin/#ai-ignore), and AST code symbols."""
    hits = ENGINE.search_hybrid(query=query, category=category, top_k=top_k)
    return json.dumps(
        {
            "query": query,
            "category": category,
            "total_indexed_chunks": len(ENGINE.chunks),
            "results": hits,
        },
        indent=2,
    )


@mcp.tool()
def get_canonical_exemplar(pattern_type: str) -> str:
    """Returns canonical file paths, mandatory rules, and live code previews for project patterns."""
    exemplars = {
        "domain-model": {
            "path": "src/Domain/Models/SampleEntity.cs",
            "rules": [
                "Strictly 1 top-level type per domain file.",
                "Zero references to persistence/ORM or HTTP framework layers.",
                "Use exact integer or decimal types for financial/measurement values (avoid float drift).",
            ],
        },
        "repository": {
            "path": "src/Infrastructure/Repositories/SampleRepository.cs",
            "rules": [
                "Inject IDbConnectionFactory; never instantiate raw DB connections directly.",
                "Parameterize all SQL queries and enforce tenant/owner scoping.",
            ],
        },
        "api-controller": {
            "path": "src/Api/Controllers/SampleController.cs",
            "rules": [
                "Every state-mutating POST/PUT/DELETE endpoint MUST enforce authentication and explicit scope checks.",
                "Delegate business rules to domain services; never embed raw SQL in controllers.",
            ],
        },
        "bdd-step": {
            "path": "tests/BDD/Steps/SampleFeatureSteps.cs",
            "rules": [
                "Always scope step classes strictly to their feature to prevent global step collisions.",
                "Inject a deterministic virtual clock / time provider so time-window tests run in milliseconds.",
            ],
        },
        "ui-widget": {
            "path": "src/Web/src/components/SampleWidget.tsx",
            "rules": [
                "Keep UI modules focused (<= 2 top-level type declarations per file).",
                "Prefer native platform fetch/EventSource over heavy deprecated HTTP clients.",
            ],
        },
    }

    key = pattern_type.strip().lower()
    if key not in exemplars:
        return json.dumps({"error": f"Unknown pattern_type '{pattern_type}'", "valid_types": list(exemplars)}, indent=2)

    info = exemplars[key]
    file_path = REPO_ROOT / info["path"]
    preview = ""
    if file_path.is_file():
        preview = "\n".join(file_path.read_text(encoding="utf-8", errors="replace").splitlines()[:60])

    return json.dumps(
        {
            "pattern_type": key,
            "canonical_path": info["path"],
            "mandatory_rules": info["rules"],
            "source_preview": preview,
        },
        indent=2,
    )


@mcp.tool()
def validate_code_against_guardrails(target_rel_path: str, code_content: str) -> str:
    """Validates candidate C# or TypeScript/TSX code via Tree-Sitter AST before writing to disk."""
    report = audit_source_guardrails(target_rel_path, code_content)
    return json.dumps(report, indent=2)


@mcp.tool()
def record_rag_decision(
    tag_type: str,
    target: str,
    rule_summary: str,
    rationale: str,
) -> str:
    """Persists a permanent #ai-pin or #ai-ignore engineering lesson to docs/decisions/ and re-indexes RAM."""
    result = ENGINE.record_decision(
        tag_type=tag_type,
        target=target,
        rule_summary=rule_summary,
        rationale=rationale,
    )
    return json.dumps(result, indent=2)


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        print(f"Indexed {len(ENGINE.chunks)} chunks from {REPO_ROOT}")
        sample_bad = "public record OrderItem(string Id);\npublic enum OrderStatus { Pending, Paid }"
        print(validate_code_against_guardrails("src/Domain/Models/OrderItem.cs", sample_bad))
        sys.exit(0)
    mcp.run()
