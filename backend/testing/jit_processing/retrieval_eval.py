"""Deterministic, synthetic retrieval-evaluation contract for JIT rollout work.

This module is a hermetic harness, not a production retriever. It models the
intended two-stage shape: triage bounded summary cards, then hydrate only the
referenced bounded transcript windows. No model, network, Firestore, or user
data is involved. The evidence expected by an evaluation is supplied by a
separate fixture so this evaluator cannot silently grade itself.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

RETRIEVAL_EVAL_SCHEMA_VERSION = 1
DEFAULT_GOLDEN_SET = Path(__file__).with_name("fixtures") / "retrieval_golden_set.json"
DEFAULT_EXPECTED_REFS = Path(__file__).with_name("fixtures") / "retrieval_expected_refs.json"

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[-/:][a-z0-9]+)*", re.IGNORECASE)
_STOPWORDS = frozenset(
    {
        "a",
        "about",
        "am",
        "an",
        "and",
        "did",
        "do",
        "for",
        "how",
        "i",
        "in",
        "is",
        "my",
        "of",
        "on",
        "the",
        "what",
        "which",
        "with",
        "when",
        "where",
        "who",
    }
)


def _require_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _require_string_list(value: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{field_name} must be a list of non-empty strings")
    return tuple(item.strip() for item in value)


def _stem(token: str) -> str:
    """Apply a deliberately tiny, explainable stem for paraphrase matching."""

    if len(token) > 5 and token.endswith("ing"):
        return token[:-3]
    if len(token) > 4 and token.endswith("ed"):
        return token[:-2]
    if len(token) > 4 and token.endswith("s"):
        return token[:-1]
    return token


def _terms(value: str) -> frozenset[str]:
    return frozenset(
        _stem(token.casefold()) for token in _TOKEN_RE.findall(value) if token.casefold() not in _STOPWORDS
    )


@dataclass(frozen=True)
class RetrievalBounds:
    """Harness bounds; these are not product or rollout thresholds."""

    max_summary_cards: int = 2
    max_summary_card_chars: int = 320
    max_window_chars: int = 720
    max_window_turns: int = 6

    def __post_init__(self) -> None:
        for name in (
            "max_summary_cards",
            "max_summary_card_chars",
            "max_window_chars",
            "max_window_turns",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "RetrievalBounds":
        if value is None:
            return cls()
        if not isinstance(value, Mapping):
            raise ValueError("bounds must be an object")
        allowed = {
            "max_summary_cards",
            "max_summary_card_chars",
            "max_window_chars",
            "max_window_turns",
        }
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"unknown retrieval bound(s): {sorted(unknown)}")
        return cls(**{key: value[key] for key in allowed if key in value})


@dataclass(frozen=True)
class CandidateThresholdConfig:
    """Optional candidate values for later discussion; no pass/fail is emitted."""

    source_hit_min: float | None = None
    false_positive_rate_max: float | None = None
    evidence_grounding_min: float | None = None
    max_tool_call_count: int | None = None
    max_token_proxy: int | None = None
    max_latency_ms: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "CandidateThresholdConfig":
        if value is None:
            return cls()
        allowed = {
            "source_hit_min",
            "false_positive_rate_max",
            "evidence_grounding_min",
            "max_tool_call_count",
            "max_token_proxy",
            "max_latency_ms",
        }
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"unknown candidate threshold(s): {sorted(unknown)}")
        return cls(**{key: value[key] for key in allowed if key in value})


@dataclass(frozen=True)
class TranscriptTurn:
    turn_id: str
    speaker: str
    text: str
    timestamp: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any], field_name: str) -> "TranscriptTurn":
        return cls(
            turn_id=_require_string(value.get("turn_id"), f"{field_name}.turn_id"),
            speaker=_require_string(value.get("speaker"), f"{field_name}.speaker"),
            text=_require_string(value.get("text"), f"{field_name}.text"),
            timestamp=(
                _require_string(value["timestamp"], f"{field_name}.timestamp")
                if value.get("timestamp") is not None
                else None
            ),
        )


@dataclass(frozen=True)
class TranscriptWindow:
    window_id: str
    conversation_id: str
    evidence_ref: str
    turns: tuple[TranscriptTurn, ...]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any], field_name: str) -> "TranscriptWindow":
        raw_turns = value.get("turns")
        if not isinstance(raw_turns, list) or not raw_turns or not all(isinstance(turn, Mapping) for turn in raw_turns):
            raise ValueError(f"{field_name}.turns must be a non-empty list")
        return cls(
            window_id=_require_string(value.get("window_id"), f"{field_name}.window_id"),
            conversation_id=_require_string(value.get("conversation_id"), f"{field_name}.conversation_id"),
            evidence_ref=_require_string(value.get("evidence_ref"), f"{field_name}.evidence_ref"),
            turns=tuple(
                TranscriptTurn.from_mapping(turn, f"{field_name}.turns[{index}]")
                for index, turn in enumerate(raw_turns)
            ),
        )


@dataclass(frozen=True)
class SummaryCard:
    card_id: str
    conversation_id: str
    title: str
    summary: str
    entities: tuple[str, ...]
    window_refs: tuple[str, ...]
    happened_at: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any], field_name: str) -> "SummaryCard":
        raw_entities = value.get("entities", [])
        raw_windows = value.get("window_refs")
        if not isinstance(raw_entities, list) or not isinstance(raw_windows, list):
            raise ValueError(f"{field_name}.entities and window_refs must be lists")
        return cls(
            card_id=_require_string(value.get("card_id"), f"{field_name}.card_id"),
            conversation_id=_require_string(value.get("conversation_id"), f"{field_name}.conversation_id"),
            title=_require_string(value.get("title"), f"{field_name}.title"),
            summary=_require_string(value.get("summary"), f"{field_name}.summary"),
            entities=_require_string_list(raw_entities, f"{field_name}.entities"),
            window_refs=_require_string_list(raw_windows, f"{field_name}.window_refs"),
            happened_at=(
                _require_string(value["happened_at"], f"{field_name}.happened_at")
                if value.get("happened_at") is not None
                else None
            ),
        )

    def searchable_text(self) -> str:
        return " ".join(part for part in (self.title, self.summary, *self.entities, self.happened_at or "") if part)


@dataclass(frozen=True)
class CandidateAnswer:
    text: str
    cited_refs: tuple[str, ...]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any], field_name: str) -> "CandidateAnswer":
        refs = value.get("cited_refs", [])
        if not isinstance(refs, list):
            raise ValueError(f"{field_name}.cited_refs must be a list")
        return cls(
            text=_require_string(value.get("text"), f"{field_name}.text"),
            cited_refs=_require_string_list(refs, f"{field_name}.cited_refs"),
        )


@dataclass(frozen=True)
class RetrievalCase:
    case_id: str
    category: str
    query: str
    summary_cards: tuple[SummaryCard, ...]
    windows: tuple[TranscriptWindow, ...]
    candidate_answer: CandidateAnswer
    bounds: RetrievalBounds

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any], index: int) -> "RetrievalCase":
        field_name = f"cases[{index}]"
        raw_cards = value.get("summary_cards")
        raw_windows = value.get("windows")
        if not isinstance(raw_cards, list) or not isinstance(raw_windows, list):
            raise ValueError(f"{field_name}.summary_cards and windows must be lists")
        cards = tuple(
            SummaryCard.from_mapping(card, f"{field_name}.summary_cards[{card_index}]")
            for card_index, card in enumerate(raw_cards)
            if isinstance(card, Mapping)
        )
        windows = tuple(
            TranscriptWindow.from_mapping(window, f"{field_name}.windows[{window_index}]")
            for window_index, window in enumerate(raw_windows)
            if isinstance(window, Mapping)
        )
        if len(cards) != len(raw_cards) or len(windows) != len(raw_windows):
            raise ValueError(f"{field_name} contains a non-object card or window")
        card_ids = [card.card_id for card in cards]
        window_ids = [window.window_id for window in windows]
        if len(set(card_ids)) != len(card_ids) or len(set(window_ids)) != len(window_ids):
            raise ValueError(f"{field_name} contains duplicate card or window IDs")
        window_map = {window.window_id: window for window in windows}
        for card in cards:
            for window_ref in card.window_refs:
                window = window_map.get(window_ref)
                if window is None:
                    raise ValueError(f"{field_name} card {card.card_id} references unknown window {window_ref}")
                if window.conversation_id != card.conversation_id:
                    raise ValueError(f"{field_name} card {card.card_id} crosses conversation boundary")
        return cls(
            case_id=_require_string(value.get("case_id"), f"{field_name}.case_id"),
            category=_require_string(value.get("category"), f"{field_name}.category"),
            query=_require_string(value.get("query"), f"{field_name}.query"),
            summary_cards=cards,
            windows=windows,
            candidate_answer=CandidateAnswer.from_mapping(
                value.get("candidate_answer") or {}, f"{field_name}.candidate_answer"
            ),
            bounds=RetrievalBounds.from_mapping(value.get("bounds")),
        )


@dataclass(frozen=True)
class SummaryCardMatch:
    card_id: str
    score: int
    matched_terms: tuple[str, ...]


@dataclass(frozen=True)
class HydratedWindow:
    window_id: str
    conversation_id: str
    evidence_ref: str
    text: str
    character_count: int
    truncated: bool


@dataclass(frozen=True)
class RetrievalMetrics:
    source_hit: float
    false_positive: float
    false_positive_rate: float
    evidence_grounding: float
    tool_call_count: int
    character_proxy: int
    token_proxy: int
    supplied_latency_ms: float
    matched_expected_ref_count: int
    expected_ref_count: int
    hydrated_ref_count: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RetrievalEvaluation:
    case_id: str
    category: str
    selected_cards: tuple[SummaryCardMatch, ...]
    hydrated_windows: tuple[HydratedWindow, ...]
    hydrated_evidence_refs: tuple[str, ...]
    metrics: RetrievalMetrics
    candidate_thresholds: CandidateThresholdConfig = field(default_factory=CandidateThresholdConfig)

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "category": self.category,
            "selected_cards": [asdict(card) for card in self.selected_cards],
            "hydrated_windows": [asdict(window) for window in self.hydrated_windows],
            "hydrated_evidence_refs": list(self.hydrated_evidence_refs),
            "metrics": self.metrics.as_dict(),
            "candidate_thresholds": self.candidate_thresholds.as_dict(),
        }


def triage_summary_cards(
    query: str, cards: Sequence[SummaryCard], *, bounds: RetrievalBounds
) -> tuple[SummaryCardMatch, ...]:
    """Rank only summary-card metadata before any transcript window is hydrated."""

    query_terms = _terms(_require_string(query, "query"))
    scored: list[SummaryCardMatch] = []
    for card in cards:
        card_terms = _terms(card.searchable_text())
        matched = tuple(sorted(query_terms & card_terms))
        if matched:
            scored.append(SummaryCardMatch(card_id=card.card_id, score=len(matched), matched_terms=matched))
    scored.sort(key=lambda match: (-match.score, match.card_id))
    return tuple(scored[: bounds.max_summary_cards])


def _render_turn(turn: TranscriptTurn) -> str:
    timestamp = f" [{turn.timestamp}]" if turn.timestamp else ""
    return f"{turn.turn_id}{timestamp} {turn.speaker}: {turn.text}"


def hydrate_bounded_windows(
    selected_cards: Sequence[SummaryCardMatch],
    cards: Sequence[SummaryCard],
    windows: Sequence[TranscriptWindow],
    *,
    bounds: RetrievalBounds,
) -> tuple[HydratedWindow, ...]:
    """Hydrate only card-linked windows under a total character budget."""

    cards_by_id = {card.card_id: card for card in cards}
    windows_by_id = {window.window_id: window for window in windows}
    hydrated: list[HydratedWindow] = []
    remaining_chars = bounds.max_window_chars
    seen_windows: set[str] = set()

    for match in selected_cards:
        card = cards_by_id[match.card_id]
        for window_id in card.window_refs:
            if window_id in seen_windows:
                continue
            if remaining_chars <= 0:
                return tuple(hydrated)
            window = windows_by_id[window_id]
            seen_windows.add(window_id)
            rendered = "\n".join(_render_turn(turn) for turn in window.turns[: bounds.max_window_turns])
            clipped = rendered[:remaining_chars]
            hydrated.append(
                HydratedWindow(
                    window_id=window.window_id,
                    conversation_id=window.conversation_id,
                    evidence_ref=window.evidence_ref,
                    text=clipped,
                    character_count=len(clipped),
                    truncated=len(clipped) < len(rendered),
                )
            )
            remaining_chars -= len(clipped)
    return tuple(hydrated)


def _summary_card_proxy(card: SummaryCard, limit: int) -> str:
    raw = " | ".join(
        part
        for part in (card.card_id, card.title, card.summary, ", ".join(card.entities), card.happened_at or "")
        if part
    )
    return raw[:limit]


def _validate_latency(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError("supplied_latency_ms must be a finite non-negative number")
    return float(value)


def evaluate_retrieval_case(
    case: RetrievalCase,
    expected_evidence_refs: Sequence[str],
    *,
    supplied_latency_ms: float,
    candidate_thresholds: CandidateThresholdConfig | None = None,
) -> RetrievalEvaluation:
    """Evaluate deterministic retrieval mechanics against externally supplied refs."""

    expected = frozenset(_require_string(ref, "expected evidence ref") for ref in expected_evidence_refs)
    selected = triage_summary_cards(case.query, case.summary_cards, bounds=case.bounds)
    hydrated = hydrate_bounded_windows(
        selected,
        case.summary_cards,
        case.windows,
        bounds=case.bounds,
    )
    hydrated_refs = tuple(window.evidence_ref for window in hydrated)
    hydrated_set = frozenset(hydrated_refs)
    matched = expected & hydrated_set
    false_positive_refs = hydrated_set - expected
    if expected:
        source_hit = len(matched) / len(expected)
    else:
        source_hit = float(not hydrated_set)
    false_positive_rate = len(false_positive_refs) / max(1, len(hydrated_set))
    cited = frozenset(case.candidate_answer.cited_refs)
    if cited:
        evidence_grounding = float(cited <= hydrated_set)
    else:
        evidence_grounding = float(not hydrated_set)
    proxy_parts = [_require_string(case.query, "query"), case.candidate_answer.text]
    proxy_parts.extend(
        _summary_card_proxy(
            next(card for card in case.summary_cards if card.card_id == match.card_id),
            case.bounds.max_summary_card_chars,
        )
        for match in selected
    )
    proxy_parts.extend(window.text for window in hydrated)
    character_proxy = sum(len(part) for part in proxy_parts)
    metrics = RetrievalMetrics(
        source_hit=source_hit,
        false_positive=float(bool(false_positive_refs)),
        false_positive_rate=false_positive_rate,
        evidence_grounding=evidence_grounding,
        tool_call_count=1 + int(bool(selected)),
        character_proxy=character_proxy,
        token_proxy=math.ceil(character_proxy / 4),
        supplied_latency_ms=_validate_latency(supplied_latency_ms),
        matched_expected_ref_count=len(matched),
        expected_ref_count=len(expected),
        hydrated_ref_count=len(hydrated_set),
    )
    return RetrievalEvaluation(
        case_id=case.case_id,
        category=case.category,
        selected_cards=selected,
        hydrated_windows=hydrated,
        hydrated_evidence_refs=hydrated_refs,
        metrics=metrics,
        candidate_thresholds=candidate_thresholds or CandidateThresholdConfig(),
    )


def load_retrieval_golden_set(path: Path | None = None) -> list[RetrievalCase]:
    fixture_path = path or DEFAULT_GOLDEN_SET
    raw = json.loads(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping) or raw.get("schema_version") != RETRIEVAL_EVAL_SCHEMA_VERSION:
        raise ValueError("retrieval golden set has unsupported schema_version")
    if not _require_string(raw.get("set_version"), "set_version"):
        raise ValueError("set_version is required")
    raw_cases = raw.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("retrieval golden set cases must be a non-empty list")
    cases = [
        RetrievalCase.from_mapping(case, index) for index, case in enumerate(raw_cases) if isinstance(case, Mapping)
    ]
    if len(cases) != len(raw_cases):
        raise ValueError("retrieval golden set contains a non-object case")
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("retrieval golden set contains duplicate case IDs")
    return cases


def load_retrieval_expected_refs(path: Path | None = None) -> dict[str, tuple[str, ...]]:
    fixture_path = path or DEFAULT_EXPECTED_REFS
    raw = json.loads(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping) or raw.get("schema_version") != RETRIEVAL_EVAL_SCHEMA_VERSION:
        raise ValueError("retrieval expected refs have unsupported schema_version")
    refs = raw.get("expected_evidence_refs")
    if not isinstance(refs, Mapping) or not refs:
        raise ValueError("expected_evidence_refs must be a non-empty object")
    result: dict[str, tuple[str, ...]] = {}
    for case_id, values in refs.items():
        case_key = _require_string(case_id, "expected ref case ID")
        result[case_key] = _require_string_list(values, f"expected_evidence_refs.{case_key}")
    return result


def evaluate_retrieval_golden_set(
    cases: Sequence[RetrievalCase],
    expected_refs: Mapping[str, Sequence[str]],
    *,
    supplied_latency_ms: Mapping[str, float] | None = None,
    candidate_thresholds: CandidateThresholdConfig | None = None,
) -> tuple[RetrievalEvaluation, ...]:
    """Evaluate a fixture set without choosing or applying product thresholds."""

    latencies = supplied_latency_ms or {}
    case_ids = {case.case_id for case in cases}
    if set(expected_refs) != case_ids:
        raise ValueError("expected refs must cover exactly the supplied golden cases")
    return tuple(
        evaluate_retrieval_case(
            case,
            expected_refs[case.case_id],
            supplied_latency_ms=latencies.get(case.case_id, 0.0),
            candidate_thresholds=candidate_thresholds,
        )
        for case in cases
    )


__all__ = [
    "CandidateAnswer",
    "CandidateThresholdConfig",
    "DEFAULT_EXPECTED_REFS",
    "DEFAULT_GOLDEN_SET",
    "HydratedWindow",
    "RETRIEVAL_EVAL_SCHEMA_VERSION",
    "RetrievalBounds",
    "RetrievalCase",
    "RetrievalEvaluation",
    "RetrievalMetrics",
    "SummaryCard",
    "SummaryCardMatch",
    "TranscriptTurn",
    "TranscriptWindow",
    "evaluate_retrieval_case",
    "evaluate_retrieval_golden_set",
    "hydrate_bounded_windows",
    "load_retrieval_expected_refs",
    "load_retrieval_golden_set",
    "triage_summary_cards",
]
