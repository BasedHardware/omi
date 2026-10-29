"""Offline replay adapter; product imports resolve from the requested backend tree."""

import argparse
import asyncio
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from contextvars import copy_context
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
from unittest.mock import patch


def replay(corpus, backend):
    # This adapter is fixed across REF and BASE; only product code changes.
    sys.path.insert(0, str(backend))
    from testing.pipeline_sim import _env  # noqa: F401
    from testing.hermetic_network import block_outbound_network, block_local_redis
    from google.cloud import firestore, storage
    import grpc

    def refuse_client(*args, **kwargs):
        raise RuntimeError('offline replay refuses cloud client construction')

    # gRPC's C transport bypasses Python's socket guard. Refuse channels and
    # cloud clients before importing any product module, even with local ADC.
    with block_outbound_network(), block_local_redis(), ExitStack() as stack:
        for module, attribute in (
            (firestore, 'Client'),
            (storage, 'Client'),
            (grpc, 'secure_channel'),
            (grpc, 'insecure_channel'),
        ):
            stack.enter_context(patch.object(module, attribute, refuse_client))
        return _replay(corpus)


def _replay(corpus):
    import fakeredis
    from config.policy import ProjectionPolicy
    from database import batch_pipeline_projection_claim as claims
    from database import _client as firestore_clients
    from database.batch_pipeline_projection import ProjectionBlocked, ProjectionReplay
    from testing.pipeline_sim.clock import VirtualClock
    from testing.pipeline_sim.projection_drain import ChainLog, Lanes
    from utils.batch_pipeline import projection, projection_followup, source_audio
    from utils.batch_pipeline.contracts import Priority, ProjectionBinding, WorkItem, projection_speech_spans
    from utils.batch_pipeline.scheduler import owner_key
    from utils.sync import bridge
    from utils.sync.assignment import assign_in_transaction
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

    exceptions = Counter()
    issues = defaultdict(set)
    active = [None]

    def record(error, stage, unit=None):
        # Never emit exception messages, arguments, paths, or tracebacks.
        frames = []
        tb = error.__traceback__
        while tb:
            frames.append(f"{tb.tb_frame.f_globals.get('__name__', 'unknown')}.{tb.tb_frame.f_code.co_name}")
            tb = tb.tb_next
        site = frames[-1] if frames else stage
        key = f'{stage}:{type(error).__name__}:{site}'
        exceptions[key] += 1
        issues[unit or active[0] or 'claim'].add(key)

    class ErrorCollector(logging.Handler):
        def emit(self, event):
            # Product walk/follow-up catches errors. Capture the current exception
            # while still in that except block instead of parsing rendered logs.
            error = sys.exc_info()[1]
            if error is not None and ('outcome=error' in event.msg or 'outcome=retry' in event.msg):
                record(error, 'followup' if event.name.endswith('projection_followup') else 'walk')

    class ReplayLog(ChainLog):
        namespace = 'batch_pipeline_test_replay'

        def policy(self, sid):
            return ProjectionPolicy.from_dict(self.jobs[sid]['policy_parts']['projection'])

        def read(self, sid):
            active[0] = sid
            return super().read(sid)

        def session(self, sid, binding, now, **part):
            log = self
            index = part.get('part_index')
            count = part.get('part_count', 1)

            class Session:
                policy = log.policy(sid)
                segment_id = sid

                def prepare(self, transaction):
                    self.job, self.entry = log.jobs[sid], log.results[sid]
                    receipt = (
                        (self.entry.get('projection_parts') or {}).get(str(index))
                        if index is not None
                        else self.entry.get('projection')
                    )
                    if receipt:
                        raise ProjectionReplay(receipt)
                    previous = self.entry['previous_segment_id']
                    if previous != log.projection_watermark(self.entry['owner_key']):
                        raise ProjectionBlocked('earlier projection pending')

                def validate_plan(self, transaction, planned):
                    pass

                def persist(self, transaction, planned=None, **options):
                    self.prepare(transaction)
                    assigned = planned[0] if planned else {}
                    receipt = {
                        'state': 'quarantined' if options.get('quarantined') else 'persisted',
                        'conversation_id': assigned.get('id'),
                        'audio_required': False,
                        'enrichment_required': False,
                    }
                    row = log.results[sid]
                    if index is not None:
                        row.setdefault('projection_parts', {})[str(index)] = receipt
                        if len(row['projection_parts']) < count:
                            return receipt
                    held = options.get('quarantined') or any(
                        part['state'] == 'quarantined' for part in (row.get('projection_parts') or {}).values()
                    )
                    summary = {**receipt, 'state': 'quarantined' if held else 'persisted'}
                    row.update(projection=summary, projection_state='quarantine_held' if held else 'persisted')
                    if options.get('quarantined'):
                        log.jobs[sid]['recovery_state'] = 'held'
                    log.owners.setdefault(row['owner_key'], {})['projection_watermark'] = sid
                    log.persist_order.append(sid)
                    return receipt

                def persist_empty(self, **options):
                    return self.persist(None, **options)

            session = Session()
            session.binding = binding
            return session

        def ready(self, sid, binding, now, **options):
            row = self.results[sid]
            index = options.get('part_index')
            receipt = row['projection_parts'][str(index)] if index is not None else row['projection']
            receipt['state'] = 'ready'
            parts = list((row.get('projection_parts') or {}).values()) or [receipt]
            if any(part['state'] == 'quarantined' for part in parts):
                row['projection_state'] = 'quarantine_held'
            elif all(part['state'] == 'ready' for part in parts):
                row['projection_state'] = 'ready'

    log = ReplayLog(Lanes(VirtualClock()))
    units = corpus['units']
    by_id = {unit['unit']: unit for unit in units}
    chains = defaultdict(list)
    coverage = Counter()
    if not units:
        coverage['invalid_empty_corpus'] = 1
    payloads = {}
    for ordinal, unit in enumerate(units):
        sid, owner = unit['unit'], unit['owner']
        if not sid or not owner or not unit.get('duration'):
            coverage['invalid_work_item'] += 1
            continue
        chains[owner].append(sid)
        duration = unit['duration']
        outcome = unit.get('outcome') or 'success'
        try:
            item = WorkItem(
                sid,
                owner,
                1700000000.0 + ordinal * 8000,
                'synthetic:audio',
                duration,
                Priority.DEEP,
                conversation_id=unit.get('conversation'),
                unit_kind=unit.get('unit_kind', 'conversation'),
            )
        except Exception as error:
            coverage['invalid_work_item'] += 1
            record(error, 'work_item', sid)
            chains[owner].remove(sid)
            continue
        log.jobs[sid] = {**asdict(item), 'fresh_capture': unit['lane'] != 'backfill', 'policy_parts': log.policy_parts}
        log.bindings[sid] = ProjectionBinding(
            owner,
            sid,
            unit.get('content') or sid,
            (sid,),
            target_conversation_id=unit.get('target'),
            record_origin=unit['record_origin'],
        )
        log.results[sid] = {
            'owner_key': owner_key(owner),
            'segment_id': sid,
            'previous_segment_id': unit.get('previous'),
            'committed_at': ordinal,
            'projection_state': 'pending',
            'result': {'outcome': outcome, 'result_uri': 'synthetic:result'},
        }
        spans = unit.get('spans')
        if spans is None and outcome != 'silence':
            coverage['missing_vad_spans'] += 1
        decoded = unit.get('decoded_duration')
        if decoded is None:
            coverage['missing_decoded_duration'] += 1
        # Explicitly labelled model inputs keep assignment replay useful when
        # the Firestore-only capture has no encrypted artifact geometry.
        spans = spans if spans is not None else [{'start': 0.0, 'end': duration}]
        decoded = decoded if decoded is not None else duration
        speech = unit.get('speech_seconds')
        numeric_spans = [
            s for s in spans if type(s.get('start')) in (int, float) and type(s.get('end')) in (int, float)
        ]
        if speech is None and outcome == 'success' and corpus.get('source') == 'firestore-structure-only':
            coverage['missing_speech_accounting'] += 1
        speech = speech if speech is not None else sum(s['end'] - s['start'] for s in numeric_spans)
        synthetic_spans = [
            {'start': s['start'], 'end': min(duration, decoded, s['end'])}
            for s in numeric_spans
            if 0 <= s['start'] < min(duration, decoded, s['end'])
        ]
        payloads[sid] = {
            'audio_seconds': decoded,
            'speech_seconds': speech,
            'speech_spans': spans,
            'words': [{'word': 'synthetic.', 'timestamp': [s['start'], s['end']]} for s in synthetic_spans],
            'diarization': {'turns': [{**s, 'speaker': 'a'} for s in synthetic_spans]},
        }
        if outcome not in {'success', 'silence'}:
            coverage['missing_terminal_empty_evidence'] += 1
        if outcome == 'silence':
            payloads[sid].update(speech_seconds=0.0, speech_spans=[], words=[], diarization={'turns': []})
        if unit.get('spans') is not None and outcome == 'success':
            try:
                projection_speech_spans(payloads[sid], duration)
                coverage['vad_validated'] += 1
            except Exception as error:
                record(error, 'vad', sid)
        references = unit.get('references')
        if references is None:
            coverage['missing_source_geometry'] += 1
        else:
            try:
                sources = {}
                refs = []
                for index, ref in enumerate(references):
                    # source_frames must come from observed metadata; deriving it
                    # from offset+frames would hide an out-of-source regression.
                    if ref.get('source_frames') is None:
                        raise ValueError('source length unavailable')
                    if (
                        type(ref['source_frames']) is not int
                        or not 0 < ref['source_frames'] <= source_audio.MAX_SOURCE_BYTES // 2
                    ):
                        raise ValueError('invalid source length')
                    pcm = bytes(ref['source_frames'] * 2)
                    sources[index] = pcm
                    refs.append({**ref, 'key': index, 'pcm_sha256': hashlib.sha256(pcm).hexdigest()})
                manifest = {
                    'owner_id': owner,
                    'conversation_id': item.conversation_id,
                    'capture_at': item.capture_at,
                    'references': refs,
                    'context': {},
                }
                body = source_audio.MAGIC + json.dumps(manifest).encode()
                source_audio.materialize(body, item, lambda ref: sources[ref['key']])
                coverage['source_validated'] += 1
            except Exception as error:
                record(error, 'source_audio', sid)

    def assign(owner, incoming, *, before_assign, after_assign, target_id=None, **options):
        unit = by_id[active[0]]
        client = StrictFirestore()
        target = unit.get('target_state') or {}
        if target_id and target.get('exists'):
            current = {
                **deepcopy(incoming),
                'id': target_id,
                'record_lane_owner': target.get('route_owner', 'batch_sync_v1'),
                'discarded': target.get('discarded', False),
                'deleted': target.get('deleted', False),
                'status': target.get('status'),
                'started_at': incoming['started_at'],
                'transcript_segments': [],
                'uses_custom_stt': target.get('custom_stt', False),
                'data_protection_level': target.get('protection', 'enhanced'),
            }
            if target.get('redirect'):
                current['sync_merged_into'] = target['redirect']
                coverage['missing_target_redirect_state'] += 1
            client.rows[('users', owner, 'conversations', target_id)] = current
        transaction = client.transaction()
        before_assign(transaction)
        planned = assign_in_transaction(
            transaction,
            client.collection('users').document(owner),
            incoming,
            target_id=target_id,
            decode=deepcopy,
            encode=deepcopy,
            invalidate=lambda row: None,
        )
        after_assign(transaction, planned)
        return planned

    def load(item, uri):
        active[0] = item.segment_id
        return payloads[item.segment_id]

    def forbid_firestore(*args, **kwargs):
        raise RuntimeError('offline replay attempted an unfaked Firestore leaf')

    projector = projection.Projector(log, load, publish=lambda *a: None)
    projector.store = log
    projector.complete_content = lambda *a, **k: None
    collector = ErrorCollector()
    root = logging.getLogger()
    old_handlers, old_level = root.handlers[:], root.level
    root.handlers, root.level = [collector], logging.DEBUG
    redis = fakeredis.FakeRedis()
    blocks = []
    try:
        with ExitStack() as stack:
            stack.enter_context(patch.object(claims, '_redis_client', lambda: redis))
            stack.enter_context(patch.object(firestore_clients, 'get_firestore_client', forbid_firestore))
            stack.enter_context(patch.object(firestore_clients, 'get_customer_firestore_client', forbid_firestore))
            stack.enter_context(patch.object(bridge, 'finish_sync_bridges', lambda owner, canonical, **k: canonical))
            stack.enter_context(patch.object(projection.conversations_db, 'assign_sync_conversation', assign))
            stack.enter_context(
                patch.object(projection.conversations_db, 'get_closest_conversation_to_timestamps', lambda *a: None)
            )
            stack.enter_context(
                patch.dict(
                    os.environ,
                    {
                        'BATCH_PIPELINE_PROJECTION_PREFETCH': '0',
                        'BATCH_PIPELINE_OWNER_DRAIN_ENABLED': 'false',
                        'BATCH_PIPELINE_PROJECTION_INDEX_DEFERRED_ENABLED': 'false',
                    },
                )
            )
            for owner, segments in chains.items():
                if not segments:
                    continue
                # Rewind the sampled window for counterfactual assignment replay.
                # Keep original links; only the external boundary is anchored.
                log.owners[owner_key(owner)] = {'projection_watermark': by_id[segments[0]].get('previous')}
                projector.project_owner(owner, limit=len(segments) + 1, budget_seconds=600)
                pending = [sid for sid in segments if not log.results[sid].get('projection')]
                if pending:
                    blocks.append({'owner': owner, 'head': pending[0], 'blocked_units': len(pending), 'units': pending})

            async def followups():
                runner = projection_followup.ProjectionFollowups(projector)

                # Every leaf runs in a distinct copied context, including enter
                # and exit. The REAL projection_claim uses fakeredis Lua.
                async def threaded(executor, function, *args, **kwargs):
                    ctx = copy_context()
                    return await asyncio.get_running_loop().run_in_executor(
                        pool, lambda: ctx.run(function, *args, **kwargs)
                    )

                with patch.object(projection_followup, 'run_blocking', threaded):
                    for sid in log.persist_order:
                        active[0] = sid
                        try:
                            await runner._run(sid)
                            coverage['followup_exercised'] += 1
                        except Exception as error:
                            record(error, 'followup', sid)

            with ThreadPoolExecutor(max_workers=2) as pool:
                asyncio.run(followups())
    finally:
        root.handlers, root.level = old_handlers, old_level
    return {
        'schema': 1,
        'units': len(units),
        'exceptions': dict(sorted(exceptions.items())),
        'unit_issues': {key: sorted(value) for key, value in sorted(issues.items())},
        'chain_blocks': blocks,
        'persisted': len(log.persist_order),
        'coverage': dict(sorted(coverage.items())),
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--backend', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = replay(json.loads(args.corpus.read_text()), args.backend.resolve())
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
