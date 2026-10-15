"""Aggregate-only safety metrics; exact one-sided binomial confidence bound."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Outcome:
    decision: str
    latency_ms: float = 0.0
    cost_usd: float | None = 0.0
    calls: int = 0
    error: str | None = None
    source: str = 'local'
    rate_cards: tuple[str, ...] = ()
    known_cost_usd: float = 0.0


def false_agree_upper(errors: int, negatives: int, alpha: float = 0.05) -> float | None:
    """Clopper-Pearson upper endpoint, P[X <= errors | p] = alpha."""
    if not 0 <= errors <= negatives or not 0 < alpha < 1:
        raise ValueError('invalid_binomial_counts')
    if negatives == 0:
        return None
    if errors == negatives:
        return 1.0
    if errors == 0:
        return -math.expm1(math.log(alpha) / negatives)

    def cdf(p: float) -> float:
        terms = [
            math.lgamma(negatives + 1)
            - math.lgamma(k + 1)
            - math.lgamma(negatives - k + 1)
            + k * math.log(p)
            + (negatives - k) * math.log1p(-p)
            for k in range(errors + 1)
        ]
        largest = max(terms)
        return math.exp(largest) * sum(math.exp(value - largest) for value in terms)

    low, high = errors / negatives, 1.0
    for _ in range(65):
        midpoint = (low + high) / 2
        if midpoint == 1.0 or cdf(midpoint) < alpha:
            high = midpoint
        else:
            low = midpoint
    return (low + high) / 2


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q * len(ordered)) - 1)]


@dataclass
class Aggregate:
    matrix: Counter = field(default_factory=Counter)
    errors: Counter = field(default_factory=Counter)
    sources: Counter = field(default_factory=Counter)
    latency: list[float] = field(default_factory=list)
    cost: float = 0.0
    known_cost: float = 0.0
    unknown_cost_items: int = 0
    calls: int = 0
    rate_cards: set[str] = field(default_factory=set)

    def add(self, gold: str, outcome: Outcome) -> None:
        if gold not in {'accept', 'reject'} or outcome.decision not in {'agree', 'disagree', 'review', 'unverified'}:
            raise ValueError('invalid_metric_label')
        self.matrix[gold, outcome.decision] += 1
        self.latency.append(outcome.latency_ms)
        self.calls += outcome.calls
        self.sources[outcome.source] += 1
        self.rate_cards.update(outcome.rate_cards)
        self.known_cost += outcome.known_cost_usd
        if outcome.cost_usd is None:
            self.unknown_cost_items += 1
        else:
            self.cost += outcome.cost_usd
        if outcome.error:
            self.errors[outcome.error] += 1

    def report(self) -> dict[str, Any]:
        n = sum(self.matrix.values())
        negatives = sum(self.matrix['reject', d] for d in ('agree', 'disagree', 'review', 'unverified'))
        positives = n - negatives
        false_agrees = self.matrix['reject', 'agree']
        abstained = sum(self.matrix[g, d] for g in ('accept', 'reject') for d in ('review', 'unverified'))
        return {
            'items': n,
            'gold_reject': negatives,
            'gold_accept': positives,
            'confusion_matrix': {
                g: {d: self.matrix[g, d] for d in ('agree', 'disagree', 'review', 'unverified')}
                for g in ('accept', 'reject')
            },
            'false_agree_rate': false_agrees / negatives if negatives else None,
            'false_agree_upper_95': false_agree_upper(false_agrees, negatives),
            'accept_recall': self.matrix['accept', 'agree'] / positives if positives else None,
            'abstention_unverified_rate': abstained / n if n else None,
            'cost_usd': None if self.unknown_cost_items else self.cost,
            'cost_per_item_usd': None if self.unknown_cost_items or not n else self.cost / n,
            'known_cost_subtotal_usd': self.known_cost,
            'unknown_cost_items': self.unknown_cost_items,
            'gateway_calls': self.calls,
            'latency_ms_p50': percentile(self.latency, 0.5),
            'latency_ms_p95': percentile(self.latency, 0.95),
            'errors': dict(self.errors),
            'deterministic_sources': dict(self.sources),
            'rate_card_ids': sorted(self.rate_cards),
        }


def promotion(candidate: dict[str, Any], baseline: dict[str, Any] | None, *, audited: bool) -> str:
    if not audited:
        return 'hold_pending_independent_label_adjudication'
    if candidate['gold_reject'] < 300 or baseline is None or baseline['gold_reject'] < 300:
        return 'hold_insufficient_per_kind_negatives'
    if candidate['gold_accept'] < 300 or baseline['gold_accept'] < 300:
        return 'hold_insufficient_per_kind_accepts'
    upper, baseline_upper = candidate['false_agree_upper_95'], baseline['false_agree_upper_95']
    if upper is None or baseline_upper is None or upper > 0.01 or upper > baseline_upper:
        return 'keep_baseline_or_review_safety_bound'
    if candidate['cost_usd'] is None or baseline['cost_usd'] is None:
        return 'hold_unknown_cost'
    if candidate['cost_usd'] >= baseline['cost_usd']:
        return 'hold_no_cost_improvement'
    if (
        candidate['accept_recall'] < baseline['accept_recall']
        or candidate['abstention_unverified_rate'] > baseline['abstention_unverified_rate']
    ):
        return 'hold_recall_or_review_burden_regression'
    return 'eligible_for_owner_review_never_automatic_rollout'
