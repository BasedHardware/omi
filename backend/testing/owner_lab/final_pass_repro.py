"""Read-only replay of production's staged-unit batch speaker pass.

No dataset is bundled. Run as a module from backend; inputs are private files.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from contextlib import contextmanager, ExitStack, redirect_stdout
import io
import json
import logging
import time
from unittest.mock import patch


class WriteBlocked(RuntimeError):
    pass


def deny_write(*args, **kwargs):
    raise WriteBlocked('owner_lab_write_fence')


@contextmanager
def write_fence():
    """Fence SDK entry points and buffered/transport writes, including pipelines.

    Empty Firestore commits are allowed: the real reference reader uses read-only
    transactions. Every request carrying writes is refused before transport.
    """
    from google.cloud.firestore_v1.document import DocumentReference
    from google.cloud.firestore_v1.async_document import AsyncDocumentReference
    from google.cloud.firestore_v1.base_batch import BaseBatch
    from google.cloud.firestore_v1.services.firestore import FirestoreClient, FirestoreAsyncClient
    from google.cloud.storage import Blob, Bucket, Client
    from redis.connection import Connection
    from redis.asyncio.connection import Connection as AsyncConnection
    from redis.client import Redis, Pipeline
    from redis.asyncio.client import Redis as AsyncRedis, Pipeline as AsyncPipeline

    def checked_commit(original):
        def commit(self, request=None, *args, **kwargs):
            writes = request.get('writes', ()) if isinstance(request, dict) else getattr(request, 'writes', ())
            if writes or kwargs.get('writes'):
                deny_write()
            return original(self, request, *args, **kwargs)

        return commit

    # Only explicit Redis reads are admitted. EVAL/scripts, transactions and
    # unknown module commands are writes until proven otherwise.
    reads = frozenset(
        'GET MGET HGET HMGET HGETALL HEXISTS HLEN EXISTS TTL PTTL TYPE SCAN HSCAN SSCAN ZSCAN SMEMBERS SISMEMBER ZRANGE ZREVRANGE ZSCORE PING INFO AUTH HELLO SELECT CLIENT'.split()
    )

    def require_read(args):
        command = args[0].decode() if isinstance(args[0], bytes) else str(args[0])
        if command.upper() not in reads or (
            command.upper() == 'CLIENT' and str(args[1]).upper() not in {'SETINFO', 'SETNAME', 'ID', 'GETNAME'}
        ):
            deny_write()

    def checked_command(original):
        def execute(self, *args, **kwargs):
            require_read(args)
            return original(self, *args, **kwargs)

        return execute

    def checked_pipeline(original):
        def execute(self, *args, **kwargs):
            for command, _options in self.command_stack:
                require_read(command)
            return original(self, *args, **kwargs)

        return execute

    with ExitStack() as stack:
        for cls in (DocumentReference, AsyncDocumentReference, BaseBatch):
            for name in ('set', 'update', 'delete', 'create'):
                stack.enter_context(patch.object(cls, name, deny_write))
        for cls in (FirestoreClient, FirestoreAsyncClient):
            stack.enter_context(patch.object(cls, 'commit', checked_commit(cls.commit)))
            for name in ('batch_write', 'write', 'delete_document', 'create_document', 'update_document'):
                stack.enter_context(patch.object(cls, name, deny_write))
        for cls, names in (
            (
                Blob,
                (
                    'upload_from_file',
                    'upload_from_filename',
                    'upload_from_string',
                    'delete',
                    'patch',
                    'update',
                    'compose',
                    'rewrite',
                    '_initiate_resumable_upload',
                ),
            ),
            (
                Bucket,
                ('delete', 'delete_blob', 'delete_blobs', 'patch', 'update', 'copy_blob', 'rename_blob', 'create'),
            ),
            (Client, ('create_bucket',)),
        ):
            for name in names:
                stack.enter_context(patch.object(cls, name, deny_write))
        for cls in (Redis, Pipeline, AsyncRedis, AsyncPipeline):
            stack.enter_context(patch.object(cls, 'execute_command', checked_command(cls.execute_command)))
        for cls in (Connection, AsyncConnection):
            stack.enter_context(patch.object(cls, 'send_command', checked_command(cls.send_command)))
        # Pipelines queued before the fence cannot bypass execute_command.
        for cls in (Pipeline, AsyncPipeline):
            stack.enter_context(patch.object(cls, 'execute', checked_pipeline(cls.execute)))
        yield


@contextmanager
def isolated_metrics():
    """Suppress this replay's Prometheus writes, including lazy label children.

    Production modules retain their real metric objects. Context-local guards
    keep unrelated callers in other threads observable while the lab runs.
    New default-registry collectors imported by the replay are suppressed too.
    """
    from contextvars import ContextVar
    from prometheus_client import REGISTRY, Counter, Gauge, Histogram, Summary, Info, Enum
    from prometheus_client.metrics import MetricWrapperBase
    from prometheus_client.registry import CollectorRegistry

    active = ContextVar('owner_lab_metrics', default=False)

    class SilentMetric:
        # The full child protocol includes value access, context managers and
        # decorators. Lazy backend imports also call Gauge.set_function().
        def __getattr__(self, name):
            return self

        def __call__(self, *args, **kwargs):
            if len(args) == 1 and callable(args[0]) and not kwargs:
                return args[0]
            return self

        def labels(self, *args, **kwargs):
            return self

        def time(self):
            return self

        def count_exceptions(self, *args, **kwargs):
            return self

        track_inprogress = time

        def set_function(self, function):
            return None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self):
            return 0

        def __iter__(self):
            return iter(())

        def __getitem__(self, key):
            return self

    silent = SilentMetric()

    def guarded(original, replacement=None):
        def call(self, *args, **kwargs):
            if active.get():
                return replacement
            return original(self, *args, **kwargs)

        return call

    original_register = CollectorRegistry.register

    def register(self, collector):
        if self is not REGISTRY or not active.get():
            return original_register(self, collector)

    with ExitStack() as stack:
        stack.enter_context(patch.object(CollectorRegistry, 'register', register))
        stack.enter_context(patch.object(MetricWrapperBase, 'labels', guarded(MetricWrapperBase.labels, silent)))
        for name in ('remove', 'clear'):
            stack.enter_context(patch.object(MetricWrapperBase, name, guarded(getattr(MetricWrapperBase, name))))
        for cls, names in (
            (Counter, ('inc',)),
            (Gauge, ('set', 'inc', 'dec', 'set_to_current_time', 'set_function')),
            (Histogram, ('observe',)),
            (Summary, ('observe',)),
            (Info, ('info',)),
            (Enum, ('state',)),
        ):
            for name in names:
                stack.enter_context(patch.object(cls, name, guarded(getattr(cls, name))))
        token = active.set(True)
        try:
            yield
        finally:
            active.reset(token)


def scope_kind(segment):
    from config.batch_conversation_speakers import batch_unit_scope

    scope = (segment.provider_speaker or {}).get('scope') or segment.speaker_id_scope or ''
    if batch_unit_scope(segment):
        return 'batch_unit'
    if scope.startswith('final:batch:conversation:'):
        return 'batch_conversation'
    if scope.startswith(('sync:', 'final:batch:sync:')):
        return 'sync'
    return 'other'


@isolated_metrics()
def reproduce(uid, conversation, receipt, *, diarizer='stub', load_prints=None, apply=None):
    """Run the real adapter; substitute only admission, writes and GPU transport."""
    from config.batch_conversation_speakers import batch_unit_scope
    from models.diarization import DiarizationResult, OMI_EMBEDDING_SPACE
    from utils.conversations import final_pass_batch as batch
    from utils.conversations.speaker_resolution import apply_speaker_resolution, load_voiceprints_for_resolution
    from utils.stt.diarization_turns import exclusive_from_activity

    captured = {'apply_calls': 0, 'learn_calls': 0, 'requeue_calls': 0}
    read_wall_seconds = 0.0
    read_budget = None
    coverage = set()
    projection_words = []
    original_units, original_assemble = batch._units, batch._assemble
    before = {
        s.id: (s.speaker_id_scope, s.speaker_id, s.is_user, s.person_id, s.recurring_voice_id)
        for s in conversation.transcript_segments
    }
    kinds = {}
    for segment in conversation.transcript_segments:
        kind = scope_kind(segment)
        kinds[kind] = kinds.get(kind, 0) + 1
    required = {s.id for s in conversation.transcript_segments if batch_unit_scope(s) and s.end > s.start}

    def timed_read(call, *args, **kwargs):
        nonlocal read_wall_seconds
        started = time.perf_counter()
        try:
            return call(*args, **kwargs)
        finally:
            read_wall_seconds += time.perf_counter() - started

    def units(uid, conversation, budget, **kwargs):
        nonlocal read_budget
        # Capture before reference loading, which itself can hit the deadline.
        read_budget = budget
        stream = timed_read(original_units, uid, conversation, budget, **kwargs)

        def capture():
            while True:
                try:
                    item, pcm, words, check = timed_read(next, stream.units)
                except StopIteration:
                    return
                coverage.update(w['segment_id'] for w in words)

                def validate(check=check):
                    return timed_read(check)

                yield item, pcm, words, validate
                del pcm, words

        return replace(stream, units=capture())

    def assemble(*args):
        nonlocal projection_words
        pcm, words, checks = original_assemble(*args)
        projection_words = words
        return pcm, words, checks

    def capture_apply(*args, **kwargs):
        captured['apply_calls'] += 1
        (apply or apply_speaker_resolution)(*args, **kwargs)

    def capture_learn(*args, **kwargs):
        captured['learn_calls'] += 1
        return {}  # Observe the attempted learning; publish no profile.

    def capture_requeue(*args):
        captured['requeue_calls'] += 1  # No outbox/Cloud Tasks write in the lab.

    class ProjectionDiarizer:
        backend = 'projection_stub'

        def diarize(self, pcm, **kwargs):
            turns = exclusive_from_activity(
                [
                    {'start': w['timestamp'][0], 'end': w['timestamp'][1], 'speaker': str(w['projection_speaker'])}
                    for w in projection_words
                    if w['timestamp'][1] > w['timestamp'][0]
                ]
            )
            return DiarizationResult(
                turns=turns,
                overlaps=[],
                centroids={},
                embedding_space=OMI_EMBEDDING_SPACE,
                version='projection-stub',
                provenance={'backend': self.backend},
            )

    with write_fence(), ExitStack() as stack:
        stack.enter_context(patch.object(batch, '_units', units))
        stack.enter_context(patch.object(batch, '_assemble', assemble))
        stack.enter_context(patch.object(batch, '_reserve_budget', lambda _: True))
        stack.enter_context(patch.object(batch.recurring_voices, 'learn', capture_learn))
        stack.enter_context(patch.object(batch, 'emit_product_event', lambda **kw: None))
        if diarizer == 'stub':
            stack.enter_context(patch.object(batch, 'HttpDiarizer', lambda *a, **kw: ProjectionDiarizer()))
        result = batch.run_batch_final_pass(
            uid,
            conversation,
            receipt,
            load_prints=load_prints or load_voiceprints_for_resolution,
            apply=capture_apply,
            requeue=capture_requeue,
        )
    changed = sum(
        before[s.id] != (s.speaker_id_scope, s.speaker_id, s.is_user, s.person_id, s.recurring_voice_id)
        for s in conversation.transcript_segments
    )
    return {
        **result,
        'exception_type': result.get('exception_type'),
        'location': result.get('location'),
        'message': result.get('reason'),  # Same code-owned diagnostic as production.
        'failing_unit': result.get('failing_unit'),
        'scope_kinds': kinds,
        'segment_coverage': {'total': len(before), 'required': len(required), 'placed': len(required & coverage)},
        'changed_segments': changed,
        'speaker_count': len({(s.speaker_id_scope, s.speaker_id) for s in conversation.transcript_segments}),
        # Timed phases include decoding/projection CPU, but exclude assembly,
        # diarization and application. Revalidation reads are included too.
        'read_wall_seconds': read_wall_seconds,
        'read_bytes': read_budget.received_bytes if read_budget else 0,
        'read_reserved_bytes': read_budget.downloaded_bytes if read_budget else 0,
        'read_objects': read_budget.objects if read_budget else 0,
        **captured,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--uid-file', required=True)
    parser.add_argument('--secret-file', required=True)
    parser.add_argument('--conversations-file', required=True, help='0600 JSON list of conversation IDs')
    parser.add_argument('--diarizer', choices=('stub', 'http'), default='stub')
    parser.add_argument('--diarizer-url-file', help='0600 file, required for http')
    args = parser.parse_args(argv)
    from testing.owner_lab.guard import owner_uid, load_secret, read_private

    uid = owner_uid(args.uid_file)
    load_secret(args.secret_file)
    ids = json.loads(read_private(args.conversations_file, 'conversation selection'))
    if not isinstance(ids, list) or not ids or any(not isinstance(cid, str) or not cid or '/' in cid for cid in ids):
        parser.error('conversation selection must be a nonempty JSON list of opaque IDs')
    if args.diarizer == 'http':
        if not args.diarizer_url_file:
            parser.error('http requires --diarizer-url-file')
        import os

        os.environ['HOSTED_DIARIZATION_API_URL'] = read_private(args.diarizer_url_file, 'diarizer URL')
    # Do not leak provider errors, paths, IDs or decoded text through library logs.
    logging.disable(logging.CRITICAL)
    successes = 0
    with write_fence():
        from database import conversations as db
        from models.conversation import Conversation
        from utils.conversations.final_pass_errors import error_details

        for index, cid in enumerate(ids):
            load_wall_seconds = 0.0
            try:
                with redirect_stdout(io.StringIO()):
                    started = time.perf_counter()
                    try:
                        row = db.get_conversation(uid, cid, include_transcript_decode_status=True)
                        if not row or not row.pop('_recovery_transcript_decoded', False):
                            raise ValueError('conversation_unavailable')
                        conversation = Conversation(**row)
                        receipt = db.get_manual_speaker_receipt(uid, cid)
                    finally:
                        load_wall_seconds = time.perf_counter() - started
                    result = reproduce(uid, conversation, receipt, diarizer=args.diarizer)
            except Exception as error:
                details = error_details(error)
                result = {
                    'outcome': 'failed_load',
                    'exception_type': details['exception_type'],
                    'location': details['location'],
                    'message': details['reason'],
                    'failing_unit': None,
                    'scope_kinds': {},
                    'segment_coverage': None,
                    'read_wall_seconds': 0.0,
                    'read_bytes': 0,
                    'read_reserved_bytes': 0,
                    'read_objects': 0,
                }
            successes += result['outcome'] == 'success'
            print(
                json.dumps({'case': index, **result, 'conversation_load_wall_seconds': load_wall_seconds}), flush=True
            )
    print(
        json.dumps(
            {'summary': True, 'conversations': len(ids), 'successes': successes, 'success_rate': successes / len(ids)}
        )
    )


if __name__ == '__main__':
    main()
