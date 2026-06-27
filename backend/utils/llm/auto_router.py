"""Daily benchmark-based LLM route selection.

The static QoS profiles remain the safety net. This module only decides when a
benchmarked route is a better value for a feature and explains that choice in a
serializable route table.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple

ARTIFICIAL_ANALYSIS_URL = "https://artificialanalysis.ai/api/v2/data/llms/models"
AUTO_ROUTER_ATTRIBUTION = "https://artificialanalysis.ai/"
AUTO_ROUTER_TTL_SECONDS = 24 * 3600
AUTO_ROUTER_SPEED_CAP_TPS = 250.0
AUTO_ROUTER_MIN_SCORE_MARGIN = 0.015

SUPPORTED_PROVIDERS = frozenset({"openai", "gemini", "openrouter", "anthropic", "perplexity"})
OPENAI_COMPATIBLE_PROVIDERS = frozenset({"openai", "gemini"})
PROVIDER_ALIASES = {
    "openai": frozenset({"openai"}),
    "gemini": frozenset({"gemini", "google", "google-ai", "google-deepmind"}),
    "openrouter": frozenset({"openrouter"}),
    "anthropic": frozenset({"anthropic", "claude"}),
    "perplexity": frozenset({"perplexity", "sonar"}),
}


@dataclass(frozen=True)
class CandidateSpec:
    model: str
    provider: str
    aliases: Tuple[str, ...]
    supports_structured_output: bool = True
    supports_prompt_cache: bool = False

    @property
    def key(self) -> str:
        return f"{self.provider}:{self.model}"


@dataclass(frozen=True)
class BenchmarkMetrics:
    model: str
    provider: str
    quality: Optional[float]
    speed_tps: Optional[float]
    input_price_per_million: Optional[float]
    output_price_per_million: Optional[float]
    latency_ms: Optional[float]
    source_name: str

    def to_public_dict(self) -> Dict[str, Any]:
        return {
            "quality": _round_or_none(self.quality, 3),
            "speed_tps": _round_or_none(self.speed_tps, 3),
            "input_price_per_million": _round_or_none(self.input_price_per_million, 6),
            "output_price_per_million": _round_or_none(self.output_price_per_million, 6),
            "latency_ms": _round_or_none(self.latency_ms, 3),
            "source_name": self.source_name,
        }


@dataclass(frozen=True)
class FeaturePolicy:
    quality_weight: float
    speed_weight: float
    cost_weight: float
    input_token_weight: float
    output_token_weight: float
    min_quality: float
    mode: str


MODEL_CANDIDATES: Tuple[CandidateSpec, ...] = (
    CandidateSpec("gpt-5.4", "openai", ("gpt-5.4", "gpt 5.4"), supports_prompt_cache=True),
    CandidateSpec("gpt-5.4-mini", "openai", ("gpt-5.4-mini", "gpt 5.4 mini"), supports_prompt_cache=True),
    CandidateSpec("gpt-4.1", "openai", ("gpt-4.1", "gpt 4.1")),
    CandidateSpec("gpt-4.1-mini", "openai", ("gpt-4.1-mini", "gpt 4.1 mini")),
    CandidateSpec("gpt-4.1-nano", "openai", ("gpt-4.1-nano", "gpt 4.1 nano")),
    CandidateSpec("o4-mini", "openai", ("o4-mini", "o4 mini")),
    CandidateSpec("gemini-2.5-flash-lite", "gemini", ("gemini-2.5-flash-lite", "gemini 2.5 flash lite")),
    CandidateSpec("gemini-3-flash-preview", "openrouter", ("gemini-3-flash-preview", "gemini 3 flash preview")),
    CandidateSpec("claude-sonnet-4-6", "anthropic", ("claude-sonnet-4-6", "claude sonnet 4.6")),
    CandidateSpec("sonar-pro", "perplexity", ("sonar-pro", "sonar pro")),
)

QUALITY_FIRST_FEATURES = {
    "app_generator",
    "chat_graph",
    "chat_responses",
    "conv_action_items",
    "conv_app_result",
    "conv_structure",
    "daily_summary",
    "goals_advice",
    "knowledge_graph",
    "learnings",
    "notifications",
    "openglass",
    "persona_chat_premium",
    "persona_clone",
}

EFFICIENCY_FIRST_FEATURES = {
    "app_integration",
    "conv_app_select",
    "conv_discard",
    "conv_folder",
    "daily_summary_simple",
    "followup",
    "memory_category",
    "onboarding",
    "session_titles",
    "smart_glasses",
    "trends",
}

OUTPUT_HEAVY_FEATURES = {
    "app_generator",
    "chat_responses",
    "goals_advice",
    "knowledge_graph",
    "notifications",
    "openglass",
    "persona_chat",
    "persona_chat_premium",
    "persona_clone",
}

INPUT_HEAVY_FEATURES = {
    "chat_extraction",
    "chat_graph",
    "conv_action_items",
    "conv_app_result",
    "conv_structure",
    "daily_summary",
    "external_structure",
    "learnings",
    "memories",
    "memory_conflict",
}

BALANCED_POLICY = FeaturePolicy(
    quality_weight=0.45,
    speed_weight=0.25,
    cost_weight=0.30,
    input_token_weight=0.65,
    output_token_weight=0.35,
    min_quality=55.0,
    mode="balanced",
)

QUALITY_POLICY = FeaturePolicy(
    quality_weight=0.60,
    speed_weight=0.15,
    cost_weight=0.25,
    input_token_weight=0.60,
    output_token_weight=0.40,
    min_quality=68.0,
    mode="quality",
)

EFFICIENCY_POLICY = FeaturePolicy(
    quality_weight=0.30,
    speed_weight=0.35,
    cost_weight=0.35,
    input_token_weight=0.75,
    output_token_weight=0.25,
    min_quality=45.0,
    mode="efficiency",
)


def get_feature_policy(feature: str) -> FeaturePolicy:
    """Return the scoring policy for a backend LLM feature."""

    if feature in QUALITY_FIRST_FEATURES:
        base = QUALITY_POLICY
    elif feature in EFFICIENCY_FIRST_FEATURES:
        base = EFFICIENCY_POLICY
    else:
        base = BALANCED_POLICY

    if feature in OUTPUT_HEAVY_FEATURES:
        return FeaturePolicy(
            quality_weight=base.quality_weight,
            speed_weight=base.speed_weight,
            cost_weight=base.cost_weight,
            input_token_weight=0.45,
            output_token_weight=0.55,
            min_quality=base.min_quality,
            mode=base.mode,
        )
    if feature in INPUT_HEAVY_FEATURES:
        return FeaturePolicy(
            quality_weight=base.quality_weight,
            speed_weight=base.speed_weight,
            cost_weight=base.cost_weight,
            input_token_weight=0.80,
            output_token_weight=0.20,
            min_quality=base.min_quality,
            mode=base.mode,
        )
    return base


def parse_artificial_analysis_models(payload: Optional[Mapping[str, Any]]) -> Dict[str, BenchmarkMetrics]:
    """Parse Artificial Analysis model data into metrics for known Omi candidates.

    The parser intentionally accepts several common field names so a harmless
    API shape change does not break routing. Rows that cannot be mapped to a
    known model are ignored.
    """

    rows = _model_rows(payload)
    parsed: Dict[str, BenchmarkMetrics] = {}
    best_alias_lengths: Dict[str, int] = {}

    for row in rows:
        candidate, alias_length = _match_candidate(row)
        if candidate is None:
            continue

        metrics = BenchmarkMetrics(
            model=candidate.model,
            provider=candidate.provider,
            quality=_extract_number(
                row,
                (
                    ("evaluations", "artificial_analysis_intelligence_index"),
                    ("evaluations", "quality_index"),
                    ("artificial_analysis_intelligence_index",),
                    ("quality_index",),
                    ("quality",),
                    ("intelligence",),
                ),
            ),
            speed_tps=_extract_number(
                row,
                (
                    ("median_output_tokens_per_second",),
                    ("output_speed", "median_tokens_per_second"),
                    ("output_speed", "tokens_per_second"),
                    ("tokens_per_second",),
                    ("speed",),
                ),
            ),
            input_price_per_million=_extract_number(
                row,
                (
                    ("pricing", "input"),
                    ("pricing", "input_per_million_tokens"),
                    ("pricing", "prompt"),
                    ("price_1m_input_tokens",),
                    ("input_price",),
                    ("prompt_price",),
                ),
            ),
            output_price_per_million=_extract_number(
                row,
                (
                    ("pricing", "output"),
                    ("pricing", "output_per_million_tokens"),
                    ("pricing", "completion"),
                    ("price_1m_output_tokens",),
                    ("output_price",),
                    ("completion_price",),
                ),
            ),
            latency_ms=_extract_number(
                row,
                (
                    ("latency", "median_ms"),
                    ("median_latency_ms",),
                    ("time_to_first_token_ms",),
                ),
            ),
            source_name=str(row.get("name") or row.get("slug") or row.get("id") or candidate.model),
        )

        previous_length = best_alias_lengths.get(candidate.key, -1)
        previous = parsed.get(candidate.key)
        if (
            previous is None
            or alias_length > previous_length
            or _metric_completeness(metrics) > _metric_completeness(previous)
        ):
            parsed[candidate.key] = metrics
            best_alias_lengths[candidate.key] = alias_length

    return parsed


def build_auto_route_table(
    profile_name: str,
    static_profile: Mapping[str, Tuple[str, str]],
    benchmark_payload: Optional[Mapping[str, Any]],
    structured_output_features: Iterable[str],
    anthropic_only_features: Iterable[str],
    perplexity_only_features: Iterable[str],
    pinned_features: Optional[Mapping[str, Tuple[str, str]]] = None,
    now: Optional[datetime] = None,
    ttl_seconds: int = AUTO_ROUTER_TTL_SECONDS,
    disabled_reason: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a complete route table with static fallbacks and dynamic picks."""

    now = now or datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=ttl_seconds)
    benchmark_metrics = parse_artificial_analysis_models(benchmark_payload)
    structured = set(structured_output_features)
    anthropic_only = set(anthropic_only_features)
    perplexity_only = set(perplexity_only_features)
    pinned = pinned_features or {}

    routes: Dict[str, Dict[str, Any]] = {}
    total_candidates = 0

    for feature, fallback in sorted(static_profile.items()):
        route, considered = _select_feature_route(
            feature=feature,
            fallback=fallback,
            benchmark_metrics=benchmark_metrics,
            structured_output_features=structured,
            anthropic_only_features=anthropic_only,
            perplexity_only_features=perplexity_only,
            disabled_reason=disabled_reason,
        )
        route.update(
            {
                "feature": feature,
                "profile": profile_name,
                "updated_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
            }
        )
        routes[feature] = route
        total_candidates += considered

    for feature, fallback in sorted(pinned.items()):
        routes[feature] = {
            "feature": feature,
            "model": fallback[0],
            "provider": fallback[1],
            "fallback_model": fallback[0],
            "fallback_provider": fallback[1],
            "source": "pinned",
            "reason": "pinned_feature",
            "profile": profile_name,
            "updated_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
        }

    dynamic_count = sum(1 for route in routes.values() if route.get("source") == "auto-router")
    return {
        "profile": profile_name,
        "source": "auto-router",
        "updated_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "ttl_seconds": ttl_seconds,
        "attribution": AUTO_ROUTER_ATTRIBUTION,
        "routes": routes,
        "summary": {
            "dynamic_count": dynamic_count,
            "static_count": len(routes) - dynamic_count,
            "known_candidate_count": len(MODEL_CANDIDATES),
            "benchmarked_candidate_count": len(benchmark_metrics),
            "candidates_considered": total_candidates,
            "disabled_reason": disabled_reason,
        },
    }


def _select_feature_route(
    feature: str,
    fallback: Tuple[str, str],
    benchmark_metrics: Mapping[str, BenchmarkMetrics],
    structured_output_features: set[str],
    anthropic_only_features: set[str],
    perplexity_only_features: set[str],
    disabled_reason: Optional[str],
) -> Tuple[Dict[str, Any], int]:
    fallback_model, fallback_provider = fallback
    policy = get_feature_policy(feature)
    base_route = {
        "model": fallback_model,
        "provider": fallback_provider,
        "fallback_model": fallback_model,
        "fallback_provider": fallback_provider,
        "source": "static",
        "policy": policy.mode,
    }

    if disabled_reason:
        return {**base_route, "reason": disabled_reason}, 0

    candidates = _eligible_candidates(
        feature,
        fallback_provider,
        structured_output_features,
        anthropic_only_features,
        perplexity_only_features,
    )
    scored = []
    for candidate in candidates:
        metrics = benchmark_metrics.get(candidate.key)
        if metrics is None or metrics.quality is None:
            continue
        if metrics.quality < policy.min_quality:
            continue
        weighted_price = _weighted_price(metrics, policy)
        scored.append((candidate, metrics, weighted_price))

    if not scored:
        return {**base_route, "reason": "no_benchmark_for_eligible_candidates"}, len(candidates)

    prices = [p for _candidate, _metrics, p in scored if p is not None]
    min_price = min(prices) if prices else None
    max_price = max(prices) if prices else None
    scored_routes = []

    for candidate, metrics, weighted_price in scored:
        score = _score_metrics(metrics, policy, weighted_price, min_price, max_price)
        scored_routes.append((score, candidate, metrics, weighted_price))

    scored_routes.sort(key=lambda item: item[0], reverse=True)
    fallback_key = f"{fallback_provider}:{fallback_model}"
    fallback_score = next(
        (score for score, candidate, _metrics, _price in scored_routes if candidate.key == fallback_key), None
    )
    best_score, best_candidate, best_metrics, best_price = scored_routes[0]

    if best_candidate.key != fallback_key and fallback_score is not None:
        if best_score < fallback_score + AUTO_ROUTER_MIN_SCORE_MARGIN:
            fallback_metrics = benchmark_metrics.get(fallback_key)
            route = {
                **base_route,
                "reason": "fallback_within_score_margin",
                "score": round(fallback_score, 4),
                "best_candidate": {
                    "model": best_candidate.model,
                    "provider": best_candidate.provider,
                    "score": round(best_score, 4),
                },
            }
            if fallback_metrics:
                route["benchmark"] = fallback_metrics.to_public_dict()
            return route, len(candidates)

    route = {
        "model": best_candidate.model,
        "provider": best_candidate.provider,
        "fallback_model": fallback_model,
        "fallback_provider": fallback_provider,
        "source": "auto-router" if best_candidate.key != fallback_key else "static",
        "reason": "benchmark_value_pick" if best_candidate.key != fallback_key else "static_route_still_best",
        "policy": policy.mode,
        "score": round(best_score, 4),
        "weighted_price_per_million": _round_or_none(best_price, 6),
        "benchmark": best_metrics.to_public_dict(),
    }
    return route, len(candidates)


def _eligible_candidates(
    feature: str,
    fallback_provider: str,
    structured_output_features: set[str],
    anthropic_only_features: set[str],
    perplexity_only_features: set[str],
) -> Tuple[CandidateSpec, ...]:
    if feature in anthropic_only_features:
        allowed_providers = {"anthropic"}
    elif feature in perplexity_only_features:
        allowed_providers = {"perplexity"}
    elif fallback_provider == "openrouter":
        allowed_providers = {"openrouter"}
    else:
        allowed_providers = set(OPENAI_COMPATIBLE_PROVIDERS)

    candidates = []
    for candidate in MODEL_CANDIDATES:
        if candidate.provider not in allowed_providers:
            continue
        if feature in structured_output_features and not candidate.supports_structured_output:
            continue
        candidates.append(candidate)
    return tuple(candidates)


def _score_metrics(
    metrics: BenchmarkMetrics,
    policy: FeaturePolicy,
    weighted_price: Optional[float],
    min_price: Optional[float],
    max_price: Optional[float],
) -> float:
    quality = _clamp((metrics.quality or 0.0) / 100.0, 0.0, 1.0)
    speed = 0.50 if metrics.speed_tps is None else _clamp(metrics.speed_tps / AUTO_ROUTER_SPEED_CAP_TPS, 0.0, 1.0)
    cost = _cost_score(weighted_price, min_price, max_price)
    return policy.quality_weight * quality + policy.speed_weight * speed + policy.cost_weight * cost


def _cost_score(price: Optional[float], min_price: Optional[float], max_price: Optional[float]) -> float:
    if price is None or min_price is None or max_price is None:
        return 0.50
    if max_price <= min_price:
        return 1.0
    return _clamp(1.0 - ((price - min_price) / (max_price - min_price)), 0.0, 1.0)


def _weighted_price(metrics: BenchmarkMetrics, policy: FeaturePolicy) -> Optional[float]:
    input_price = metrics.input_price_per_million
    output_price = metrics.output_price_per_million
    if input_price is None and output_price is None:
        return None
    if input_price is None:
        return output_price
    if output_price is None:
        return input_price
    return policy.input_token_weight * input_price + policy.output_token_weight * output_price


def _model_rows(payload: Optional[Mapping[str, Any]]) -> Sequence[Mapping[str, Any]]:
    if not payload:
        return ()
    rows = payload.get("data") or payload.get("models") or payload.get("items") or payload
    if not isinstance(rows, list):
        return ()
    return tuple(row for row in rows if isinstance(row, Mapping))


def _match_candidate(row: Mapping[str, Any]) -> Tuple[Optional[CandidateSpec], int]:
    name = " ".join(str(row.get(key) or "") for key in ("slug", "id", "name", "model"))
    normalized_name = _normalize_alias(name)
    provider_hints = _row_provider_hints(row)
    matches = []
    for candidate in MODEL_CANDIDATES:
        for alias in (candidate.model, *candidate.aliases):
            normalized_alias = _normalize_alias(alias)
            if not normalized_alias:
                continue
            if _contains_alias(normalized_name, normalized_alias):
                matches.append((len(normalized_alias), candidate))
    if not matches:
        return None, 0

    provider_matches = [
        (alias_length, candidate)
        for alias_length, candidate in matches
        if _candidate_matches_provider_hints(candidate, provider_hints)
    ]
    if provider_matches:
        matches = provider_matches
    elif provider_hints:
        return None, 0
    else:
        longest_alias = max(alias_length for alias_length, _candidate in matches)
        longest_matches = [
            (alias_length, candidate) for alias_length, candidate in matches if alias_length == longest_alias
        ]
        if len({candidate.key for _alias_length, candidate in longest_matches}) > 1:
            return None, 0
        matches = longest_matches

    matches.sort(key=lambda item: item[0], reverse=True)
    return matches[0][1], matches[0][0]


def _row_provider_hints(row: Mapping[str, Any]) -> set[str]:
    explicit_hints = set()
    for key in ("provider", "organization", "creator", "vendor", "company"):
        value = row.get(key)
        if isinstance(value, Mapping):
            value = value.get("name") or value.get("slug") or value.get("id")
        normalized = _normalize_provider_hint(value)
        if normalized:
            explicit_hints.add(normalized)
    if explicit_hints:
        return explicit_hints

    hints = set()
    for key in ("slug", "id", "model"):
        value = row.get(key)
        if not isinstance(value, str):
            continue
        normalized = _normalize_alias(value)
        for provider, aliases in PROVIDER_ALIASES.items():
            if any(normalized == alias or normalized.startswith(f"{alias}-") for alias in aliases):
                hints.add(provider)

    return hints


def _candidate_matches_provider_hints(candidate: CandidateSpec, provider_hints: set[str]) -> bool:
    aliases = PROVIDER_ALIASES.get(candidate.provider, frozenset({candidate.provider}))
    return bool(provider_hints & aliases)


def _normalize_provider_hint(value: Any) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = _normalize_alias(value)
    for provider, aliases in PROVIDER_ALIASES.items():
        if normalized == provider or normalized in aliases:
            return provider
    return normalized


def _contains_alias(name: str, alias: str) -> bool:
    if name == alias:
        return True
    return re.search(rf"(^|[^a-z0-9.]){re.escape(alias)}($|[^a-z0-9.])", name) is not None


def _normalize_alias(value: str) -> str:
    return re.sub(r"[\s_/]+", "-", value.strip().lower())


def _extract_number(row: Mapping[str, Any], paths: Iterable[Tuple[str, ...]]) -> Optional[float]:
    for path in paths:
        value: Any = row
        for key in path:
            if not isinstance(value, Mapping) or key not in value:
                value = None
                break
            value = value[key]
        number = _as_float(value)
        if number is not None:
            return number
    return None


def _as_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, str):
        match = re.search(r"-?\d+(?:\.\d+)?", value.replace(",", ""))
        if not match:
            return None
        number = float(match.group(0))
        return number if math.isfinite(number) else None
    return None


def _metric_completeness(metrics: BenchmarkMetrics) -> int:
    return sum(
        value is not None
        for value in (
            metrics.quality,
            metrics.speed_tps,
            metrics.input_price_per_million,
            metrics.output_price_per_million,
            metrics.latency_ms,
        )
    )


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(max(value, minimum), maximum)


def _round_or_none(value: Optional[float], digits: int) -> Optional[float]:
    if value is None:
        return None
    return round(value, digits)
