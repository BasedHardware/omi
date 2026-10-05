"""Offline, independent-snapshot comparison of old and overlap-aware predecessors.

Input is schema_version=1, timezone (IANA), conversations (decoded cards), and
evaluations. Each evaluation names conversation_id, preceding_ids (the exact
newest-first, at-most-six query result), capture_end, uid_allowed (booleans), mode (merge or shadow),
and optional scores [{candidate_id, question_version, state_sha256, p_same}].
Cards must be snapshots of decision-time inputs, not subsequently merged rows.
No services, model calls, writes, hypothetical chain updates, or user-data logs.
A missing score is indeterminate, never a predicted keep or merge. Pending
refresh in merge mode is also indeterminate: persistence cannot be replayed.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.conversation_smart_merge import (
    MERGE_THRESHOLD,
    OVERLAP_CAPTURE_FIELDS,
    PRECEDING_METADATA_FIELDS,
    PRECEDING_QUERY_LIMIT,
    QUESTION_VERSION,
    smart_merge_flatten_enabled,
)
from utils.conversations.smart_merge_policy import (
    DECISION_FIELD,
    SkipReason,
    check_pair,
    fragment_of,
    fragment_segments,
    ledger_fragments,
    new_conversation_skip,
    predecessor_status_skip,
    refresh_owed,
    select_predecessor,
    stretch_before,
)
from utils.conversations.smart_merge_state import build_state, state_sha256

_TIME_FIELDS = frozenset(
    {'created_at', 'started_at', 'finished_at', 'decided_at', 'last_merged_at', 'merged_at', 'until'}
)
_STATUSES = frozenset({'in_progress', 'processing', 'merging', 'completed', 'failed'})


def _decode(value: Any, field: str = '') -> Any:
    if field in _TIME_FIELDS and value is not None:
        if not isinstance(value, str):
            raise ValueError(f'{field} must be an ISO-8601 timestamp with timezone')
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError(f'{field} requires a timezone')
        return parsed
    if isinstance(value, dict):
        return {key: _decode(item, key) for key, item in value.items()}
    if isinstance(value, list):
        return [_decode(item) for item in value]
    return value


def _segments(row: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    segments = row.get('transcript_segments')
    if not isinstance(segments, list) or any(not isinstance(item, dict) for item in segments):
        raise ValueError('selected cards require decoded transcript_segments lists')
    for item in segments:
        for key in ('start', 'end'):
            number = item.get(key)
            if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number):
                raise ValueError('transcript offsets must be finite numbers')
        if item['start'] > item['end'] or not isinstance(item.get('text'), str):
            raise ValueError('transcript segments require ordered offsets and text')
    return segments


def _project(row: Mapping[str, Any], *, overlap_enabled: bool) -> dict[str, Any]:
    fields = PRECEDING_METADATA_FIELDS + (OVERLAP_CAPTURE_FIELDS if overlap_enabled else ())
    projected: dict[str, Any] = {}
    for path in fields:
        keys = path.split('.')
        value: Any = row
        for key in keys:
            if not isinstance(value, Mapping) or key not in value:
                break
            value = value[key]
        else:
            target = projected
            for key in keys[:-1]:
                target = target.setdefault(key, {})
            target[keys[-1]] = value
    return projected


def _score(value: Any) -> float | None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0 <= value <= 1
    ):
        return None
    return float(value)


def _decision(
    new: Mapping[str, Any],
    preceding: list[Mapping[str, Any]],
    cards: Mapping[str, Mapping[str, Any]],
    evaluation: Mapping[str, Any],
    tz: ZoneInfo,
    *,
    overlap_enabled: bool,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        'predecessor': None,
        'predecessor_skipped_overlap': 0,
        'decision': 'skip',
        'reason': None,
    }
    if not evaluation['uid_allowed']:
        return dict(result, reason=SkipReason.UID_NOT_ALLOWED)
    segments = _segments(new)
    reason = new_conversation_skip(new, segments, capture_end=evaluation['capture_end'])
    if reason is None and not isinstance(new.get('created_at'), datetime):
        reason = SkipReason.CONVERSATION_NOT_ELIGIBLE
    if reason is not None:
        return dict(result, reason=reason)
    rows = [_project(row, overlap_enabled=overlap_enabled) for row in preceding]
    selection = select_predecessor(new, rows, overlap_enabled=overlap_enabled)
    result['predecessor_skipped_overlap'] = len(selection.skipped_ids)
    if selection.candidate is None:
        return dict(result, reason=SkipReason.NO_PREDECESSOR)
    candidate_id = str(selection.candidate['id'])
    result['predecessor'] = candidate_id
    reason = predecessor_status_skip(selection.candidate)
    if reason is not None:
        return dict(result, reason=reason)
    if refresh_owed(selection.candidate) and evaluation['mode'] == 'merge':
        return dict(result, decision='indeterminate', reason='refresh_required')
    survivor = cards[candidate_id]
    survivor_segments = _segments(survivor)
    check = check_pair(survivor, survivor_segments, new, segments)
    result.update(gap_seconds=check.gap_seconds, speech_gap_seconds=check.speech_gap_seconds)
    if check.reason is not None:
        return dict(result, reason=check.reason)
    stored = new.get(DECISION_FIELD)
    prior = stored if isinstance(stored, Mapping) else {}
    reuse = prior.get('candidate_id') == candidate_id and prior.get('question_version') == QUESTION_VERSION
    if reuse:
        p_same = _score(prior.get('p_same'))
        result.update(score_source='sticky_decision', state_sha256=prior.get('state_sha256'))
    else:
        fragments = ledger_fragments(survivor)
        b = fragment_of(new)
        if b is None or not fragments:
            return dict(result, reason=SkipReason.CONVERSATION_NOT_ELIGIBLE)
        a = fragments[-1]
        candidates = list(fragments[:-1])
        for row in rows:
            if str(row.get('id')) != candidate_id and str(row.get('id')) not in selection.skipped_ids:
                candidates.extend(ledger_fragments(row))
        stretch = stretch_before(a, candidates)
        state = build_state(
            source=str(new['source']),
            a=a,
            a_segments=fragment_segments(survivor, survivor_segments, a),
            b=b,
            b_segments=segments,
            stretch=stretch,
            tz=tz,
        )
        state_hash = state_sha256(state)
        result.update(state_sha256=state_hash, stretch_count=len(stretch))
        scores = [
            score
            for score in evaluation.get('scores', [])
            if score.get('candidate_id') == candidate_id
            and score.get('question_version') == QUESTION_VERSION
            and score.get('state_sha256') == state_hash
        ]
        if not scores:
            return dict(result, decision='indeterminate', reason='score_missing')
        if len(scores) != 1:
            raise ValueError('scores must identify one answer per candidate, question version and state hash')
        p_same = _score(scores[0].get('p_same'))
        result['score_source'] = 'exported_state_score'
    same = p_same is not None and p_same >= MERGE_THRESHOLD
    decision = (
        ('shadow_would_merge' if same else 'shadow_keep')
        if evaluation['mode'] == 'shadow'
        else ('would_merge' if same else 'kept')
    )
    reason = 'jev_unavailable' if p_same is None else ('jev_same' if same else 'jev_different')
    return dict(result, decision=decision, reason=reason, p_same=p_same)


def replay(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    if payload.get('schema_version') != 1 or isinstance(payload.get('schema_version'), bool):
        raise ValueError('schema_version must be 1')
    tz = ZoneInfo(payload.get('timezone', 'UTC'))
    supplied = payload.get('conversations')
    evaluations = payload.get('evaluations')
    if not isinstance(supplied, list) or not isinstance(evaluations, list):
        raise ValueError('conversations and evaluations must be lists')
    cards: dict[str, dict[str, Any]] = {}
    for supplied_row in supplied:
        if not isinstance(supplied_row, dict):
            raise ValueError('conversation cards must be objects')
        row = _decode(supplied_row)
        cid = row.get('id')
        if not isinstance(cid, str) or not cid or cid in cards:
            raise ValueError('conversation ids must be unique nonempty strings')
        cards[cid] = row
    output = []
    for evaluation in evaluations:
        if not isinstance(evaluation, dict) or evaluation.get('conversation_id') not in cards:
            raise ValueError('evaluation requires a supplied conversation_id')
        if (
            not isinstance(evaluation.get('capture_end'), bool)
            or not isinstance(evaluation.get('uid_allowed'), bool)
            or evaluation.get('mode') not in ('shadow', 'merge')
        ):
            raise ValueError('evaluation requires capture_end/uid_allowed booleans and mode shadow or merge')
        ids = evaluation.get('preceding_ids')
        if (
            not isinstance(ids, list)
            or len(ids) > PRECEDING_QUERY_LIMIT
            or any(not isinstance(cid, str) or cid not in cards for cid in ids)
            or len(set(ids)) != len(ids)
        ):
            raise ValueError('preceding_ids must be the unique, supplied, at-most-six query result ids')
        scores = evaluation.get('scores', [])
        if not isinstance(scores, list) or any(not isinstance(score, dict) for score in scores):
            raise ValueError('scores must be a list of objects')
        new = cards[evaluation['conversation_id']]
        preceding = [cards[cid] for cid in ids]
        created = new.get('created_at')
        previous = created
        for row in preceding:
            time = row.get('created_at')
            if (
                not isinstance(created, datetime)
                or not isinstance(time, datetime)
                or time >= created
                or time > previous
                or row.get('source') != new.get('source')
                or row.get('discarded') is not False
                or row.get('status') not in _STATUSES
            ):
                raise ValueError('preceding_ids must preserve the exported visible same-source newest-first query')
            previous = time
        old = _decision(new, preceding, cards, evaluation, tz, overlap_enabled=False)
        new_result = _decision(new, preceding, cards, evaluation, tz, overlap_enabled=True)
        output.append(
            {
                'conversation_id': new['id'],
                'replay_kind': 'independent_snapshot_no_writes',
                'flatten_enabled': smart_merge_flatten_enabled(),
                'old': old,
                'new': new_result,
            }
        )
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('export', type=Path, help='Local JSON export; never fetched from a service')
    args = parser.parse_args()
    try:
        payload = json.loads(args.export.read_text(encoding='utf-8'))
        if not isinstance(payload, dict):
            raise ValueError('export must be an object')
        output = replay(payload)
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.exit(2, f'Invalid local export ({type(error).__name__}); see --help for the input contract.\n')
    for row in output:
        print(json.dumps(row, sort_keys=True, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
