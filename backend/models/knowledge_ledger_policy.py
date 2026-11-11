"""Stable slot and rendering policy for ``knowledge_ledger.v1`` facts.

This module is intentionally pure so models, prompt projections, and tests can
share one contract without importing database or runtime code.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any, Iterable, Optional

PROFILE_CHARACTER_BUDGET = 2_400
PLAYBOOK_INDEX_CHARACTER_BUDGET = 800
PLAYBOOK_HANDLE_CHARACTER_LIMIT = 360
PROFILE_LINE_CHARACTER_LIMIT = 360


@dataclass(frozen=True)
class LedgerSlotDefinition:
    name: str
    renderer_order: int
    aliases: tuple[str, ...] = ()


# Canonical names remain snake_case because that is the released wire shape.
# New names are append-only: renaming a canonical entry would split history.
LEDGER_SLOT_DEFINITIONS: tuple[LedgerSlotDefinition, ...] = (
    LedgerSlotDefinition("preferred_name", 10, ("name", "display_name", "called_name")),
    LedgerSlotDefinition("pronouns", 20, ("preferred_pronouns",)),
    LedgerSlotDefinition("primary_language", 30, ("language", "preferred_language")),
    LedgerSlotDefinition("age_years", 35, ("age",)),
    LedgerSlotDefinition("timezone", 40, ("time_zone", "user_timezone")),
    LedgerSlotDefinition("home_city", 50, ("city", "home_location", "residence_city")),
    LedgerSlotDefinition("work_city", 60, ("office_city", "work_location")),
    LedgerSlotDefinition("occupation", 70, ("job", "job_title", "role")),
    LedgerSlotDefinition("employer", 80, ("company", "workplace")),
    LedgerSlotDefinition("communication_style", 90, ("preferred_communication_style",)),
    LedgerSlotDefinition("dietary_preferences", 100, ("diet", "dietary_restrictions")),
    LedgerSlotDefinition("current_focus", 110, ("current_priority", "primary_focus")),
)

# Released legacy predicates that may become current profile slots during
# migration. Keep this beside the registry so producer growth gets the same
# append-only policy review.
LEDGER_SLOT_BY_LEGACY_PREDICATE = {
    "resides_in": "home_city",
    "works_at": "employer",
    "age_years": "age_years",
}


_SLOT_TOKEN_PATTERN = re.compile(r"[^a-z0-9]+")
_SLOT_BY_NAME = {definition.name: definition for definition in LEDGER_SLOT_DEFINITIONS}
_SLOT_ALIASES = {
    alias: definition.name for definition in LEDGER_SLOT_DEFINITIONS for alias in (definition.name, *definition.aliases)
}


# Higher rank always wins before recency or curation. This is the durable
# product authority order; curation cannot make an inference outrank a user.
LEDGER_AUTHORITY_RANK = {
    "direct_user_statement": 600,
    "explicit_remember": 600,
    "onboarding": 500,
    "agent_reusable_conclusion": 400,
    "daily_reconciliation": 300,
    "legacy_migration": 200,
    "recurring_workflow": 100,
    "standing_trigger": 100,
}


def normalize_slot_token(value: str) -> str:
    """Normalize spelling only; this does not admit an unknown slot."""

    return _SLOT_TOKEN_PATTERN.sub("_", (value or "").strip().lower()).strip("_")


def normalize_playbook_handle(value: Any) -> str:
    """Collapse a playbook description to one compact, single-line handle."""

    return " ".join(str(value or "").split())


def canonicalize_ledger_slot(value: Optional[str], *, strict: bool = True) -> Optional[str]:
    """Return one released canonical slot name.

    Unknown slots fail new writes in strict mode. Read projections use
    ``strict=False`` so historic/future names remain stored but do not enter a
    prompt under an invented ordering contract.
    """

    if value is None:
        return None
    normalized = normalize_slot_token(value)
    if not normalized:
        return None
    canonical = _SLOT_ALIASES.get(normalized)
    if canonical is None and strict:
        raise ValueError(f"unsupported knowledge ledger slot: {normalized}")
    return canonical


def ledger_authority_rank(reason: Any) -> int:
    value = getattr(reason, "value", reason)
    return LEDGER_AUTHORITY_RANK.get(str(value or ""), 0)


def _row_timestamp(row: Any) -> float:
    value = (
        getattr(row, "valid_from", None)
        or getattr(row, "valid_at", None)
        or getattr(row, "captured_at", None)
        or getattr(row, "created_at", None)
    )
    if not isinstance(value, datetime):
        return 0.0
    try:
        return value.timestamp()
    except (OSError, OverflowError, ValueError):
        return 0.0


def _row_identity(row: Any) -> str:
    return str(getattr(row, "memory_id", None) or getattr(row, "id", ""))


def _winner_key(row: Any) -> tuple[int, float, int, str]:
    return (
        ledger_authority_rank(getattr(row, "write_reason", None)),
        _row_timestamp(row),
        int(getattr(row, "curation_weight", 0) or 0),
        _row_identity(row),
    )


def select_profile_slot_winners(rows: Iterable[Any]) -> list[tuple[str, Any]]:
    """Choose exactly one current fact per canonical slot.

    Authority wins first, then newest fact at the same authority, then explicit
    curation weight and stable row identity. Renderer order is independent of
    curation, keeping prompt diffs deterministic.
    """

    winners: dict[str, Any] = {}
    for row in rows:
        slot = canonicalize_ledger_slot(getattr(row, "slot", None), strict=False)
        if slot is None:
            continue
        current = winners.get(slot)
        if current is None or _winner_key(row) > _winner_key(current):
            winners[slot] = row
    return sorted(
        winners.items(),
        key=lambda pair: (_SLOT_BY_NAME[pair[0]].renderer_order, pair[0], _row_identity(pair[1])),
    )


def render_bounded_profile(rows: Iterable[Any], *, character_budget: int = PROFILE_CHARACTER_BUDGET) -> str:
    if character_budget < 0:
        raise ValueError("character_budget must be nonnegative")
    lines: list[str] = []
    used = 0
    for slot, row in select_profile_slot_winners(rows):
        content = " ".join(str(getattr(row, "content", "") or "").split())[:PROFILE_LINE_CHARACTER_LIMIT]
        if not content:
            continue
        line = f"{slot}: {content}"
        separator = 1 if lines else 0
        if used + separator + len(line) > character_budget:
            continue
        lines.append(line)
        used += separator + len(line)
    return "\n".join(lines)


__all__ = [
    "LEDGER_AUTHORITY_RANK",
    "LEDGER_SLOT_BY_LEGACY_PREDICATE",
    "LEDGER_SLOT_DEFINITIONS",
    "PLAYBOOK_HANDLE_CHARACTER_LIMIT",
    "PLAYBOOK_INDEX_CHARACTER_BUDGET",
    "PROFILE_CHARACTER_BUDGET",
    "PROFILE_LINE_CHARACTER_LIMIT",
    "LedgerSlotDefinition",
    "canonicalize_ledger_slot",
    "ledger_authority_rank",
    "normalize_playbook_handle",
    "normalize_slot_token",
    "render_bounded_profile",
    "select_profile_slot_winners",
]
