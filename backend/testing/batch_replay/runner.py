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


def geometry_boundaries(units, validate_spans, source_audio, item_type, priority):
    """Synthetic boundary distribution, labelled separately from captured shapes."""
    durations = sorted(
        [
            unit['duration']
            for unit in units
            if type(unit.get('duration')) in (int, float) and 0 < unit['duration'] <= 7200
        ]
    )
    quantiles = (
        [
            {'quantile': quantile, 'duration': durations[round((len(durations) - 1) * quantile)]}
            for quantile in (0, 0.25, 0.5, 0.75, 0.9, 0.99, 1)
        ]
        if durations
        else []
    )
    samples = sorted({point['duration'] for point in quantiles})
    failures = []
    cases = expected_rejections = 0

    def check(name, operation, reject=False):
        nonlocal cases, expected_rejections
        cases += 1
        try:
            operation()
        except ValueError as error:
            if reject:
                expected_rejections += 1
            else:
                failures.append({'case': name, 'exception': type(error).__name__})
        except Exception as error:
            failures.append({'case': name, 'exception': type(error).__name__})
        else:
            if reject:
                failures.append({'case': name, 'exception': 'MissingExpectedRejection'})

    for index, duration in enumerate(samples):
        if duration <= 1 / 16000:
            continue
        for offset in (-1, 0, 1):
            end = duration + offset / 16000
            start = max(0.0, end - min(0.5, duration / 2))
            payload = {'speech_spans': [{'start': start, 'end': end}], 'speech_seconds': end - start}
            check(f'vad-{index}-eof-{offset}', lambda payload=payload: validate_spans(payload, duration))
        end = duration + 0.101
        payload = {'speech_spans': [{'start': 0.0, 'end': end}], 'speech_seconds': end}
        check(f'vad-{index}-outside-tolerance', lambda: validate_spans(payload, duration), reject=True)
        item = item_type(
            f'boundary-{index}',
            'synthetic-boundary-owner',
            1700000000.0,
            'synthetic:audio',
            duration,
            priority,
            conversation_id='synthetic-boundary-target',
        )
        frames = round(duration * 16000)
        if frames < 1:
            continue
        pcm = bytes(4)
        for name, start, offset, length, reject in (
            ('last-frame', frames - 1, 1, 1, False),
            ('first-frame', 0, 0, 1, False),
            ('past-capture', frames, 0, 1, True),
            ('past-source', 0, 2, 1, True),
            ('zero-frames', 0, 0, 0, True),
        ):
            ref = {
                'start_frame': start,
                'offset_frame': offset,
                'frames': length,
                'pcm_sha256': hashlib.sha256(pcm).hexdigest(),
            }
            body = (
                source_audio.MAGIC
                + json.dumps(
                    {
                        'owner_id': item.owner_id,
                        'conversation_id': item.conversation_id,
                        'capture_at': item.capture_at,
                        'references': [ref],
                        'context': {},
                    }
                ).encode()
            )
            check(
                f'slice-{index}-{name}', lambda body=body: source_audio.materialize(body, item, lambda _: pcm), reject
            )
    return {
        'source': 'synthetic-boundaries-from-duration-quantiles',
        'durations': samples,
        'quantiles': quantiles,
        'cases': cases,
        'expected_rejections': expected_rejections,
        'failures': failures,
    }


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
    unit_counts = defaultdict(Counter)
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
        identity = unit or active[0] or 'claim'
        issues[identity].add(key)
        unit_counts[identity][key] += 1

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
            if sid in untestable:
                raise ProjectionBlocked('recorded outcome and lane evidence required')
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
    untestable = set()
    for ordinal, unit in enumerate(units):
        sid, owner = unit['unit'], unit['owner']
        if not sid or not owner or not unit.get('duration'):
            coverage['invalid_work_item'] += 1
            continue
        chains[owner].append(sid)
        duration = unit['duration']
        outcome = unit.get('outcome')
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
        lane = unit.get('lane')
        log.jobs[sid] = {
            **asdict(item),
            'policy_parts': log.policy_parts,
            **({'fresh_capture': lane == 'fresh'} if lane in {'fresh', 'backfill'} else {}),
        }
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
            'result': {'outcome': outcome or 'unknown', 'result_uri': 'synthetic:result'},
        }
        if lane not in {'fresh', 'backfill'}:
            coverage['missing_lane'] += 1
            untestable.add(sid)
        if outcome not in {'success', 'silence'}:
            gap = (
                'missing_outcome'
                if outcome is None
                else 'missing_terminal_empty_evidence' if outcome == 'no_recoverable_speech' else 'invalid_outcome'
            )
            coverage[gap] += 1
            untestable.add(sid)
        if sid in untestable:
            continue
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

        def seed(cid, state, *, child=True):
            if not state.get('exists'):
                return
            current = {
                **deepcopy(incoming),
                'id': cid,
                'record_lane_owner': state.get('route_owner', 'batch_sync_v1'),
                'discarded': state.get('discarded', False),
                'deleted': state.get('deleted', False),
                'status': state.get('status'),
                'started_at': incoming['started_at'],
                'transcript_segments': [],
                'uses_custom_stt': state.get('custom_stt', False),
                'data_protection_level': state.get('protection', 'enhanced'),
            }
            if state.get('redirect'):
                current['sync_merged_into'] = state['redirect']
                if child and state.get('redirect_state') is not None:
                    seed(state['redirect'], state['redirect_state'], child=False)
                else:
                    coverage['missing_target_redirect_state'] += 1
            client.rows[('users', owner, 'conversations', cid)] = current

        if target_id:
            seed(target_id, target)
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
        if item.segment_id in untestable:
            raise ProjectionBlocked('recorded outcome and lane evidence required')
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
    boundaries = geometry_boundaries(units, projection_speech_spans, source_audio, WorkItem, Priority.DEEP)
    for failure in boundaries['failures']:
        key = f"synthetic_boundary:{failure['exception']}:{failure['case']}"
        exceptions[key] += 1
        issues['synthetic-boundaries'].add(key)
        unit_counts['synthetic-boundaries'][key] += 1
    return {
        'schema': 1,
        'units': len(units),
        'exceptions': dict(sorted(exceptions.items())),
        'unit_issues': {key: sorted(value) for key, value in sorted(issues.items())},
        'unit_exception_counts': {unit: dict(sorted(counts.items())) for unit, counts in sorted(unit_counts.items())},
        'chain_blocks': blocks,
        'persisted': len(log.persist_order),
        'coverage': dict(sorted(coverage.items())),
        'boundaries': boundaries,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--backend', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = replay(json.loads(args.corpus.read_text()), args.backend.resolve())
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
