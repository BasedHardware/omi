"""Pipeline lab: start-state shapes found on a real day, reproduced with synthetic rows.

Each test mirrors one failure of the first real-day dry run: a blob still sealed under the
production key, a memory chunk over Firestore's entity limit, a focused goal, a row the
product refuses to encode, and a Typesense that is not listening. None may drop a row silently.
"""

import json
import socket
from types import SimpleNamespace

from testing.pipeline_lab.chain.plugin import stage_summary
from testing.pipeline_lab.seed.writer import (
    ProductSeedWriter,
    clear_sealed_blobs,
    reset_lab_user,
    seed_start_state,
)
from testing.pipeline_lab.stack import LAB_UID
from testing.pipeline_lab.stack.env import peer_listening

LAB_ENV = {'FIRESTORE_EMULATOR_HOST': '127.0.0.1:8085', 'GOOGLE_CLOUD_PROJECT': 'demo-omi-local'}
SEALED = 'gAAAAAB' + 'x' * 600  # the shape of production ciphertext: a long opaque string


def test_sealed_blobs_are_cleared_and_named():
    row = {
        'id': 'c1',
        'open_loop_extractions': SEALED,
        'open_loop_extractions_compressed': True,
        'manual_speaker_assignments': {'s1': 'p1'},
        'manual_speaker_assignments_compressed': True,
    }
    assert clear_sealed_blobs(row) == ['open_loop_extractions']
    assert row['open_loop_extractions'] is None and row['open_loop_extractions_compressed'] is None
    # Decoded JSON stays as it is.
    assert row['manual_speaker_assignments'] == {'s1': 'p1'}
    assert clear_sealed_blobs({'id': 'c2', 'open_loop_extractions': None}) == []


class _Batch:
    def __init__(self, sink):
        self.sink, self.ops = sink, []

    def set(self, ref, data):
        self.ops.append((ref, data))

    def commit(self):
        self.sink.extend(self.ops)


class _Ref:
    def __init__(self, path):
        self.path = path

    def collection(self, name):
        return _Ref(self.path + (name,))

    def document(self, name):
        return _Ref(self.path + (name,))


class _Client:
    project = 'demo-omi-local'

    def __init__(self):
        self.written = []
        self.commits = 0

    def collection(self, name):
        return _Ref((name,))

    def batch(self):
        self.commits += 1
        return _Batch(self.written)


def test_conversations_are_encoded_in_batches_and_failures_counted():
    seen = []

    def encode(uid, row, level):
        seen.append((row['id'], level, row.get('open_loop_extractions')))
        if row['id'] == 'bad':
            raise ValueError('manual_speaker_assignments must be an object: detail')
        return {'encoded': True, 'id': row['id']}

    rows = [{'id': f'c{i}', 'data_protection_level': 'enhanced', 'photos': [1]} for i in range(250)]
    rows.append({'id': 'sealed', 'open_loop_extractions': SEALED, 'open_loop_extractions_compressed': True})
    rows.append({'id': 'bad'})
    client = _Client()
    writer = ProductSeedWriter(client)
    written = writer.write_conversations(LAB_UID, rows, SimpleNamespace(encode_conversation_for_write=encode))
    assert written == 251 and len(client.written) == 251
    assert client.commits == 2  # 200 + 51, not one write per row
    assert ('c0', 'enhanced', None) in seen and ('sealed', 'standard', None) in seen
    assert writer.cleared == {'open_loop_extractions': 1}
    assert writer.skipped == {'conversations': {'ValueError: manual_speaker_assignments must be an object': 1}}
    warnings = writer.warnings()
    assert any('1 conversations row(s) not written' in w for w in warnings)
    assert any('open_loop_extractions cleared on 1' in w for w in warnings)


def test_memory_chunk_over_the_entity_limit_is_split_until_it_fits():
    calls = []

    def save(rows):
        calls.append(len(rows))
        if len(rows) > 50:
            raise RuntimeError('400 maximum entity size is 1048576 bytes')
        if any(r.get('id') == 'poison' for r in rows):
            raise RuntimeError('400 maximum entity size is 1048576 bytes')

    writer = ProductSeedWriter(_Client())
    chunk = [{'id': f'm{i}'} for i in range(199)] + [{'id': 'poison'}]
    assert writer.save_memories(save, chunk) == 199
    assert calls[0] == 200 and max(calls[1:]) <= 100
    # Only the single memory that cannot fit on its own is reported.
    assert writer.skipped == {'memories': {'RuntimeError: 400 maximum entity size is 1048576 bytes': 1}}

    other = ProductSeedWriter(_Client())

    def refuse(rows):
        raise PermissionError('denied')

    assert other.save_memories(refuse, [{'id': 'a'}, {'id': 'b'}]) == 0
    assert other.skipped == {'memories': {'PermissionError: denied': 2}}


def test_focused_goal_is_created_in_the_background_then_focused():
    calls = []
    goals_db = SimpleNamespace(
        create_goal=lambda uid, row, **kw: calls.append(('create', row['status'], row.get('focus_rank')))
        or {'goal_id': row['id']},
        focus_goal=lambda uid, goal_id, **kw: calls.append(('focus', goal_id, kw['focus_rank'], kw['idempotency_key'])),
    )
    writer = ProductSeedWriter(_Client())
    writer.write_goal(goals_db, LAB_UID, {'id': 'g1', 'status': 'focused', 'focus_rank': 0})
    writer.write_goal(goals_db, LAB_UID, {'id': 'g2', 'status': 'background', 'focus_rank': None})
    assert calls == [
        ('create', 'background', None),
        ('focus', 'g1', 0, 'pipeline-lab-seed-g1'),
        ('create', 'background', None),
    ]


def test_seed_report_carries_timings_and_warnings():
    class _Writer:
        timings = {'conversations': 1.5}
        skipped = {'goals': {'GoalConflictError': 1}}
        cleared = {}

        def write(self, state):
            return {'goals': 0}

        def warnings(self):
            return ['seed: 1 goals row(s) not written (GoalConflictError)']

    state = SimpleNamespace(report=SimpleNamespace(as_dict=lambda: {'kept': {}}))
    report = seed_start_state(state, _Writer(), reset=lambda: 3)
    assert report['reset_deleted'] == 3
    assert set(report['timings']) == {'reset', 'conversations'}
    assert report['skipped'] == {'goals': {'GoalConflictError': 1}} and 'cleared' not in report
    assert report['warnings'] == ['seed: 1 goals row(s) not written (GoalConflictError)']


def test_reset_uses_recursive_delete_on_a_real_client():
    deleted = []

    class _Doc:
        def delete(self):
            deleted.append('user')

    class _Users:
        def document(self, uid):
            assert uid == LAB_UID
            return _Doc()

    class _BulkClient:
        project = 'demo-omi-local'

        def collection(self, name):
            return _Users()

        def recursive_delete(self, ref):
            deleted.append('tree')
            return 41

    assert reset_lab_user(_BulkClient(), environ=LAB_ENV) == 41
    assert deleted == ['tree', 'user']


def test_peer_probe_sees_a_closed_typesense_port():
    with socket.socket() as server:
        server.bind(('127.0.0.1', 0))
        server.listen(1)
        port = server.getsockname()[1]
        assert peer_listening(('127.0.0.1', port)) is True
    assert peer_listening(('127.0.0.1', port), timeout=0.5) is False  # a closed port refuses at once


def test_discard_stage_reports_entry_warnings_and_timings(tmp_path):
    (tmp_path / 'conversations').mkdir()
    (tmp_path / 'chain_entry.json').write_text(
        json.dumps(
            {
                'engine': 'product',
                'pipeline': 'v3',
                'timings': {'seed': 80.0, 'driver': 400.0},
                'warnings': ['seed: open_loop_extractions cleared on 7 conversation(s)'],
            }
        )
    )
    output, warnings = stage_summary('discard', tmp_path)
    assert output['timings'] == {'seed': 80.0, 'driver': 400.0}
    assert warnings == ['seed: open_loop_extractions cleared on 7 conversation(s)']


def _conv(cid, start, end, **extra):
    return {'id': cid, 'started_at': start, 'finished_at': end, 'structured': {'title': cid}, **extra}


def test_v3_production_rows_sharing_recordings_are_merged_not_missing():
    from testing.pipeline_lab.baseline.compare import baseline_view

    replay = [
        _conv(
            'r1',
            '2026-03-14T09:00:00+00:00',
            '2026-03-14T09:40:00+00:00',
            baseline_id='p1',
            baseline_ids=['p1', 'p2'],
        )
    ]
    production = [
        _conv('p1', '2026-03-14T09:00:00+00:00', '2026-03-14T09:20:00+00:00'),
        _conv('p2', '2026-03-14T09:21:00+00:00', '2026-03-14T09:40:00+00:00'),
        _conv('p3', '2026-03-14T15:00:00+00:00', '2026-03-14T15:30:00+00:00'),
    ]
    view = baseline_view(replay, production)
    by_prod = {row['baseline_id']: row for row in view['conversations'] if row['replay_id'] is None}
    assert by_prod['p2']['status'] == 'merged' and by_prod['p2']['merged_into'] == 'r1'
    assert by_prod['p3']['status'] == 'missing'
    assert view['counts']['merged'] == 1 and view['counts']['missing'] == 1


def test_recording_fate_counts_unclaimed_recordings_without_speech():
    from testing.pipeline_lab.v3.run import recording_fate

    recordings = [{'id': 'a', 'status': 'completed'}, {'id': 'b', 'status': 'completed'}, {'id': 'c'}]
    derived = [{'id': 'd1', 'v3_recording_ids': ['a']}]
    fate = recording_fate(recordings, derived, words={'a': 40, 'b': 0, 'c': 12})
    assert fate['recordings'] == 3 and fate['unclaimed'] == 2 and fate['unclaimed_without_speech'] == 1


def test_reset_clears_the_lab_uid_outside_its_user_tree():
    """A second run of a day found the first run's finalization jobs and daily-summary lock."""
    import hashlib

    from testing.pipeline_lab.seed.writer import reset_lab_state

    hashed = hashlib.sha256(LAB_UID.encode()).hexdigest()
    docs = {
        ('conversation_finalization_jobs', 'job-1'): {'uid': LAB_UID},
        ('conversation_finalization_jobs', 'job-2'): {'uid': 'someone-else'},
        ('dream_due', LAB_UID): {},
        ('batch_pipeline_privacy', hashed): {},
        ('conversation_finalization_projection_shards', 'terminal-0'): {'queued': 3},
        ('memory_guarded', LAB_UID): {},  # a product fence refuses this delete
    }
    deleted = []

    class _Snap:
        def __init__(self, key):
            self.exists = key in docs
            self.reference = _DocRef(key)

    class _DocRef:
        def __init__(self, key):
            self.key = key

        def get(self):
            return _Snap(self.key)

        def delete(self):
            if self.key[0] == 'memory_guarded':
                raise ValueError('authority must survive deletion')
            docs.pop(self.key, None)
            deleted.append(self.key)

    class _Query:
        def __init__(self, name, value):
            self.name, self.value = name, value

        def stream(self):
            return [_Snap(k) for k, v in list(docs.items()) if k[0] == self.name and v.get('uid') == self.value]

    class _Coll:
        def __init__(self, name):
            self.id = name

        def where(self, *, filter):
            return _Query(self.id, filter.value)

        def document(self, doc_id):
            return _DocRef((self.id, doc_id))

    class _Users:
        def document(self, uid):
            return SimpleNamespace(delete=lambda: deleted.append(('users', uid)))

    class _Client:
        project = 'demo-omi-local'

        def collections(self):
            return [_Coll('users')] + [_Coll(n) for n in sorted({k[0] for k in docs})]

        def collection(self, name):
            return _Users() if name == 'users' else _Coll(name)

        def recursive_delete(self, ref):
            return 0

    class _Redis:
        def __init__(self):
            self.keys = {
                f'users:{LAB_UID}:daily_summary_lock:2026-03-14',
                f'episodes:client_seen:{LAB_UID}',
                f'external-action-items:v1:{{{hashed}}}',
                'users:someone-else:name',
            }

        def scan_iter(self, match, count):
            needle = match.strip('*')
            return [k for k in sorted(self.keys) if needle in k]

        def delete(self, *keys):
            self.keys -= set(keys)
            return len(keys)

    redis = _Redis()
    counts = reset_lab_state(_Client(), redis, environ=LAB_ENV)
    assert counts['redis'] == 3 and redis.keys == {'users:someone-else:name'}
    assert set(docs) == {
        ('conversation_finalization_jobs', 'job-2'),
        ('conversation_finalization_projection_shards', 'terminal-0'),
        ('batch_pipeline_privacy', hashed),  # the product keeps this authority through deletion
        ('memory_guarded', LAB_UID),
    }
    assert counts['top_level'] == 2 and counts['refused'] == 1
