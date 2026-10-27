"""Episode telemetry. Bounded label vocabularies, never labeled by uid; helpers never raise.

- per-moment calls, tokens and estimated cost (``omi_episode_moment_*``)
- close reasons (``omi_episode_closed_total``)
- provisional precision: kept vs dropped vs dismissed at reconciliation
  (``omi_episode_provisional_items_total``)
- wrap-up latency: end of the closing conversation's speech to its finished
  notes (``omi_episode_wrapup_latency_seconds``)
- boundary decisions, including Jev answers (``omi_episode_boundary_total``)
- client gating: moments skipped because no capable client was seen
  (``omi_episode_moments_skipped_no_client_total``), and live conversations by
  whether the user's client was seen (``omi_episode_live_sessions_total``)
- episodes API calls by client channel and admission outcome
  (``omi_episode_client_requests_total``)
"""

from __future__ import annotations

from collections.abc import Mapping

from prometheus_client import REGISTRY, Counter, Histogram

from config.episodes import EST_INPUT_USD_PER_MTOK, EST_OUTPUT_USD_PER_MTOK


def _reuse_or_create(factory, name: str, documentation: str, labelnames: list[str], **kwargs):
    """Module-reload-safe collector: reuse only an identical registration, else raise."""
    registered = getattr(REGISTRY, '_names_to_collectors', {})
    existing = registered.get(name) if isinstance(registered, Mapping) else None
    if existing is not None:
        if type(existing) is not factory or list(getattr(existing, '_labelnames', ())) != list(labelnames):
            raise ValueError(f'metric {name} already registered with a different shape')
        return existing
    return factory(name, documentation, labelnames, **kwargs)


MOMENT_OUTCOMES = frozenset(
    {
        'applied',
        'skipped_short',
        'skipped_applied',
        'skipped_closed',
        'rate_limited',
        'llm_error',
        'parse_error',
        'conflict',
        'error',
    }
)
MOMENT_TRIGGERS = frozenset({'pause', 'rollover', 'interval', 'session_end', 'finalize'})
# Gated work that never ran: ended moments by trigger, plus conversation attaches.
SKIP_TRIGGERS = MOMENT_TRIGGERS | {'attach'}
CLOSE_REASON_LABELS = frozenset(
    {'user', 'gap', 'idle', 'hard_cap', 'source_change', 'calendar_boundary', 'moved_on', 'boundary'}
)
PROVISIONAL_OUTCOMES = frozenset({'kept', 'dropped', 'dismissed'})
BOUNDARY_OUTCOMES = frozenset(
    {
        'new',
        'continue',
        'parallel',
        'pending',
        'close',
        'jev_continue',
        'jev_close',
        'jev_no_answer',
        'sync_rejoin',
        'sync_rejoin_member',
    }
)

EPISODE_MOMENT_UPDATES_TOTAL = _reuse_or_create(
    Counter,
    'omi_episode_moment_updates_total',
    'Per-moment incremental episode updates by trigger and outcome. Never labeled by uid.',
    ['trigger', 'outcome'],
)
EPISODE_MOMENT_TOKENS_TOTAL = _reuse_or_create(
    Counter,
    'omi_episode_moment_tokens_total',
    'Tokens spent by the per-moment incremental update (kind=input|output).',
    ['kind'],
)
EPISODE_MOMENT_COST_USD_TOTAL = _reuse_or_create(
    Counter,
    'omi_episode_moment_cost_usd_total',
    'Estimated USD for per-moment updates at the gpt-5-nano rate card; the gateway ledger is authoritative.',
    [],
)
EPISODE_MOMENT_LATENCY_SECONDS = _reuse_or_create(
    Histogram,
    'omi_episode_moment_update_latency_seconds',
    'Model latency of the per-moment incremental update.',
    ['outcome'],
    buckets=(0.25, 0.5, 1, 2, 3, 5, 8, 13, 20),
)
EPISODE_CLOSED_TOTAL = _reuse_or_create(
    Counter, 'omi_episode_closed_total', 'Episodes closed, by close reason.', ['reason']
)
EPISODE_PROVISIONAL_ITEMS_TOTAL = _reuse_or_create(
    Counter,
    'omi_episode_provisional_items_total',
    'Provisional items at reconciliation: kept (became a saved task), dropped, dismissed by the user.',
    ['outcome'],
)
EPISODE_WRAPUP_LATENCY_SECONDS = _reuse_or_create(
    Histogram,
    'omi_episode_wrapup_latency_seconds',
    'Seconds from the end of an episode-closing conversation to its finished notes.',
    ['reason'],
    buckets=(5, 15, 30, 60, 120, 300, 600, 1200, 3600),
)
EPISODE_BOUNDARY_TOTAL = _reuse_or_create(
    Counter,
    'omi_episode_boundary_total',
    'Moment boundary decisions against the open episode.',
    ['outcome'],
)
EPISODE_MOMENTS_SKIPPED_NO_CLIENT_TOTAL = _reuse_or_create(
    Counter,
    'omi_episode_moments_skipped_no_client_total',
    'Admitted moments, finalization tails and conversation attaches skipped because the user has no client that called /v1/episodes.',
    ['trigger'],
)
EPISODE_LIVE_SESSIONS_TOTAL = _reuse_or_create(
    Counter,
    'omi_episode_live_sessions_total',
    'Admitted live conversations at their first speech, by whether a capable client was seen (true|false).',
    ['client_seen'],
)
CLIENT_CHANNELS = frozenset({'beta', 'store', 'unknown'})
CLIENT_REQUEST_OUTCOMES = frozenset({'admitted', 'channel_closed', 'not_admitted'})
EPISODE_CLIENT_REQUESTS_TOTAL = _reuse_or_create(
    Counter,
    'omi_episode_client_requests_total',
    'Episodes API calls by X-Omi-App-Channel (beta|store|unknown) and outcome (admitted|channel_closed|not_admitted).',
    ['channel', 'outcome'],
)


def _label(value: str, allowed: frozenset[str]) -> str:
    return value if value in allowed else 'other'


def _prime() -> None:
    """Export every bounded series at zero from process start.

    Cloud Run and pusher replicas come and go; a series born at its first increment
    makes ``increase()`` miss that increment, and for a rare event (a few calls a day)
    that was most of them: the cost counter read about zero.
    """
    try:
        for trigger in MOMENT_TRIGGERS:
            for outcome in MOMENT_OUTCOMES:
                EPISODE_MOMENT_UPDATES_TOTAL.labels(trigger=trigger, outcome=_label(outcome, MOMENT_OUTCOMES))
        for trigger in SKIP_TRIGGERS:
            EPISODE_MOMENTS_SKIPPED_NO_CLIENT_TOTAL.labels(trigger=trigger)
        for kind in ('input', 'output'):
            EPISODE_MOMENT_TOKENS_TOTAL.labels(kind=kind)
        for reason in CLOSE_REASON_LABELS:
            EPISODE_CLOSED_TOTAL.labels(reason=_label(reason, CLOSE_REASON_LABELS))
        for outcome in PROVISIONAL_OUTCOMES:
            EPISODE_PROVISIONAL_ITEMS_TOTAL.labels(outcome=_label(outcome, PROVISIONAL_OUTCOMES))
        for outcome in BOUNDARY_OUTCOMES:
            EPISODE_BOUNDARY_TOTAL.labels(outcome=_label(outcome, BOUNDARY_OUTCOMES))
        for outcome in MOMENT_OUTCOMES:
            EPISODE_MOMENT_LATENCY_SECONDS.labels(outcome=_label(outcome, MOMENT_OUTCOMES))
        for reason in CLOSE_REASON_LABELS:
            EPISODE_WRAPUP_LATENCY_SECONDS.labels(reason=_label(reason, CLOSE_REASON_LABELS))
        for seen in ('true', 'false'):
            EPISODE_LIVE_SESSIONS_TOTAL.labels(client_seen=seen)
        for channel in CLIENT_CHANNELS:
            for outcome in CLIENT_REQUEST_OUTCOMES:
                EPISODE_CLIENT_REQUESTS_TOTAL.labels(channel=channel, outcome=_label(outcome, CLIENT_REQUEST_OUTCOMES))
    except Exception:
        pass


_prime()


def estimated_cost_usd(input_tokens: int, output_tokens: int) -> float:
    return (max(0, input_tokens) * EST_INPUT_USD_PER_MTOK + max(0, output_tokens) * EST_OUTPUT_USD_PER_MTOK) / 1e6


def record_moment_update(
    *, trigger: str, outcome: str, input_tokens: int = 0, output_tokens: int = 0, latency_seconds: float | None = None
) -> None:
    try:
        outcome_label = _label(outcome, MOMENT_OUTCOMES)
        EPISODE_MOMENT_UPDATES_TOTAL.labels(trigger=_label(trigger, MOMENT_TRIGGERS), outcome=outcome_label).inc()
        if input_tokens > 0:
            EPISODE_MOMENT_TOKENS_TOTAL.labels(kind='input').inc(input_tokens)
        if output_tokens > 0:
            EPISODE_MOMENT_TOKENS_TOTAL.labels(kind='output').inc(output_tokens)
        cost = estimated_cost_usd(input_tokens, output_tokens)
        if cost > 0:
            EPISODE_MOMENT_COST_USD_TOTAL.inc(cost)
        if latency_seconds is not None:
            EPISODE_MOMENT_LATENCY_SECONDS.labels(outcome=outcome_label).observe(max(0.0, latency_seconds))
    except Exception:
        pass


def record_episode_closed(reason: str) -> None:
    try:
        EPISODE_CLOSED_TOTAL.labels(reason=_label(reason, CLOSE_REASON_LABELS)).inc()
    except Exception:
        pass


def record_provisional_outcomes(counts: Mapping[str, int]) -> None:
    try:
        for outcome, count in counts.items():
            if count > 0:
                EPISODE_PROVISIONAL_ITEMS_TOTAL.labels(outcome=_label(outcome, PROVISIONAL_OUTCOMES)).inc(count)
    except Exception:
        pass


def record_wrapup_latency(reason: str, seconds: float) -> None:
    try:
        EPISODE_WRAPUP_LATENCY_SECONDS.labels(reason=_label(reason, CLOSE_REASON_LABELS)).observe(max(0.0, seconds))
    except Exception:
        pass


def record_boundary(outcome: str) -> None:
    try:
        EPISODE_BOUNDARY_TOTAL.labels(outcome=_label(outcome, BOUNDARY_OUTCOMES)).inc()
    except Exception:
        pass


def record_moment_skipped_no_client(trigger: str) -> None:
    try:
        EPISODE_MOMENTS_SKIPPED_NO_CLIENT_TOTAL.labels(trigger=_label(trigger, SKIP_TRIGGERS)).inc()
    except Exception:
        pass


def record_live_session(client_seen: bool) -> None:
    try:
        EPISODE_LIVE_SESSIONS_TOTAL.labels(client_seen='true' if client_seen else 'false').inc()
    except Exception:
        pass


def record_client_request(channel: str, outcome: str) -> None:
    try:
        EPISODE_CLIENT_REQUESTS_TOTAL.labels(
            channel=channel if channel in CLIENT_CHANNELS else 'unknown',
            outcome=_label(outcome, CLIENT_REQUEST_OUTCOMES),
        ).inc()
    except Exception:
        pass
