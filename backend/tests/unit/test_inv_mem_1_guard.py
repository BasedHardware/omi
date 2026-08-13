"""INV-MEM-1/2/3 — Product memory tier, vector hydration, and canonical fail-closed guards.

Behavioral characterization plus source ratchet (no NEW violations) over memory
invariant path globs. See docs/product/invariants/memory-*.md.
"""

from __future__ import annotations

import ast
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Set, Tuple

import pytest

from database.memory_collections import MemoryCollections
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.memory_search_gateway import SearchDecision, SearchMode, SearchVectorHit, hydrate_and_filter_vector_hits
from models.product_memory import (
    MemoryAccessPolicy,
    MemoryItemStatus,
    MemoryTier,
    ProcessingState,
    MemoryItem,
    is_default_access_eligible,
)
from utils.memory.memory_read_api import query_default_product_memory_items

BACKEND_DIR = Path(__file__).resolve().parents[2]

PRODUCT_TIERS = frozenset({"short_term", "long_term", "archive"})

# Frozen allowlist of existing MemoryCollections @property names. Any new property
# is a ratchet violation (INV-MEM-1: one canonical product-memory collection).
_ALLOWED_MEMORY_COLLECTIONS_PROPERTIES = frozenset(
    {
        "user_root",
        "memory_items",
        "memory_operations",
        # Immutable source-replacement receipts are journal metadata, not a
        # second product-memory collection or product tier.
        "memory_source_replacements",
        "memory_outbox",
        "memory_control_state",
        # Migration checkpoint under memory_control (not a product-memory tier store).
        "legacy_canonical_backfill_checkpoint",
        # Operational graph-enrichment sweep cursor under memory_control; it
        # stores no product-memory records or source content.
        "historical_graph_enrichment_cursor",
        "memory_apply_control_state",
        "memory_lineage",
        "memory_historical_overrides",
        "memory_evidence",
        "memory_graph_assertions",
        # Existing review surface, now centralized through MemoryCollections.
        "memory_review_queue",
        "memory_runs",
        "memory_import_runs",
        "memory_import_artifacts",
        "memory_import_candidates",
        "non_active_memory_routes",
        "short_term_lifecycle_transitions",
        "legacy_fallback",
        "memory_commits",
        "memory_state",
        "memory_state_head",
        "all_collection_paths",
    }
)

# Per-line markers that indicate archive is used only on explicit archive paths.
_ARCHIVE_EXPLICIT_MARKERS = (
    "archive_explicit",
    "archive_capability",
    "archive_requested",
    "archive_allowed",
    "is_archive_access_eligible",
    "query_archive_product_memory_items",
    "build_archive_memory_vector_filter",
    "SearchMode.archive_explicit",
    "archive_requires_explicit_query",
    "archive_explicit_allowed",
    "explicit_archive_memory",
    "not_archive",
)

# Known legacy/debt: existing occurrences exempt from the archive-default-read ratchet.
_ARCHIVE_DEFAULT_READ_LINE_ALLOWLIST: Tuple[Tuple[str, int], ...] = (("database/memory_vector_metadata.py", 119),)

# Scan roots for INV-MEM source ratchet.
_RATchet_SCAN_GLOBS = (
    "database/memory_*.py",
    "utils/memory/**/*.py",
    "models/product_memory.py",
    "models/memory_search_gateway.py",
)


def _evidence() -> MemoryEvidence:
    return MemoryEvidence(
        evidence_id="ev_guard",
        source_id="conv_guard",
        source_type="conversation",
        source_version="v1",
        artifact_preservation=ArtifactPreservationState.preserved,
    )


def _item(
    memory_id: str,
    *,
    tier: MemoryTier = MemoryTier.short_term,
    content: str = "memory content",
    expires_at: datetime | None = None,
) -> MemoryItem:
    now = datetime.now(timezone.utc)
    if expires_at is None and tier == MemoryTier.short_term:
        expires_at = now + timedelta(days=30)
    return MemoryItem(
        memory_id=memory_id,
        uid="u_guard",
        version=1,
        tier=tier,
        status=MemoryItemStatus.active,
        processing_state=ProcessingState.processed,
        content=content,
        evidence=[_evidence()],
        source_state=SourceState.active,
        sensitivity_labels=[],
        visibility="private",
        user_asserted=False,
        captured_at=now - timedelta(days=1),
        updated_at=now,
        expires_at=expires_at,
        ledger_commit_id="commit_lt" if tier == MemoryTier.long_term else None,
        ledger_sequence=1 if tier == MemoryTier.long_term else None,
        item_revision=1,
        source_commit_id=f"source-{memory_id}",
        content_hash=f"hash-{memory_id}",
        account_generation=0,
    )


def _vector_hit(item: MemoryItem, *, score: float = 0.9) -> SearchVectorHit:
    return SearchVectorHit(
        memory_id=item.memory_id,
        score=score,
        projection_commit_id=item.ledger_commit_id or "commit_proj",
        vector_updated_at=item.updated_at,
        uid=item.uid,
        account_generation=item.account_generation,
        item_revision=item.item_revision,
        source_commit_id=item.source_commit_id,
        content_hash=item.content_hash,
    )


_RATchet_PARSE_CACHE: dict[str, ast.Module] = {}
_RATchet_TEXT_CACHE: dict[str, str] = {}


def _file_text(path: Path) -> str:
    key = path.as_posix()
    if key not in _RATchet_TEXT_CACHE:
        _RATchet_TEXT_CACHE[key] = path.read_text(encoding="utf-8")
    return _RATchet_TEXT_CACHE[key]


def _parsed_tree(path: Path) -> ast.Module:
    key = path.as_posix()
    if key not in _RATchet_PARSE_CACHE:
        _RATchet_PARSE_CACHE[key] = ast.parse(_file_text(path))
    return _RATchet_PARSE_CACHE[key]


def _iter_ratchet_python_files() -> List[Path]:
    files: Set[Path] = set()
    for pattern in _RATchet_SCAN_GLOBS:
        for path in BACKEND_DIR.glob(pattern):
            if path.is_file() and path.suffix == ".py":
                files.add(path)
    return sorted(files)


def _relative_backend_path(path: Path) -> str:
    return path.relative_to(BACKEND_DIR).as_posix()


def _memory_collections_unlisted_properties(tree: ast.Module) -> List[str]:
    offenders: List[str] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != "MemoryCollections":
            continue
        for child in node.body:
            if not isinstance(child, ast.FunctionDef):
                continue
            is_property = any(
                isinstance(decorator, ast.Name) and decorator.id == "property" for decorator in child.decorator_list
            )
            if not is_property:
                continue
            if child.name not in _ALLOWED_MEMORY_COLLECTIONS_PROPERTIES:
                offenders.append(child.name)
    return offenders


def _tier_assignment_offenders(tree: ast.Module, *, rel_path: str) -> List[str]:
    offenders: List[str] = []

    def _check_tier_value(value_node: ast.AST, context: str) -> None:
        if isinstance(value_node, ast.Constant) and isinstance(value_node.value, str):
            if value_node.value not in PRODUCT_TIERS:
                offenders.append(f"{rel_path}: {context} uses tier literal {value_node.value!r}")
        elif isinstance(value_node, ast.Attribute) and isinstance(value_node.value, ast.Name):
            enum_name = value_node.value.id
            member = value_node.attr
            if enum_name in {"MemoryTier", "MemoryLayer"} and member not in PRODUCT_TIERS:
                offenders.append(f"{rel_path}: {context} uses {enum_name}.{member}")

    class _TierVisitor(ast.NodeVisitor):
        def visit_Assign(self, node: ast.Assign) -> None:
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {"tier", "memory_tier"}:
                    _check_tier_value(node.value, f"tier assignment at line {node.lineno}")
                elif isinstance(target, ast.Attribute) and target.attr in {"tier", "memory_tier"}:
                    _check_tier_value(node.value, f"tier assignment at line {node.lineno}")
            self.generic_visit(node)

        def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
            if isinstance(node.target, ast.Name) and node.target.id in {"tier", "memory_tier"} and node.value:
                _check_tier_value(node.value, f"annotated tier at line {node.lineno}")
            self.generic_visit(node)

        def visit_Compare(self, node: ast.Compare) -> None:
            for comparator in node.comparators:
                if isinstance(comparator, ast.Attribute) and isinstance(comparator.value, ast.Name):
                    if comparator.value.id in {"MemoryTier", "MemoryLayer"} and comparator.attr not in PRODUCT_TIERS:
                        offenders.append(
                            f"{rel_path}: tier comparison at line {node.lineno} uses "
                            f"{comparator.value.id}.{comparator.attr}"
                        )
            self.generic_visit(node)

        def visit_Call(self, node: ast.Call) -> None:
            for keyword in node.keywords:
                if keyword.arg in {"tier", "memory_tier"}:
                    _check_tier_value(keyword.value, f"keyword {keyword.arg} at line {node.lineno}")
            self.generic_visit(node)

    _TierVisitor().visit(tree)
    return offenders


def _archive_default_read_offenders(path: Path, text: str) -> List[str]:
    rel_path = _relative_backend_path(path)
    offenders: List[str] = []
    lines = text.splitlines()
    archive_line_re = re.compile(r"Memory(?:Tier|Layer)\.archive\b")

    for index, line in enumerate(lines, start=1):
        if (rel_path, index) in _ARCHIVE_DEFAULT_READ_LINE_ALLOWLIST:
            continue
        if not archive_line_re.search(line):
            continue

        window_start = max(0, index - 8)
        window_end = min(len(lines), index + 8)
        window = "\n".join(lines[window_start:window_end])
        if any(marker in window for marker in _ARCHIVE_EXPLICIT_MARKERS):
            continue
        offenders.append(f"{rel_path}:{index}: archive tier without explicit archive context")
    return offenders


class TestInvMem1DefaultAccessAndCanonicalCollection:
    """INV-MEM-1: three tiers, default access is short_term + long_term only."""

    def test_default_access_policy_allows_short_and_long_term_only(self):
        now = datetime.now(timezone.utc)
        policy = MemoryAccessPolicy.for_omi_chat()
        short = _item("mem_st", tier=MemoryTier.short_term, content="short term fact")
        long_term = _item(
            "mem_lt",
            tier=MemoryTier.long_term,
            content="long term fact",
            expires_at=None,
        )
        archive = _item(
            "mem_ar",
            tier=MemoryTier.archive,
            content="archived fact",
            expires_at=None,
        )

        assert is_default_access_eligible(short, policy, now=now).allowed is True
        assert is_default_access_eligible(long_term, policy, now=now).allowed is True
        assert is_default_access_eligible(archive, policy, now=now).allowed is False
        assert is_default_access_eligible(archive, policy, now=now).reason == "archive_requires_explicit_query"

    def test_query_default_product_memory_items_excludes_archive(self):
        now = datetime.now(timezone.utc)
        policy = MemoryAccessPolicy.for_omi_chat()
        items = [
            _item("mem_st", tier=MemoryTier.short_term, content="coffee short"),
            _item("mem_lt", tier=MemoryTier.long_term, content="coffee long", expires_at=None),
            _item("mem_ar", tier=MemoryTier.archive, content="coffee archive", expires_at=None),
        ]

        results = query_default_product_memory_items("coffee", items, policy=policy, now=now)
        result_ids = {entry["memory_id"] for entry in results}

        assert result_ids == {"mem_st", "mem_lt"}
        assert "mem_ar" not in result_ids

    def test_archive_transition_is_removed_from_default_access(self):
        now = datetime.now(timezone.utc)
        policy = MemoryAccessPolicy.for_omi_chat()
        long_term = _item("mem_transition", tier=MemoryTier.long_term, expires_at=None)
        archived = long_term.model_copy(update={"tier": MemoryTier.archive, "item_revision": 2})

        decision = is_default_access_eligible(archived, policy, now=now)

        assert decision.allowed is False
        assert decision.reason == "archive_requires_explicit_query"

    def test_memory_collections_canonical_product_memory_path_is_memory_items(self):
        paths = MemoryCollections(uid="u_guard")

        assert paths.memory_items == "users/u_guard/memory_items"
        assert paths.memory_items in paths.all_collection_paths()
        assert "memory_short_term" not in paths.all_collection_paths()
        assert "memory_archive" not in paths.all_collection_paths()


class TestInvMem2VectorHydrationFailClosed:
    """INV-MEM-2: vector hits are candidate IDs only; hydration is authoritative."""

    def test_missing_authoritative_items_are_excluded_with_repair_candidates(self):
        present = _item("mem_present", tier=MemoryTier.long_term, content="present", expires_at=None)
        hits = [
            _vector_hit(present, score=0.95),
            SearchVectorHit(
                memory_id="mem_missing",
                score=0.9,
                projection_commit_id="commit_proj",
                vector_updated_at=present.updated_at,
            ),
        ]

        result = hydrate_and_filter_vector_hits(
            hits=hits,
            authoritative_items={"mem_present": present},
            policy=MemoryAccessPolicy.for_omi_chat(),
            mode=SearchMode.default,
            required_projection_commit_id="commit_proj",
            required_account_generation=0,
        )

        assert [entry.item.memory_id for entry in result.results] == ["mem_present"]
        assert result.decisions["mem_missing"] == SearchDecision.missing_authoritative_item
        assert result.repair_purge_candidates
        assert any(candidate["memory_id"] == "mem_missing" for candidate in result.repair_purge_candidates)

    def test_stale_projection_fails_closed_with_empty_results(self):
        item = _item("mem_stale", tier=MemoryTier.long_term, content="stale", expires_at=None)
        hits = [_vector_hit(item, score=0.9)]
        hits[0] = hits[0].model_copy(update={"projection_commit_id": "stale_commit"})

        result = hydrate_and_filter_vector_hits(
            hits=hits,
            authoritative_items={"mem_stale": item},
            policy=MemoryAccessPolicy.for_omi_chat(),
            mode=SearchMode.default,
            required_projection_commit_id="commit_proj",
            required_account_generation=0,
        )

        assert result.results == []
        assert result.decisions["mem_stale"] == SearchDecision.stale_projection
        assert result.repair_purge_candidates

    def test_archive_hits_denied_in_default_mode_without_repair_candidates(self):
        archive = _item("mem_arch", tier=MemoryTier.archive, content="archived", expires_at=None)
        hits = [_vector_hit(archive, score=0.9)]

        result = hydrate_and_filter_vector_hits(
            hits=hits,
            authoritative_items={"mem_arch": archive},
            policy=MemoryAccessPolicy.for_omi_chat(),
            mode=SearchMode.default,
            required_projection_commit_id="commit_proj",
            required_account_generation=0,
        )

        assert result.results == []
        assert result.decisions["mem_arch"] == SearchDecision.access_denied
        assert result.repair_purge_candidates == []


class TestInvMemSourceRatchet:
    """Source ratchet: forbid NEW violations in memory invariant path globs."""

    def test_scan_paths_are_non_empty(self):
        files = _iter_ratchet_python_files()
        assert files, "INV-MEM ratchet scan found no Python files"

    def test_memory_collections_has_no_new_collection_path_properties(self):
        offenders: List[str] = []
        collections_path = BACKEND_DIR / "database" / "memory_collections.py"
        tree = ast.parse(collections_path.read_text(encoding="utf-8"))
        for name in _memory_collections_unlisted_properties(tree):
            offenders.append(f"database/memory_collections.py: unlisted MemoryCollections property {name!r}")
        assert offenders == [], "INV-MEM-1 unlisted MemoryCollections properties:\n" + "\n".join(offenders)

    def test_no_non_canonical_product_tier_literals_in_memory_paths(self):
        offenders: List[str] = []
        for path in _iter_ratchet_python_files():
            rel_path = _relative_backend_path(path)
            tree = _parsed_tree(path)
            offenders.extend(_tier_assignment_offenders(tree, rel_path=rel_path))
        assert offenders == [], "INV-MEM-1 forbidden product tier literals:\n" + "\n".join(offenders)

    def test_default_read_paths_do_not_include_archive_without_explicit_mode(self):
        offenders: List[str] = []
        for path in _iter_ratchet_python_files():
            text = _file_text(path)
            offenders.extend(_archive_default_read_offenders(path, text))
        assert offenders == [], "INV-MEM-1 forbidden archive in default-read paths:\n" + "\n".join(offenders)
