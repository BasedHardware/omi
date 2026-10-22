"""Cross-device finalization adapter for the coverage authority.

Bounded completed snapshots only; no extra STT/LLM calls. The existing group
writer fences the speech and metadata used for every member. No secondary
segments are appended, no discard/deletion is performed, and audio is untouched.
"""

from __future__ import annotations

import logging
from itertools import combinations
from typing import Any

from config import refactor_modes
from database import capture_groups, capture_coverage
from database.capture_speech import get_shared_speech_snapshot
from models.capture_coverage import CaptureKey
from utils.capture.coverage_alignment import align, policy_metadata, quality_rank
from utils.capture.coverage_metrics import CROSS_DEVICE, CROSS_DEVICE_LINES
from utils.capture.identity import capture_keys
from utils.capture.shadow import compare
from utils.observability.fallback import record_fallback
from utils.conversations.overlap_shared_speech import shared_speech_group_guard

FLAG = 'CAPTURE_COVERAGE_MODE'
MAX_SNAPSHOTS = 7
SHADOW_SAMPLE_PERCENT = 5.0
MAX_PAIRS = 12
MAX_KEYS = 8
logger = logging.getLogger(__name__)


def _observe(decision) -> None:
    outcome = 'disagree' if decision.would_fold else 'agree'
    compare('cross_device_fold', outcome, lane='V3')
    CROSS_DEVICE_LINES.labels(outcome='duplicate').inc(decision.duplicate_lines)
    CROSS_DEVICE_LINES.labels(outcome='examined').inc(decision.secondary_lines)
    logger.info(
        'event=refactor_shadow lane=V3 check=cross_device_fold outcome=%s would_fold=%s duplicate_line_rate=%.4f',
        outcome,
        decision.would_fold,
        decision.duplicate_line_rate,
    )


def _alias_group(uid: str, rows: dict[str, dict[str, Any]], fingerprints: dict[str, str], group_id: str) -> None:
    primary = min(rows.values(), key=quality_rank)
    for secondary in rows.values():
        if secondary['id'] == primary['id']:
            continue
        keys = capture_keys(secondary)
        if len(keys) > MAX_KEYS:
            continue
        for root, channel, epoch, device_id, session_id in keys:
            key = CaptureKey(
                capture_root=root,
                channel=channel,
                clock_epoch=epoch,
                device_id=device_id,
                recording_session_id=session_id,
            )
            capture_coverage.record_shared(
                uid,
                key,
                primary_id=primary['id'],
                secondary_id=secondary['id'],
                group_id=group_id,
                fingerprints={cid: fingerprints[cid] for cid in (primary['id'], secondary['id'])},
                window={'started_at': secondary['started_at'], 'finished_at': secondary['finished_at']},
            )


def reconcile(uid: str, candidate_id: str, other_ids: list[str]) -> bool:
    """Return serving selection; a serving abstention must not fall into old grouping.

    Default shadow only observes and leaves incumbent behavior intact. Serve
    replaces the legacy automatic group decision, including on failed evidence.
    """
    if not refactor_modes.shadow_sampled(FLAG, uid, SHADOW_SAMPLE_PERCENT):
        # Shadow snapshot reads are sampled like the rest of the coverage shadow.
        return False
    serving = refactor_modes.serving_for(FLAG, uid)
    reads = checks = 0
    for other_id in other_ids[: MAX_SNAPSHOTS - 1]:
        if other_id == candidate_id:
            continue
        try:
            # Reload after every join: membership revisions/primary may change
            # when a third device finalizes, even though transcripts do not.
            if reads + 2 > MAX_SNAPSHOTS or checks >= MAX_PAIRS:
                break
            first_row, afp = get_shared_speech_snapshot(uid, candidate_id)
            second_row, bfp = get_shared_speech_snapshot(uid, other_id)
            reads += 2
            if not first_row or not second_row:
                continue
            first: dict[str, Any] = {**first_row, 'id': candidate_id}
            second: dict[str, Any] = {**second_row, 'id': other_id}
            decision = align(first, second)
            checks += 1
            _observe(decision)
            if not serving or not decision.would_fold or not afp or not bfp:
                continue
            groups: list[dict[str, Any]] = [r.get('capture_group') or {} for r in (first, second)]
            group_ids = {g['id'] for g in groups if g.get('id')}
            if len(group_ids) > 1 or any(g.get('kind') for g in groups):
                continue
            existing = next((g for g in groups if g.get('id')), {})
            # Do not silently convert a legacy group which could contain unique
            # speech or a complementary remote channel.
            if existing and existing.get('primary_policy') != 'cross_device_v1':
                continue
            rows: dict[str, dict[str, Any]] = {candidate_id: first, other_id: second}
            fingerprints: dict[str, str] = {candidate_id: afp, other_id: bfp}
            for member in existing.get('members') or []:
                cid = member['id']
                if cid in rows:
                    continue
                if reads >= MAX_SNAPSHOTS:
                    break
                row, fp = get_shared_speech_snapshot(uid, cid)
                reads += 1
                if not row or not fp:
                    break
                rows[cid], fingerprints[cid] = {**row, 'id': cid}, fp
            required = {m['id'] for m in existing.get('members') or []} | {candidate_id, other_id}
            if set(rows) != required:
                continue
            # Shared speech is not transitive: every member must independently
            # confirm each other, including entrants to an existing group.
            confirmed = True
            for a, b in combinations(rows.values(), 2):
                if checks >= MAX_PAIRS or not align(a, b).would_fold:
                    confirmed = False
                    break
                checks += 1
            if not confirmed:
                continue
            metadata = {cid: policy_metadata(row) for cid, row in rows.items()}

            def guard(current, transaction, client):
                return (
                    set(current) == set(rows)
                    and shared_speech_group_guard(current, transaction, client)
                    and all(policy_metadata(current[cid]) == metadata[cid] for cid in rows)
                )

            group_id = capture_groups.join_capture_group(
                uid,
                candidate_id,
                other_id,
                decision.evidence(),
                expected_windows={cid: (r['started_at'], r['finished_at']) for cid, r in rows.items()},
                expected_fingerprints=fingerprints,
                expected_group_revision=int(existing.get('revision') or 0),
                join_guard=guard,
                quality_ranker=quality_rank,
            )
            CROSS_DEVICE.labels(outcome='folded' if group_id else 'conflict').inc()
            if group_id:
                _alias_group(uid, rows, fingerprints, group_id)
        except Exception:
            # No exception text: decryption/provider failures may contain data.
            compare('cross_device_fold', 'error', lane='V3')
            CROSS_DEVICE.labels(outcome='error').inc()
            record_fallback(
                component='conversation_finalization',
                from_mode='cross_device_coverage',
                to_mode='separate_captures',
                reason='other',
                outcome='degraded',
                log=logger,
            )
    return serving
