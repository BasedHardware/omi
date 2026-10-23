"""Row evaluators for contract (j). Pure: evidence dicts in, ``RowResult`` out.

Evidence shapes (all aggregates; ``None`` or a missing key means unmeasured):

``corpus`` (rows 1 and 2, corpus half), written by ``testing/quality_corpus/score.py``::

    {"corpus_minutes": 72.4,
     "pipelines": {"batch":  {"wer": {"errors": 812, "reference_words": 10400, "wer": 0.078},
                              "speaker": {"words": 9100, "correct_1to1": 8400}},
                   "legacy": {...same...}},
     "baseline": {"speaker_accuracy": 0.921, "source": "main@<sha>"}}

Each pipeline also carries ``missing_units`` and ``scored_wer_minutes`` (WER audio
that had output and was scored). Rows 1 and 2 accept a corpus only when
``pinned`` is true and no pipeline is missing a unit; row 1's 60-minute floor is
on scored audio, not the index.

``replay`` (rows 1b and 2, replay half), computed in RAM by
``parity_gate.replay_aggregates`` from batch/legacy word pairs.

``aggregates`` (rows 3, 4, 5, 7, 8): see the ``*_KEYS`` tuples below. On the
prod-shadow surface ``prod_shadow.from_fleet_gate_sample`` fills rows 3 and 4
from the workspace fleet gate's JSON line.

``cost`` (row 6)::

    {"steady_hours": 2.3,
     "leases_per_min_per_node": 47.1,           # staging, prod per-node config
     "batch":  {"gpu_node_hours": .., "gpu_usd_per_hour": .., "vendor_stt_usd": .., "cpu_worker_usd": .., "audio_hours": ..},
     "legacy": {...same...}}
"""

from __future__ import annotations

import math
from typing import Any, Mapping

from scripts.parity.report_schema import (
    ROW_SURFACES,
    THRESHOLDS,
    ParityReason as R,
    RowResult,
    Status,
    Surface,
    Thresholds,
)


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def finite(value: Any) -> float | None:
    return _num(value)


def _count(mapping: Mapping[str, Any] | None, key: str) -> int | None:
    if not mapping:
        return None
    value = _num(mapping.get(key))
    if value is None or value < 0 or value != int(value):
        return None
    return int(value)


def _result(row, status, reason, surface, measured=None, sample=None):
    return RowResult(row, status, reason, surface, measured or {}, sample or {})


def _not_applicable(row: str, surface: Surface) -> RowResult | None:
    if surface not in ROW_SURFACES[row]:
        return _result(row, Status.NOT_APPLICABLE, R.PASS, surface)
    return None


def _missing(row: str, surface: Surface) -> RowResult:
    return _result(row, Status.PENDING, R.INPUT_MISSING, surface)


def corpus_defect(corpus: Mapping[str, Any]) -> dict[str, Any] | None:
    """Why a corpus scores file is not evidence, or None when it is. Absent fields fail closed.

    Scores from an unpinned corpus (fetch-by-checksum, F6) are not evidence, and
    neither are scores where a pipeline is missing unit outputs: a partial copy
    would score only the remainder.
    """
    if corpus.get('pinned') is not True:
        return {'pinned': corpus.get('pinned')}
    pipelines = corpus.get('pipelines') or {}
    missing = {name: _count(side, 'missing_units') for name, side in pipelines.items() if isinstance(side, Mapping)}
    if not missing or any(v != 0 for v in missing.values()):
        return {'missing_units': missing}
    return None


# --- Row 1: transcript accuracy on the corpus -------------------------------------------------


def row_1(corpus: Mapping[str, Any] | None, surface: Surface, t: Thresholds = THRESHOLDS) -> RowResult:
    if (na := _not_applicable('1', surface)) is not None:
        return na
    if not corpus:
        return _missing('1', surface)
    if (defect := corpus_defect(corpus)) is not None:
        return _result('1', Status.PENDING, R.INPUT_INVALID, surface, defect)
    pipelines = corpus.get('pipelines') or {}
    scored = [_num((pipelines.get(name) or {}).get('scored_wer_minutes')) for name in ('batch', 'legacy')]
    batch = (pipelines.get('batch') or {}).get('wer') or {}
    legacy = (pipelines.get('legacy') or {}).get('wer') or {}
    b_words, l_words = _count(batch, 'reference_words'), _count(legacy, 'reference_words')
    b_err, l_err = _count(batch, 'errors'), _count(legacy, 'errors')
    if None in (*scored, b_words, l_words, b_err, l_err):
        return _result('1', Status.PENDING, R.INPUT_INVALID, surface)
    minutes = min(scored)  # type: ignore[type-var]
    sample = {'scored_wer_minutes': minutes, 'min_corpus_minutes': t.wer_min_corpus_minutes}
    if minutes < t.wer_min_corpus_minutes or not b_words or not l_words:
        return _result('1', Status.PENDING, R.SAMPLE_BELOW_MINIMUM, surface, sample=sample)
    wer_b, wer_l = b_err / b_words, l_err / l_words
    delta_pp = (wer_b - wer_l) * 100.0
    measured = {
        'wer_batch': round(wer_b, 5),
        'wer_legacy': round(wer_l, 5),
        'delta_pp': round(delta_pp, 3),
        'limit_pp': t.wer_delta_pp,
    }
    if round(delta_pp, 9) > t.wer_delta_pp:  # a boundary value is inside the threshold
        return _result('1', Status.FAIL, R.WER_DELTA_OVER_LIMIT, surface, measured, sample)
    return _result('1', Status.PASS, R.PASS, surface, measured, sample)


# --- Row 1b: per-conversation agreement on the staging replay ---------------------------------


def row_1b(replay: Mapping[str, Any] | None, surface: Surface, t: Thresholds = THRESHOLDS) -> RowResult:
    if (na := _not_applicable('1b', surface)) is not None:
        return na
    if not replay:
        return _missing('1b', surface)
    n = _count(replay, 'conversations')
    med = _num(replay.get('agreement_wer_median'))
    unreviewed = _count(replay, 'outliers_unreviewed')
    if n is None or unreviewed is None:
        return _result('1b', Status.PENDING, R.INPUT_INVALID, surface)
    sample = {'conversations': n, 'min_conversations': t.agreement_min_conversations}
    measured = {
        'agreement_wer_median': None if med is None else round(med, 5),
        'agreement_wer_p95': replay.get('agreement_wer_p95'),
        'outliers_over_limit': replay.get('outliers_over_limit'),
        'outliers_reviewed': replay.get('outliers_reviewed'),
        'outliers_unreviewed': unreviewed,
        'median_limit': t.agreement_median_max,
        'outlier_limit': t.agreement_outlier_max,
    }
    # Hard failures are decisive at any sample size; PASS needs the minimum sample.
    if unreviewed:
        return _result('1b', Status.FAIL, R.AGREEMENT_OUTLIER_UNREVIEWED, surface, measured, sample)
    if n < t.agreement_min_conversations or med is None:
        return _result('1b', Status.PENDING, R.SAMPLE_BELOW_MINIMUM, surface, measured, sample)
    if med > t.agreement_median_max:
        return _result('1b', Status.FAIL, R.AGREEMENT_MEDIAN_OVER_LIMIT, surface, measured, sample)
    return _result('1b', Status.PASS, R.PASS, surface, measured, sample)


# --- Row 2: speaker labels (corpus accuracy + replay owner agreement) -------------------------


def row_2(corpus, replay, surface: Surface, t: Thresholds = THRESHOLDS) -> RowResult:
    if (na := _not_applicable('2', surface)) is not None:
        return na
    if not corpus and not replay:
        return _missing('2', surface)
    measured: dict[str, Any] = {'drop_limit_pp': t.speaker_accuracy_drop_pp, 'owner_limit': t.owner_agreement_min}
    sample: dict[str, Any] = {'min_owner_conversations': t.owner_agreement_min_conversations}
    pending_reason = None
    if surface is Surface.PROD_SHADOW:
        # Prod shadow has no corpus half: owner agreement on David's own recordings only.
        corpus = None
    elif not corpus:
        pending_reason = R.INPUT_MISSING
    elif (defect := corpus_defect(corpus)) is not None:
        corpus, pending_reason = None, R.INPUT_INVALID
        measured['corpus_defect'] = defect
    # Corpus half: batch accuracy >= the frozen main baseline - 1pp. The legacy score is never
    # a stand-in for a missing baseline: a regression both pipelines share would cancel out.
    speaker = ((corpus or {}).get('pipelines') or {}).get('batch', {}).get('speaker') or {}
    words, correct = _count(speaker, 'words'), _count(speaker, 'correct_1to1')
    baseline = _num(((corpus or {}).get('baseline') or {}).get('speaker_accuracy'))
    if corpus is None:
        pass
    elif not words or correct is None or baseline is None:
        pending_reason = pending_reason or R.INPUT_MISSING
    else:
        accuracy = correct / words
        drop_pp = (baseline - accuracy) * 100.0
        measured.update(speaker_accuracy=round(accuracy, 5), baseline=round(baseline, 5), drop_pp=round(drop_pp, 3))
        sample['corpus_words'] = words
        if round(drop_pp, 9) > t.speaker_accuracy_drop_pp:
            return _result('2', Status.FAIL, R.SPEAKER_ACCURACY_REGRESSED, surface, measured, sample)
    # Replay half: owner-word agreement >= 97% over >= 200 conversations.
    conversations = _count(replay, 'owner_conversations') if replay else None
    scored, agree = (
        (_count(replay, 'owner_scored_words'), _count(replay, 'owner_agree_words')) if replay else (None, None)
    )
    if conversations is None or scored is None or agree is None:
        pending_reason = pending_reason or R.INPUT_MISSING
    else:
        sample['owner_conversations'] = conversations
        rate = agree / scored if scored else None
        measured['owner_agreement'] = None if rate is None else round(rate, 5)
        if rate is not None and conversations >= t.owner_agreement_min_conversations and rate < t.owner_agreement_min:
            return _result('2', Status.FAIL, R.OWNER_AGREEMENT_BELOW_LIMIT, surface, measured, sample)
        if conversations < t.owner_agreement_min_conversations or rate is None:
            pending_reason = pending_reason or R.SAMPLE_BELOW_MINIMUM
    if pending_reason:
        return _result('2', Status.PENDING, pending_reason, surface, measured, sample)
    return _result('2', Status.PASS, R.PASS, surface, measured, sample)


# --- Row 3: first-summary latency -------------------------------------------------------------

ROW3_KEYS = (
    'first_summary_dispatch_measured_count',
    'first_summary_dispatch_breaches_over_121s',
    'first_summary_dispatch_max_seconds',
    'first_summary_completion_p95_seconds',
    'accept_to_summary_p95_seconds',
    'legacy_accept_to_summary_p95_seconds',
)


def row_3(agg: Mapping[str, Any] | None, surface: Surface, t: Thresholds = THRESHOLDS) -> RowResult:
    if (na := _not_applicable('3', surface)) is not None:
        return na
    if not agg:
        return _missing('3', surface)
    dispatches = _count(agg, 'first_summary_dispatch_measured_count')
    breaches = _count(agg, 'first_summary_dispatch_breaches_over_121s')
    completion = _num(agg.get('first_summary_completion_p95_seconds'))
    accept = _num(agg.get('accept_to_summary_p95_seconds'))
    legacy = _num(agg.get('legacy_accept_to_summary_p95_seconds'))
    measured = {
        'dispatch_breaches_over_121s': breaches,
        'completion_p95_seconds': completion,
        'accept_to_summary_p95_seconds': accept,
        'legacy_accept_to_summary_p95_seconds': legacy,
        'completion_p95_limit_seconds': t.first_summary_completion_p95_seconds,
        'accept_slack_seconds': t.accept_to_summary_p95_slack_seconds,
    }
    sample = {'dispatches': dispatches, 'min_dispatches': t.first_summary_min_dispatches}
    if dispatches is None or breaches is None:
        return _result('3', Status.PENDING, R.INPUT_INVALID, surface, measured, sample)
    if dispatches and _num(agg.get('first_summary_dispatch_max_seconds')) is None:
        # Without the measured max the strict 121s limit cannot be checked; a zero count is not proof.
        return _result('3', Status.PENDING, R.INPUT_INVALID, surface, measured, sample)
    if breaches:
        return _result('3', Status.FAIL, R.FIRST_SUMMARY_DISPATCH_BREACH, surface, measured, sample)
    if dispatches < t.first_summary_min_dispatches:
        return _result('3', Status.PENDING, R.SAMPLE_BELOW_MINIMUM, surface, measured, sample)
    if completion is None or accept is None or legacy is None:
        return _result('3', Status.PENDING, R.INPUT_MISSING, surface, measured, sample)
    if completion > t.first_summary_completion_p95_seconds:
        return _result('3', Status.FAIL, R.FIRST_SUMMARY_COMPLETION_P95, surface, measured, sample)
    if accept > legacy + t.accept_to_summary_p95_slack_seconds:
        return _result('3', Status.FAIL, R.ACCEPT_TO_SUMMARY_P95, surface, measured, sample)
    return _result('3', Status.PASS, R.PASS, surface, measured, sample)


# --- Row 4: completeness ----------------------------------------------------------------------

ROW4_KEYS = (
    'admitted_units',
    'stuck_jobs_over_30m',
    'obligations_over_15m',
    'terminal_unrecovered_speech_fraction',
    'conversation_count_batch',
    'conversation_count_legacy',
    'duration_seconds_batch',
    'duration_seconds_legacy',
    'systematic_difference',  # {"count": int, "duration_seconds": float, "explanation_ref": str}
)


def _drift(batch: float, legacy: float, adjust: float) -> float | None:
    if legacy <= 0:
        return None if batch - adjust else 0.0
    return abs((batch - adjust) - legacy) / legacy


def row_4(agg: Mapping[str, Any] | None, surface: Surface, t: Thresholds = THRESHOLDS) -> RowResult:
    if (na := _not_applicable('4', surface)) is not None:
        return na
    if not agg:
        return _missing('4', surface)
    stuck = _count(agg, 'stuck_jobs_over_30m')
    obligations = _count(agg, 'obligations_over_15m')
    speech = _num(agg.get('terminal_unrecovered_speech_fraction'))
    admitted = _count(agg, 'admitted_units')
    measured: dict[str, Any] = {
        'stuck_jobs_over_30m': stuck,
        'obligations_over_15m': obligations,
        'terminal_unrecovered_speech_fraction': speech,
        'terminal_unrecovered_speech_limit': t.terminal_unrecovered_speech_max,
        'tolerance': t.count_duration_tolerance,
    }
    sample = {'admitted_units': admitted}
    if stuck is None or obligations is None:
        return _result('4', Status.PENDING, R.INPUT_INVALID, surface, measured, sample)
    if stuck:
        return _result('4', Status.FAIL, R.STUCK_JOB_OVER_30M, surface, measured, sample)
    if obligations:
        return _result('4', Status.FAIL, R.OBLIGATION_OVER_15M, surface, measured, sample)
    if speech is not None and speech > t.terminal_unrecovered_speech_max:
        return _result('4', Status.FAIL, R.TERMINAL_UNRECOVERED_SPEECH, surface, measured, sample)
    if not admitted:
        return _result('4', Status.PENDING, R.SAMPLE_BELOW_MINIMUM, surface, measured, sample)
    if speech is None:
        return _result('4', Status.PENDING, R.INPUT_MISSING, surface, measured, sample)
    counts = [
        _num(agg.get(k))
        for k in (
            'conversation_count_batch',
            'conversation_count_legacy',
            'duration_seconds_batch',
            'duration_seconds_legacy',
        )
    ]
    if None in counts:
        return _result('4', Status.PENDING, R.INPUT_MISSING, surface, measured, sample)
    cb, cl, db, dl = counts  # type: ignore[misc]
    systematic = agg.get('systematic_difference') or {}
    adj_count = _num(systematic.get('count')) or 0.0
    adj_duration = _num(systematic.get('duration_seconds')) or 0.0
    if (adj_count or adj_duration) and not systematic.get('explanation_ref'):
        # A subtracted difference must be documented in the report with its own count (contract (j)).
        return _result('4', Status.PENDING, R.INPUT_INVALID, surface, measured, sample)
    count_drift, duration_drift = _drift(cb, cl, adj_count), _drift(db, dl, adj_duration)
    measured.update(
        count_drift=None if count_drift is None else round(count_drift, 5),
        duration_drift=None if duration_drift is None else round(duration_drift, 5),
        systematic_difference={
            'count': adj_count,
            'duration_seconds': adj_duration,
            'explanation_ref': systematic.get('explanation_ref'),
        },
    )
    if count_drift is None or count_drift > t.count_duration_tolerance:
        return _result('4', Status.FAIL, R.COUNT_DRIFT, surface, measured, sample)
    if duration_drift is None or duration_drift > t.count_duration_tolerance:
        return _result('4', Status.FAIL, R.DURATION_DRIFT, surface, measured, sample)
    return _result('4', Status.PASS, R.PASS, surface, measured, sample)


# --- Row 5: zero lost recordings --------------------------------------------------------------

ROW5_KEYS = ('accepted_content_ids', 'receipted_or_terminal_content_ids', 'lost_content_ids')


def row_5(agg: Mapping[str, Any] | None, surface: Surface, t: Thresholds = THRESHOLDS) -> RowResult:
    """accepted − (projection receipts ∪ explicit terminal dispositions) = 0, exactly.

    The collector does the set arithmetic on content ids in memory and hands
    only the three counts here. ``lost`` must equal accepted − accounted; any
    inconsistency is treated as unmeasured, never as zero.
    """
    if (na := _not_applicable('5', surface)) is not None:
        return na
    if not agg:
        return _missing('5', surface)
    accepted = _count(agg, 'accepted_content_ids')
    accounted = _count(agg, 'receipted_or_terminal_content_ids')
    lost = _count(agg, 'lost_content_ids')
    measured = {'accepted': accepted, 'accounted': accounted, 'lost': lost}
    if accepted is None or accounted is None or lost is None or lost != accepted - accounted or accounted > accepted:
        return _result('5', Status.PENDING, R.INPUT_INVALID, surface, measured)
    if lost:
        return _result('5', Status.FAIL, R.LOST_RECORDINGS, surface, measured)
    if not accepted:
        return _result('5', Status.PENDING, R.SAMPLE_BELOW_MINIMUM, surface, measured)
    return _result('5', Status.PASS, R.PASS, surface, measured)


# --- Row 6: cost per audio-hour and throughput ------------------------------------------------


def usd_per_audio_hour(side: Mapping[str, Any] | None) -> float | None:
    """(GPU node-hours × list $/h + vendor STT $ + CPU workers $) ÷ captured audio-hours."""
    if not side:
        return None
    parts = [_num(side.get(k)) for k in ('gpu_node_hours', 'gpu_usd_per_hour', 'vendor_stt_usd', 'cpu_worker_usd')]
    hours = _num(side.get('audio_hours'))
    if None in parts or hours is None or hours <= 0:
        return None
    node_hours, rate, vendor, cpu = parts  # type: ignore[misc]
    return (node_hours * rate + vendor + cpu) / hours


def max_supported_percent(leases_per_min_per_node: float | None, t: Thresholds = THRESHOLDS) -> float | None:
    """Ramp percent the measured per-node throughput carries on ``max_nodes`` nodes."""
    if leases_per_min_per_node is None or leases_per_min_per_node <= 0:
        return None
    return min(100.0, 100.0 * t.max_nodes * leases_per_min_per_node / t.legacy_leases_per_min_mean)


def row_6(cost: Mapping[str, Any] | None, surface: Surface, t: Thresholds = THRESHOLDS) -> RowResult:
    if (na := _not_applicable('6', surface)) is not None:
        return na
    if not cost:
        return _missing('6', surface)
    hours = _num(cost.get('steady_hours'))
    sample = {'steady_hours': hours, 'min_steady_hours': t.cost_min_steady_hours}
    if hours is None or hours < t.cost_min_steady_hours:
        return _result('6', Status.PENDING, R.SAMPLE_BELOW_MINIMUM, surface, sample=sample)
    if surface is Surface.STAGING:
        # Staging measures throughput at prod's per-node configuration.
        rate = _num(cost.get('leases_per_min_per_node'))
        supported = max_supported_percent(rate, t)
        measured = {
            'leases_per_min_per_node': rate,
            'floor': t.leases_per_min_per_node_floor,
            'max_nodes': t.max_nodes,
            'max_supported_percent': supported,
        }
        if rate is None:
            return _result('6', Status.PENDING, R.INPUT_MISSING, surface, measured, sample)
        if rate <= 0 or supported is None:
            # A zero or negative rate carries no ramp percent: never a PASS without a numeric cap.
            return _result('6', Status.PENDING, R.INPUT_INVALID, surface, measured, sample)
        # Contract (j): below the floor the row still PASSes, capped at the percent the measured
        # throughput carries (the report's ``max_supported_percent``, printed before the terminal
        # line); legacy dark then waits for David's fifth-node decision. ``capped`` records it.
        measured['capped'] = rate < t.leases_per_min_per_node_floor
        return _result('6', Status.PASS, R.PASS, surface, measured, sample)
    batch, legacy = usd_per_audio_hour(cost.get('batch')), usd_per_audio_hour(cost.get('legacy'))
    measured = {
        'batch_usd_per_audio_hour': None if batch is None else round(batch, 5),
        'legacy_usd_per_audio_hour': None if legacy is None else round(legacy, 5),
    }
    if batch is None or legacy is None:
        return _result('6', Status.PENDING, R.INPUT_MISSING, surface, measured, sample)
    if batch > legacy:
        return _result('6', Status.FAIL, R.COST_ABOVE_LEGACY, surface, measured, sample)
    return _result('6', Status.PASS, R.PASS, surface, measured, sample)


# --- Rows 7 and 8: privacy and ordering -------------------------------------------------------


def _zero_row(row, key, reason, agg, surface):
    if (na := _not_applicable(row, surface)) is not None:
        return na
    if not agg:
        return _missing(row, surface)
    value, considered = _count(agg, key), _count(agg, key.replace('violations', 'units_considered'))
    measured = {key: value}
    if value is None:
        return _result(row, Status.PENDING, R.INPUT_INVALID, surface, measured)
    if value:
        return _result(row, Status.FAIL, reason, surface, measured)
    if not considered:
        return _result(row, Status.PENDING, R.SAMPLE_BELOW_MINIMUM, surface, measured, {'units_considered': considered})
    return _result(row, Status.PASS, R.PASS, surface, measured, {'units_considered': considered})


def row_7(agg, surface: Surface) -> RowResult:
    """Units paid or projected for privacy-fenced or deleted owners = 0."""
    return _zero_row('7', 'privacy_violations', R.PRIVACY_VIOLATION, agg, surface)


def row_8(agg, surface: Surface) -> RowResult:
    """Per-owner commit order equals capture order (OrderedMerge): 0 violations."""
    return _zero_row('8', 'ordering_violations', R.ORDERING_VIOLATION, agg, surface)
