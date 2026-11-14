"""Episode telemetry. Bounded label vocabularies, never labeled by uid; helpers never raise.

- per-moment calls, tokens and estimated cost (``omi_episode_moment_*``)
- close reasons (``omi_episode_closed_total``)
- provisional precision: kept vs dropped vs dismissed at reconciliation
  (``omi_episode_provisional_items_total``)
- wrap-up latency: end of the closing conversation's speech to its finished
  notes (``omi_episode_wrapup_latency_seconds``)
- boundary decisions, including Jev answers (``omi_episode_boundary_total``)
- Variant F candidate privacy refusals (``omi_episode_f_gate_total``) and fallback
  call sites (``omi_episode_f_fallback_total``)
- client gating: moments skipped because no capable client was seen
  (``omi_episode_moments_skipped_no_client_total``), and live conversations by
  whether the user's client was seen (``omi_episode_live_sessions_total``)
- episodes API calls by client channel and admission outcome
  (``omi_episode_client_requests_total``)
- closed-episode composer runs by outcome and trigger, their latency, and the
  paid model calls inside them (``omi_episode_compose_total``,
  ``omi_episode_compose_seconds``, ``omi_episode_compose_calls_total``)
- Home attach-gap read observations (``omi_episode_home_attach_gap_total``)
- Home list members shown and hidden as below the notes floor
  (``omi_episode_home_members_total``)
- closed-episode size by join-variant arm recorded when the episode opened, ``f`` or
  ``control`` (``omi_episode_closed_members``, ``omi_episode_closed_span_seconds``)
"""

from __future__ import annotations

from collections.abc import Mapping

from prometheus_client import REGISTRY, Counter, Histogram, disable_created_metrics

from config.episodes import EST_INPUT_USD_PER_MTOK, EST_OUTPUT_USD_PER_MTOK

# Episode collectors may be imported before the shared backend metrics module
# in listen/pusher worker startup; keep their exposition contract consistent.
disable_created_metrics()


def reuse_or_create(factory, name: str, documentation: str, labelnames: list[str], **kwargs):
    """Module-reload-safe collector: reuse only an identical registration, else raise."""
    registered = getattr(REGISTRY, '_names_to_collectors', {})
    existing = registered.get(name) if isinstance(registered, Mapping) else None
    if existing is not None:
        if type(existing) is not factory or list(getattr(existing, '_labelnames', ())) != list(labelnames):
            raise ValueError(f'metric {name} already registered with a different shape')
        return existing
    return factory(name, documentation, labelnames, **kwargs)


EPISODE_HOME_ATTACH_GAP_TOTAL = reuse_or_create(
    Counter,
    'omi_episode_home_attach_gap_total',
    'Home reads observing an unlinked recording wholly inside a live ownership window; repeated reads count again.',
    [],
)


def record_home_attach_gap() -> None:
    try:
        EPISODE_HOME_ATTACH_GAP_TOTAL.inc()
    except Exception:
        pass  # Telemetry must never fail a Home read.


MOMENT_OUTCOMES = frozenset(
    {
        'applied',
        'skipped_short',
        'skipped_applied',
        'skipped_closed',
        # A write into a closed episode the composer owns: bookkeeping only, no model call.
        'composer_owned',
        'rate_limited',
        'llm_error',
        'parse_error',
        'quality_error',
        'conflict',
        'error',
    }
)
MOMENT_TRIGGERS = frozenset({'pause', 'rollover', 'interval', 'finalize', 'sync_recovery', 'session_end'})
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
        # Variant F (config.episodes.f_join_enabled_for): a recorded-time join marked for F, its
        # answer, its fallback (no answer keeps today's join), and a kill-switched settle.
        'f_pending',
        'f_pending_conflict',
        'f_pending_error',
        'f_continue',
        'f_close',
        'f_no_answer',
        'f_disabled',
        'f_later_member',
        'f_orphan',
        'f_orphan_check_error',
    }
)

F_GATE_REASONS = frozenset(
    {
        'held',
        'client_processing',
        'deferred',
        'local_pending',
        'local_only',
        'row_consent',
        'user_consent',
        'locked_discarded',
        'owner',
        'status',
        'hidden',
        'other',
    }
)

F_FALLBACK_SITES = frozenset(
    {
        'pending_conflict',
        'pending_error',
        'synced_failed',
        'recheck_failed',
        'previous_failed',
        'gate_failed',
        'unknown_previous',
        'recheck_failed_settle',
        'unknown_jev',
        'other',
    }
)

EPISODE_MOMENT_UPDATES_TOTAL = reuse_or_create(
    Counter,
    'omi_episode_moment_updates_total',
    'Per-moment incremental episode updates by trigger and outcome. Never labeled by uid.',
    ['trigger', 'outcome'],
)
EPISODE_MOMENT_TOKENS_TOTAL = reuse_or_create(
    Counter,
    'omi_episode_moment_tokens_total',
    'Tokens spent by the per-moment incremental update (kind=input|output).',
    ['kind'],
)
EPISODE_MOMENT_COST_USD_TOTAL = reuse_or_create(
    Counter,
    'omi_episode_moment_cost_usd_total',
    'Estimated USD for per-moment updates at the gpt-5-nano rate card; the gateway ledger is authoritative.',
    [],
)
EPISODE_MOMENT_LATENCY_SECONDS = reuse_or_create(
    Histogram,
    'omi_episode_moment_update_latency_seconds',
    'Model latency of the per-moment incremental update.',
    ['outcome'],
    buckets=(0.25, 0.5, 1, 2, 3, 5, 8, 13, 20),
)
EPISODE_CLOSED_TOTAL = reuse_or_create(
    Counter, 'omi_episode_closed_total', 'Episodes closed, by close reason.', ['reason']
)
CLOSE_CONFLICT_REASONS = frozenset({'recorded_window_overlap', 'recorded_window_incomplete', 'state_version_changed'})
F_JOIN_ARMS = frozenset({'f', 'control'})
EPISODE_CLOSED_MEMBERS = reuse_or_create(
    Histogram,
    'omi_episode_closed_members',
    'Member conversations per closed episode, by episode-join variant arm (f|control).',
    ['arm'],
    buckets=(1, 2, 3, 4, 6, 8, 12, 20, 40),
)
EPISODE_CLOSED_SPAN_SECONDS = reuse_or_create(
    Histogram,
    'omi_episode_closed_span_seconds',
    'Recorded span of a closed episode in seconds, by episode-join variant arm (f|control).',
    ['arm'],
    buckets=(60, 300, 900, 1800, 3600, 5400, 7200, 10800, 14400),
)
EPISODE_CLOSE_CONFLICT_TOTAL = reuse_or_create(
    Counter, 'omi_episode_close_conflict_total', 'Lazy episode closes deferred by a storage conflict.', ['reason']
)
EPISODE_PROVISIONAL_ITEMS_TOTAL = reuse_or_create(
    Counter,
    'omi_episode_provisional_items_total',
    'Provisional items at reconciliation: kept (became a saved task), dropped, dismissed by the user.',
    ['outcome'],
)
EPISODE_WRAPUP_LATENCY_SECONDS = reuse_or_create(
    Histogram,
    'omi_episode_wrapup_latency_seconds',
    'Seconds from the end of an episode-closing conversation to its finished notes.',
    ['reason'],
    buckets=(5, 15, 30, 60, 120, 300, 600, 1200, 3600),
)
EPISODE_BOUNDARY_TOTAL = reuse_or_create(
    Counter,
    'omi_episode_boundary_total',
    'Moment boundary decisions against the open episode.',
    ['outcome'],
)
EPISODE_F_GATE_TOTAL = reuse_or_create(
    Counter,
    'omi_episode_f_gate_total',
    'Variant F candidate privacy gate refusals by first failing condition. Never labeled by uid.',
    ['reason'],
)
EPISODE_F_FALLBACK_TOTAL = reuse_or_create(
    Counter,
    'omi_episode_f_fallback_total',
    'Variant F fallbacks by bounded call site. Existing fallback reasons are unchanged.',
    ['site'],
)
EPISODE_MOMENTS_SKIPPED_NO_CLIENT_TOTAL = reuse_or_create(
    Counter,
    'omi_episode_moments_skipped_no_client_total',
    'Admitted moments, finalization tails and conversation attaches skipped because the user has no client that called /v1/episodes.',
    ['trigger'],
)
EPISODE_LIVE_SESSIONS_TOTAL = reuse_or_create(
    Counter,
    'omi_episode_live_sessions_total',
    'Admitted live conversations at their first speech, by whether a capable client was seen (true|false).',
    ['client_seen'],
)
COMPOSE_OUTCOMES = frozenset(
    {
        'settling',
        'composed',
        'composed_single',
        'unchanged',
        'leased',
        'waiting',
        'live',
        'empty',
        'no_episode',
        'superseded',
        'kept_pending',
        'stale',
        'backoff',
        'conflict',
        'disabled',
        'error',
    }
)
# What asked for the compose. Bounded, never a uid: a close, a Home/page read, a
# member finalize, or the settle timer draining deferred work.
COMPOSE_TRIGGERS = frozenset({'close', 'read', 'member_final', 'settle'})
# Paid model calls inside a compose: the run's trigger, plus the one repair retry.
COMPOSE_CALL_TRIGGERS = COMPOSE_TRIGGERS | {'repair'}
COMPOSE_CALL_OUTCOMES = frozenset({'ok', 'parse_error', 'no_sections', 'error'})
EPISODE_COMPOSE_TOTAL = reuse_or_create(
    Counter,
    'omi_episode_compose_total',
    'Closed-episode composer runs by outcome and trigger. Never labeled by uid.',
    ['outcome', 'trigger'],
)
EPISODE_COMPOSE_SECONDS = reuse_or_create(
    Histogram,
    'omi_episode_compose_seconds',
    'Wall time of a composer run, including its model call, by outcome and trigger.',
    ['outcome', 'trigger'],
    buckets=(0.1, 0.5, 1, 3, 5, 8, 13, 20, 30, 60, 90),
)
EPISODE_COMPOSE_CALLS_TOTAL = reuse_or_create(
    Counter,
    'omi_episode_compose_calls_total',
    'Paid composer model calls by trigger (close|read|member_final|settle|repair) and outcome. Never labeled by uid.',
    ['trigger', 'outcome'],
)
COMPOSE_MODES = frozenset({'full', 'notes_first'})
EPISODE_COMPOSE_INPUT_TOKENS_TOTAL = reuse_or_create(
    Counter,
    'omi_episode_compose_input_tokens_total',
    'Input tokens spent by closed-episode composes, by prompt mode (full|notes_first). Never labeled by uid.',
    ['mode'],
)
EPISODE_COMPOSE_OUTPUT_TOKENS_TOTAL = reuse_or_create(
    Counter,
    'omi_episode_compose_output_tokens_total',
    'Reported billed output tokens on every composer reply, including terminal parse failures.',
    ['mode'],
)
EPISODE_COMPOSE_TOOL_CALLS = reuse_or_create(
    Histogram,
    'omi_episode_compose_tool_calls',
    'Transcript-excerpt tool calls per closed-episode compose, by prompt mode (full|notes_first).',
    ['mode'],
    buckets=(0, 1, 2, 3, 4, 5),
)
COMPOSE_SKIP_REASONS = frozenset({'evidence_unchanged', 'late_deferred'})
EPISODE_COMPOSE_TRIGGER_SKIPPED_TOTAL = reuse_or_create(
    Counter,
    'omi_episode_compose_trigger_skipped_total',
    'Composer triggers skipped before scheduling or paying, by bounded reason. Never labeled by uid.',
    ['reason'],
)
HOME_MEMBER_OUTCOMES = frozenset({'shown', 'hidden_below_floor'})
EPISODE_HOME_MEMBERS_TOTAL = reuse_or_create(
    Counter,
    'omi_episode_home_members_total',
    'Conversations considered for Home list rows by outcome. Never labeled by uid.',
    ['outcome'],
)
CLIENT_CHANNELS = frozenset({'beta', 'store', 'unknown'})
CLIENT_REQUEST_OUTCOMES = frozenset({'admitted', 'channel_closed', 'not_admitted'})
EPISODE_CLIENT_REQUESTS_TOTAL = reuse_or_create(
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
        for reason in CLOSE_CONFLICT_REASONS | {'other'}:
            EPISODE_CLOSE_CONFLICT_TOTAL.labels(reason=_label(reason, CLOSE_CONFLICT_REASONS))
        for outcome in PROVISIONAL_OUTCOMES:
            EPISODE_PROVISIONAL_ITEMS_TOTAL.labels(outcome=_label(outcome, PROVISIONAL_OUTCOMES))
        for outcome in BOUNDARY_OUTCOMES:
            EPISODE_BOUNDARY_TOTAL.labels(outcome=_label(outcome, BOUNDARY_OUTCOMES))
        for reason in F_GATE_REASONS:
            EPISODE_F_GATE_TOTAL.labels(reason=_label(reason, F_GATE_REASONS))
        for site in F_FALLBACK_SITES:
            EPISODE_F_FALLBACK_TOTAL.labels(site=_label(site, F_FALLBACK_SITES))
        for outcome in MOMENT_OUTCOMES:
            EPISODE_MOMENT_LATENCY_SECONDS.labels(outcome=_label(outcome, MOMENT_OUTCOMES))
        for reason in CLOSE_REASON_LABELS:
            EPISODE_WRAPUP_LATENCY_SECONDS.labels(reason=_label(reason, CLOSE_REASON_LABELS))
        for seen in ('true', 'false'):
            EPISODE_LIVE_SESSIONS_TOTAL.labels(client_seen=seen)
        for arm in F_JOIN_ARMS:
            EPISODE_CLOSED_MEMBERS.labels(arm=arm)
            EPISODE_CLOSED_SPAN_SECONDS.labels(arm=arm)
        for outcome in COMPOSE_OUTCOMES:
            for trigger in COMPOSE_TRIGGERS:
                EPISODE_COMPOSE_TOTAL.labels(outcome=_label(outcome, COMPOSE_OUTCOMES), trigger=trigger)
                EPISODE_COMPOSE_SECONDS.labels(outcome=_label(outcome, COMPOSE_OUTCOMES), trigger=trigger)
        for trigger in COMPOSE_CALL_TRIGGERS:
            for outcome in COMPOSE_CALL_OUTCOMES:
                EPISODE_COMPOSE_CALLS_TOTAL.labels(
                    trigger=_label(trigger, COMPOSE_CALL_TRIGGERS), outcome=_label(outcome, COMPOSE_CALL_OUTCOMES)
                )
        for mode in COMPOSE_MODES:
            EPISODE_COMPOSE_INPUT_TOKENS_TOTAL.labels(mode=_label(mode, COMPOSE_MODES))
            EPISODE_COMPOSE_TOOL_CALLS.labels(mode=_label(mode, COMPOSE_MODES))
        for reason in COMPOSE_SKIP_REASONS:
            EPISODE_COMPOSE_TRIGGER_SKIPPED_TOTAL.labels(reason=_label(reason, COMPOSE_SKIP_REASONS))
        for outcome in HOME_MEMBER_OUTCOMES:
            EPISODE_HOME_MEMBERS_TOTAL.labels(outcome=_label(outcome, HOME_MEMBER_OUTCOMES))
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


def record_closed_size(arm: str, members: int, span_seconds: float | None) -> None:
    try:
        label = _label(arm, F_JOIN_ARMS)
        EPISODE_CLOSED_MEMBERS.labels(arm=label).observe(max(0, int(members)))
        if span_seconds is not None and span_seconds >= 0:
            EPISODE_CLOSED_SPAN_SECONDS.labels(arm=label).observe(span_seconds)
    except Exception:
        pass


def record_close_conflict(reason: str) -> str:
    label = _label(reason, CLOSE_CONFLICT_REASONS)
    try:
        EPISODE_CLOSE_CONFLICT_TOTAL.labels(reason=_label(reason, CLOSE_CONFLICT_REASONS)).inc()
    except Exception:
        pass
    return label


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


def record_f_gate(reason: str) -> None:
    try:
        EPISODE_F_GATE_TOTAL.labels(reason=_label(reason, F_GATE_REASONS)).inc()
    except Exception:
        pass


def record_f_fallback(site: str) -> None:
    try:
        EPISODE_F_FALLBACK_TOTAL.labels(site=_label(site, F_FALLBACK_SITES)).inc()
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


def record_compose_trigger_skipped(reason: str) -> None:
    try:
        EPISODE_COMPOSE_TRIGGER_SKIPPED_TOTAL.labels(reason=_label(reason, COMPOSE_SKIP_REASONS)).inc()
    except Exception:
        pass


def record_compose(outcome: str, seconds: float, trigger: str = 'close') -> None:
    try:
        trigger_label = _label(trigger, COMPOSE_TRIGGERS)
        EPISODE_COMPOSE_TOTAL.labels(outcome=_label(outcome, COMPOSE_OUTCOMES), trigger=trigger_label).inc()
        EPISODE_COMPOSE_SECONDS.labels(outcome=_label(outcome, COMPOSE_OUTCOMES), trigger=trigger_label).observe(
            max(0.0, seconds)
        )
    except Exception:
        pass


def record_compose_call(trigger: str, outcome: str) -> None:
    """One paid composer model call, including the repair retry."""
    try:
        EPISODE_COMPOSE_CALLS_TOTAL.labels(
            trigger=_label(trigger, COMPOSE_CALL_TRIGGERS), outcome=_label(outcome, COMPOSE_CALL_OUTCOMES)
        ).inc()
    except Exception:
        pass


def record_compose_reply(mode: str, input_tokens: int, output_tokens: int) -> None:
    """Reported billed usage on every reply, even if parse/repair later fails."""
    try:
        label = _label(mode, COMPOSE_MODES)
        EPISODE_COMPOSE_INPUT_TOKENS_TOTAL.labels(mode=label).inc(max(0, input_tokens))
        EPISODE_COMPOSE_OUTPUT_TOKENS_TOTAL.labels(mode=label).inc(max(0, output_tokens))
    except Exception:
        pass


def record_compose_tools(mode: str, tool_calls: int) -> None:
    try:
        EPISODE_COMPOSE_TOOL_CALLS.labels(mode=_label(mode, COMPOSE_MODES)).observe(max(0, int(tool_calls)))
    except Exception:
        pass


def record_home_members(*, shown: int, hidden: int) -> None:
    """Aggregate only, so the fleet effect of the below-floor hide stays visible."""
    try:
        if shown:
            EPISODE_HOME_MEMBERS_TOTAL.labels(outcome=_label('shown', HOME_MEMBER_OUTCOMES)).inc(shown)
        if hidden:
            EPISODE_HOME_MEMBERS_TOTAL.labels(outcome=_label('hidden_below_floor', HOME_MEMBER_OUTCOMES)).inc(hidden)
    except Exception:
        pass


EPISODE_BATCH_PENDING_OVERDUE_READS_TOTAL = reuse_or_create(
    Counter,
    'omi_episode_batch_pending_overdue_reads_total',
    'Home member observations without a batch projection past the stamped 2h deadline. Not unique members.',
    [],
)


def record_batch_pending_overdue() -> None:
    try:
        EPISODE_BATCH_PENDING_OVERDUE_READS_TOTAL.inc()
    except Exception:
        pass
