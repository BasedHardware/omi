#!/usr/bin/env python3
# LIFECYCLE: one-time
# DELETE-AFTER: INV-MEM-6

"""Inventory legacy memory surfaces and enforce the Gate F shrink-only ratchet.

This is deliberately a source/resource inventory, not a runtime probe.  It
reads only checked-in files, emits paths/lines/classifications (never source
text), and has no database, network, model, or user-data dependency.  The
baseline records the current debt while the JIT-processing migration is in
flight: a class may shrink, but a new reference in a tracked class fails the
ratchet.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = ROOT / "backend" / "scripts" / "legacy_memory_surface_baseline.json"
BASELINE_REPOSITORY_PATH = "backend/scripts/legacy_memory_surface_baseline.json"


@dataclass(frozen=True)
class InventoryRule:
    """One bounded source/resource marker family.

    ``paths`` are repository-relative exact paths or glob patterns.  Keeping
    these explicit is important: unrelated documentation and fixtures cannot
    change the ratchet, while a new file under a tracked legacy surface is
    still observed when the rule uses a directory glob.
    """

    classification: str
    paths: tuple[str, ...]
    pattern: str
    symbol: str


@dataclass(frozen=True)
class Finding:
    classification: str
    symbol: str
    path: str
    line: int

    def as_dict(self) -> dict[str, object]:
        return {
            "classification": self.classification,
            "line": self.line,
            "path": self.path,
            "symbol": self.symbol,
        }


# These are the known Gate F surfaces from the implementation checklist.  The
# patterns intentionally identify stable symbols/resource names rather than
# copying source lines into a report.
RULES: tuple[InventoryRule, ...] = (
    InventoryRule(
        "conversation_eager_memory_writer",
        (
            "backend/utils/conversations/process_conversation.py",
            "backend/routers/conversations.py",
            "backend/routers/listen/conversations.py",
            "backend/utils/sync/pipeline.py",
            "backend/routers/developer.py",
            "backend/utils/conversations/merge_conversations.py",
        ),
        r"_extract_memories|extract_memories_from_text|defer_memory_extraction",
        "eager_extraction_symbol",
    ),
    InventoryRule(
        "short_term_lifecycle",
        (
            "backend/utils/memory/*.py",
            "backend/jobs/short_term_lifecycle_worker.py",
            "backend/modal/memory_maintenance_job.py",
            "backend/routers/memory_admin.py",
            "backend/database/product_memory_items.py",
        ),
        r"short_term_lifecycle|MemoryTier\.short_term|MemoryLayer\.short_term",
        "short_term_symbol",
    ),
    InventoryRule(
        "consolidation_promotion",
        (
            "backend/utils/memory/*.py",
            "backend/modal/memory_maintenance_job.py",
            "backend/scripts/memory-continuity-gauntlet.py",
        ),
        r"canonical_consolidation|short_term_promotion|consolidat(?:e|ion|ed|ing)|promotion",
        "consolidation_symbol",
    ),
    InventoryRule(
        "profile_synthesis",
        (
            "backend/routers/users.py",
            "backend/database/users.py",
            "backend/utils/llm/ai_user_profile.py",
            "backend/routers/mcp.py",
            "backend/routers/mcp_sse.py",
            "desktop/macos/Desktop/Sources/ProactiveAssistants/Services/AIUserProfileService.swift",
            "desktop/macos/Desktop/Sources/Providers/ChatProvider.swift",
            "desktop/macos/Desktop/Sources/Rewind/Core/RewindDatabase.swift",
            "desktop/macos/Desktop/Sources/ProactiveAssistants/Assistants/TaskExtraction/TaskAssistant.swift",
            "desktop/macos/Desktop/Sources/ProactiveAssistants/Assistants/Insight/InsightAssistant.swift",
            "desktop/windows/src/main/assistants/aiUserProfile/**/*.ts",
            "desktop/windows/src/main/agentKernel/desktopChatPrompt.ts",
            "desktop/windows/src/main/ipc/mainChatPersonalization.ts",
            "desktop/windows/src/main/ipc/db.ts",
        ),
        r"ai_user_profile|AIUserProfile|synthesize_ai_user_profile|formatAIProfileSection",
        "profile_symbol",
    ),
    InventoryRule(
        "old_proactive_assistants",
        (
            "desktop/macos/Desktop/Sources/ProactiveAssistants/Assistants/**/*.swift",
            "desktop/macos/Desktop/Sources/ProactiveAssistants/ProactiveAssistantsPlugin.swift",
            "desktop/windows/src/main/assistants/**/*.ts",
        ),
        r"MemoryAssistant|InsightAssistant|SuggestionAssistant|register(?:Memory|Insight|Suggestion)Assistant|GeminiClient|runAdviceExtraction|saveInsightToSQLite|createMemory\(",
        "proactive_assistant_symbol",
    ),
    InventoryRule(
        "maintenance_resources",
        (
            ".github/workflows/gcp_memory_maintenance_job*.yml",
            "backend/deploy/runtime_env/*.yaml",
            "backend/scripts/validate_memory_maintenance_scheduler.py",
            "backend/runtime_images.json",
        ),
        r"memory-maintenance-job|memory-maintenance-hourly|MEMORY_CANONICAL_(?:MAINTENANCE|CONSOLIDATION)|short_term_lifecycle",
        "maintenance_resource_symbol",
    ),
)


def _iter_files(root: Path, paths: Sequence[str]) -> Iterable[Path]:
    """Yield existing files once, deterministically, for a rule."""

    seen: set[Path] = set()
    for relative in sorted(paths):
        candidate = root / relative
        matches = [candidate] if candidate.is_file() else sorted(root.glob(relative))
        for path in matches:
            if path.is_file() and not path.name.endswith((".test.ts", ".spec.ts")) and path not in seen:
                seen.add(path)
                yield path


def scan(root: Path = ROOT, rules: Sequence[InventoryRule] = RULES) -> list[Finding]:
    """Return stable, content-free findings for ``root``."""

    findings: list[Finding] = []
    for rule in rules:
        expression = re.compile(rule.pattern)
        for path in _iter_files(root, rule.paths):
            relative = path.relative_to(root).as_posix()
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeError) as exc:
                raise RuntimeError(f"cannot read inventory input {relative}: {exc}") from exc
            for line_number, line in enumerate(lines, start=1):
                for _match in expression.finditer(line):
                    findings.append(
                        Finding(
                            classification=rule.classification,
                            symbol=rule.symbol,
                            path=relative,
                            line=line_number,
                        )
                    )
    return sorted(findings, key=lambda item: (item.classification, item.path, item.line, item.symbol))


def counts(findings: Iterable[Finding]) -> dict[str, int]:
    """Count each classification/symbol/path family without source text.

    The path component prevents a deletion in one producer from masking a new
    reference in another producer while still allowing line movement and
    ordinary formatting edits.
    """

    result: dict[str, int] = {}
    for finding in findings:
        key = f"{finding.classification}|{finding.symbol}|{finding.path}"
        result[key] = result.get(key, 0) + 1
    return dict(sorted(result.items()))


def compare_counts(current: Mapping[str, int], baseline: Mapping[str, int]) -> tuple[list[str], list[str]]:
    """Return (growth, shrinkage); only growth is a ratchet failure."""

    growth: list[str] = []
    shrinkage: list[str] = []
    for key in sorted(set(current) | set(baseline)):
        before = int(baseline.get(key, 0))
        after = int(current.get(key, 0))
        if after > before:
            growth.append(f"{key}: {before} -> {after}")
        elif after < before:
            shrinkage.append(f"{key}: {before} -> {after}")
    return growth, shrinkage


def parse_baseline(payload: object) -> dict[str, int]:
    """Validate and normalize one versioned inventory baseline payload."""

    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise RuntimeError("legacy-memory baseline must contain version 1")
    values = payload.get("counts")
    if not isinstance(values, dict) or any(not isinstance(key, str) for key in values):
        raise RuntimeError("legacy-memory baseline counts must be an object")
    try:
        return {key: int(value) for key, value in sorted(values.items())}
    except (TypeError, ValueError) as exc:
        raise RuntimeError("legacy-memory baseline counts must be integers") from exc


def load_baseline(path: Path = BASELINE_PATH) -> dict[str, int]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid legacy-memory baseline {path}: {exc}") from exc
    return parse_baseline(payload)


def load_baseline_from_ref(
    base_ref: str,
    *,
    root: Path = ROOT,
    repository_path: str = BASELINE_REPOSITORY_PATH,
) -> dict[str, int] | None:
    """Load the baseline committed at ``base_ref``.

    A valid base without this file is allowed only for the ratchet's first
    introduction.  Once merged, every later change is compared to both the
    working baseline and the immutable base-side baseline, so a PR cannot hide
    new debt by increasing its baseline in the same diff.
    """

    resolved = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{base_ref}^{{commit}}"],
        cwd=root,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    if resolved.returncode:
        detail = resolved.stderr.strip() or "ref does not resolve to a commit"
        raise RuntimeError(f"cannot resolve legacy-memory baseline ref {base_ref}: {detail}")

    result = subprocess.run(
        ["git", "show", f"{base_ref}:{repository_path}"],
        cwd=root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode:
        return None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid legacy-memory baseline at {base_ref}: {exc}") from exc
    return parse_baseline(payload)


def evaluate_ratchet(
    current: Mapping[str, int],
    baseline: Mapping[str, int],
    *,
    base_baseline: Mapping[str, int] | None = None,
) -> tuple[list[str], list[str]]:
    """Compare source and baseline, including base-side anti-inflation checks."""

    growth, shrinkage = compare_counts(current, baseline)
    if base_baseline is not None:
        baseline_growth, baseline_shrinkage = compare_counts(baseline, base_baseline)
        growth.extend(f"baseline {item}" for item in baseline_growth)
        shrinkage.extend(f"baseline {item}" for item in baseline_shrinkage)
    return sorted(growth), sorted(shrinkage)


def report(
    root: Path = ROOT,
    baseline_path: Path = BASELINE_PATH,
    *,
    base_ref: str | None = None,
) -> dict[str, object]:
    findings = scan(root)
    current = counts(findings)
    baseline = load_baseline(baseline_path)
    base_baseline = load_baseline_from_ref(base_ref, root=root) if base_ref else None
    growth, shrinkage = evaluate_ratchet(current, baseline, base_baseline=base_baseline)
    return {
        "baseline": str(baseline_path.relative_to(root).as_posix()),
        "base_ref": base_ref,
        "base_ref_has_baseline": base_baseline is not None,
        "counts": current,
        "findings": [finding.as_dict() for finding in findings],
        "growth": growth,
        "shrinkage": shrinkage,
        "status": "fail" if growth else "pass",
        "version": 1,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-ratchet", action="store_true", help="fail when any tracked class grows")
    parser.add_argument(
        "--base-ref",
        help="Git ref whose committed baseline is the immutable anti-inflation boundary",
    )
    parser.add_argument("--json", action="store_true", dest="as_json", help="emit deterministic JSON")
    args = parser.parse_args(argv)
    try:
        payload = report(base_ref=args.base_ref)
    except RuntimeError as exc:
        print(f"legacy memory surface inventory: ERROR: {exc}", file=sys.stderr)
        return 2

    if args.as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif args.check_ratchet and not payload["growth"]:
        print(
            "legacy memory surface inventory: PASS "
            f"({len(payload['findings'])} findings across {len(payload['counts'])} path counters)"
        )
    else:
        print(f"legacy memory surface inventory: {payload['status'].upper()}")
        for key, value in payload["counts"].items():
            print(f"{key}: {value}")
        if payload["shrinkage"]:
            print(f"shrinkage: {len(payload['shrinkage'])} class(es)")
        if payload["growth"]:
            print("growth:")
            for item in payload["growth"]:
                print(f"  {item}")
    return 1 if args.check_ratchet and payload["growth"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
