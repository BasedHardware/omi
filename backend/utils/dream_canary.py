"""Scheduled synthetic path through dirty admission, real dream lanes and encrypted report."""

import asyncio
import logging
import json
from dataclasses import replace
from datetime import datetime, timezone

from config.dream_agent import Caps, canary_uid, mode
from database import dream_canary, dream_store, review_store, review_changes, conversations
from models.agent_edit import HarnessEdit
from database.dream_dirty import canary_writing
from database.dream_effect_fence import ACTIVE_RUN
from utils.conversations import lifecycle
from utils import dream_agent, dream_harness_transport
from utils.agent_capabilities import tools
from utils.agent_capabilities.reads import read_record
from utils.executors import db_executor, run_blocking
from utils.dream_metrics import CANARY

logger = logging.getLogger(__name__)
DEADLINE_SECONDS = 600


class CanaryFailure(Exception):
    pass


def fixture_edit():
    ref = 'conversations/' + dream_canary.RECORD_ID
    return HarnessEdit(
        kind='spelling',
        target=ref,
        before='Qorby',
        after='Qorbi',
        evidence=[ref],
        reason='Synthetic explicit spelling check',
        value=4,
    )


def seed(uid):
    dream_canary.ensure_synthetic_owner(uid)
    # A failed journal/Undo check must not poison the next deterministic probe.
    # Only the fixed fixture's receipts are reset, after synthetic-owner proof.
    key = tools.edit_key(fixture_edit())
    change_id = tools.dream_change_view.change_id_for_key(uid, key)
    review_store.user(uid).collection('review_changes').document(review_store.safe_id(change_id)).delete()
    review_store.user(uid).collection('review_do_not_redo').document(review_store.safe_id(key)).delete()
    review_store.user(uid).collection('transcript_corrections').document(dream_canary.RECORD_ID).set(
        review_store.encode_doc(uid, {'source': []})
    )
    token = canary_writing.set(True)
    try:
        lifecycle.create_completed_conversation(
            uid,
            {
                'id': dream_canary.RECORD_ID,
                'created_at': datetime.now(timezone.utc),
                'status': 'completed',
                'discarded': False,
                'has_photos': False,
                'data_protection_level': 'enhanced',
                'structured': {
                    'title': 'Synthetic dream check',
                    'overview': 'Robot Qorby plans an invented workshop.',
                },
                'transcript_segments': [
                    {
                        'id': 'synthetic-speech',
                        'text': 'Our robot is Qorby. The correct robot name is spelled Q O R B I, Qorbi. It plans an invented workshop.',
                        'speaker': 'SPEAKER_00',
                        'start': 0,
                        'end': 5,
                    }
                ],
            },
        )
    finally:
        canary_writing.reset(token)


async def _probe(uid, progress, state):
    await run_blocking(db_executor, seed, uid)
    if not await run_blocking(db_executor, dream_store.dirty_count, uid):
        raise CanaryFailure('not_enqueued')
    state['stage'] = 'admit'
    # Schema bytes dominate the cap; only 256 completion tokens per lane.
    # Allow 48 half-hour checks plus retries, sharing the global ceiling.
    caps = replace(
        Caps.from_env(),
        tokens=min(96000, Caps.from_env().tokens),
        passes=96,
        manual_runs=96,
        edits=1,
        completion_tokens=256,
    )
    ref = 'conversations/' + dream_canary.RECORD_ID
    edit = fixture_edit()
    calls = [
        {
            'id': 'synthetic-edit',
            'function': {
                'name': 'propose_edit',
                'arguments': json.dumps({'edit': edit.model_dump(mode='json')}),
            },
        },
        {
            'id': 'synthetic-finish',
            'function': {
                'name': 'finish',
                'arguments': json.dumps({'summary': 'Synthetic pipeline health check'}),
            },
        },
    ]
    report = await dream_agent.run_pass(
        uid, caps=caps, canary=True, timeout_seconds=540, progress=progress, bootstrap_tools=calls
    )
    progress.clear()
    if not report.get('run_id'):
        raise CanaryFailure('not_admitted')
    state['stage'] = 'model'
    if (
        report.get('status') != 'complete'
        or set(report.get('model_lanes', []))
        != {
            dream_harness_transport.VERIFY_LANE,
        }
        or report.get('verifier_transport_responses') != 2
        or report.get('tool_counts', {}).get('propose_edit') != 1
    ):
        state['error'] = report.get('error_type') or 'CanaryFailure'
        raise CanaryFailure('model_incomplete')
    state['stage'] = 'report'
    doc = await run_blocking(db_executor, dream_store.own_run, uid, report['run_id'])
    decoded = await run_blocking(db_executor, review_store.decode_doc, uid, doc)
    if (
        not decoded
        or decoded.get('source', {}).get('status') != 'complete'
        or doc.get('mode') != 'shadow'
        or doc.get('tokens', 0) <= 0
    ):
        raise CanaryFailure('report_missing')
    # The marked synthetic owner is the only canary write authority.
    # A verifier's semantic choice cannot page on-call. Its successful
    # schema round-trip is checked above; this deterministic fixture
    # checks the same journal and Undo boundary independently.
    state['stage'] = 'journal'
    records = {ref: await run_blocking(db_executor, read_record, uid, ref)}
    fences = await run_blocking(db_executor, tools.proposal_fences, uid, {'records': records})
    original = await run_blocking(db_executor, conversations.get_conversation_raw_snapshot, uid, dream_canary.RECORD_ID)
    probe_lease = await run_blocking(db_executor, dream_store.acquire, uid, caps, canary=True, trigger='manual')
    if not probe_lease:
        raise CanaryFailure('journal_not_admitted')
    scope = ACTIVE_RUN.set((uid, probe_lease['run_id']))
    try:
        status = await run_blocking(
            db_executor,
            tools.apply_verified_edit,
            uid,
            edit,
            records,
            authority='dream',
            expected_records=fences,
        )
        if status != 'applied':
            raise CanaryFailure('journal_missing')
    finally:
        ACTIVE_RUN.reset(scope)
        await run_blocking(
            db_executor,
            dream_store.finish,
            uid,
            probe_lease,
            {'reason': 'idle', 'tokens': 0, 'usage_unknown': False},
            success=True,
            refund=True,
        )
    key = tools.edit_key(edit, records)
    change = tools.dream_change_view.edit_change(uid, edit, records, key)
    state['stage'] = 'undo'
    await run_blocking(db_executor, review_changes.set_undone, uid, change.change_id, True)
    restored = await run_blocking(db_executor, read_record, uid, ref)
    restored_segments = [
        {field: value for field, value in segment.items() if field != 'original_text'}
        for segment in restored['transcript_segments']
    ]
    expected_segments = [
        {field: value for field, value in segment.items() if field != 'original_text'}
        for segment in records[ref]['transcript_segments']
    ]
    if restored_segments != expected_segments:
        raise CanaryFailure('undo_inexact')
    raw = await run_blocking(db_executor, conversations.get_conversation_raw_snapshot, uid, dream_canary.RECORD_ID)
    if raw is None or original is None or raw['transcript_segments'] != original['transcript_segments']:
        raise CanaryFailure('original_speech_changed')
    # A durable Undo marker is correct for real corrections; the
    # synthetic fixture intentionally repeats the same operation.
    await run_blocking(
        db_executor,
        lambda: review_store.user(uid).collection('review_do_not_redo').document(review_store.safe_id(key)).delete(),
    )
    await run_blocking(
        db_executor,
        lambda: review_store.user(uid)
        .collection('review_changes')
        .document(review_store.safe_id(change.change_id))
        .delete(),
    )


async def check():
    uid = canary_uid()
    state = {'stage': 'enqueue', 'error': 'none'}
    passed = False
    skipped = False
    consecutive = 0
    progress = {}
    try:
        async with asyncio.timeout(DEADLINE_SECONDS):
            if not uid:
                raise CanaryFailure('misconfigured')
            # An operator stop is not a failed synthetic pass. Env and the
            # dynamic dream_control flag both surface as mode() == 'off'.
            if mode() == 'off':
                skipped = True
                state['error'] = 'disabled'
            else:
                await _probe(uid, progress, state)
                passed = True
    except Exception as exc:
        state['stage'] = progress.get('stage', state['stage'])
        if state['error'] == 'none':
            state['error'] = type(exc).__name__
    if skipped:
        try:
            async with asyncio.timeout(3):
                consecutive = await run_blocking(db_executor, dream_canary.reset_failures)
        except Exception:
            consecutive = 0
        status = 'skipped'
    else:
        try:
            async with asyncio.timeout(3):
                consecutive = await run_blocking(db_executor, dream_canary.record_result, passed)
        except Exception as exc:
            passed, state['error'] = False, type(exc).__name__
        status = 'pass' if passed else 'fail'
    stage = state['stage']
    error = state['error']
    CANARY.labels(status, stage).inc()
    logger.info(
        'Dream canary status=%s stage=%s error_type=%s consecutive_failures=%d', status, stage, error, consecutive
    )
    return {'status': status, 'stage': stage, 'error_type': error, 'consecutive_failures': consecutive}
