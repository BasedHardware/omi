"""Hermetic coverage for scripts/migrate_screen_frames_to_data_plane_bucket.py.

Fakes implement only the Firestore / GCS surface the script uses, with the
semantics it relies on: document-path ordering, projected reads, dotted
update paths, DELETE_FIELD, update-time preconditions, create-only rewrites
and generation-matched deletes.
"""

import json
from datetime import datetime, timezone

import pytest
from google.api_core.exceptions import FailedPrecondition, NotFound, PreconditionFailed
from google.cloud import firestore

import database.screen_frames as screen_frames_db
from scripts import migrate_screen_frames_to_data_plane_bucket as mig

DEV = 'based-hardware-dev-screen-frames'
PROD = 'based-hardware-prod-screen-frames'
PROD_KEY = 'based_hardware_prod_screen_frames'


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


def _get_path(data, dotted):
    node = data
    for part in dotted.split('.'):
        if not isinstance(node, dict) or part not in node:
            return None, False
        node = node[part]
    return node, True


def _set_path(data, dotted, value):
    parts = dotted.split('.')
    node = data
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    if value is firestore.DELETE_FIELD:
        node.pop(parts[-1], None)
    else:
        node[parts[-1]] = value


class Snapshot:
    def __init__(self, ref, data, exists=True):
        self.reference = ref
        self._data = data
        self.exists = exists
        self.update_time = ref.store.times.get(ref.path)

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class DocRef:
    def __init__(self, store, path):
        self.store = store
        self.path = path

    def collection(self, name):
        return Query(self.store, prefix=f'{self.path}/{name}/')

    def get(self, field_paths=None):
        data = self.store.docs.get(self.path)
        if data is None:
            return Snapshot(self, None, exists=False)
        if field_paths is None:
            return Snapshot(self, dict(data))
        projected = {}
        for field in field_paths:
            value, found = _get_path(data, field)
            if found:
                _set_path(projected, field, value)
        return Snapshot(self, projected)

    def update(self, data, option=None):
        if self.path not in self.store.docs:
            raise NotFound('missing')
        if option is not None and option != self.store.times.get(self.path):
            raise FailedPrecondition('stale')
        if self.store.race_on_update.pop(self.path, None):
            self.store.touch(self.path)
            raise FailedPrecondition('raced')
        for key, value in data.items():
            _set_path(self.store.docs[self.path], key, value)
        self.store.touch(self.path)
        self.store.updates.append((self.path, data))

    def delete(self):
        self.store.docs.pop(self.path, None)


class Query:
    def __init__(self, store, *, prefix=None, group=None, start=None, limit=None, where=None):
        self.store, self.prefix, self.group, self.start, self._limit, self._where = (
            store,
            prefix,
            group,
            start,
            limit,
            where,
        )

    def _copy(self, **changes):
        fields = dict(prefix=self.prefix, group=self.group, start=self.start, limit=self._limit, where=self._where)
        fields.update(changes)
        return Query(self.store, **fields)

    def order_by(self, field):
        assert field == '__name__'
        return self

    def select(self, fields):
        return self

    def start_after(self, cursor):
        return self._copy(start=cursor['__name__'].path)

    def limit(self, n):
        return self._copy(limit=n)

    def where(self, field, op, value):
        return self._copy(where=(field, value))

    def stream(self):
        self.store.queries += 1
        paths = sorted(self.store.docs, key=lambda p: p.split('/'))
        out = []
        for path in paths:
            parts = path.split('/')
            if self.group and not (len(parts) >= 2 and parts[-2] == self.group):
                continue
            if self.prefix and not (path.startswith(self.prefix) and '/' not in path[len(self.prefix) :]):
                continue
            if self.start is not None and not path.split('/') > self.start.split('/'):
                continue
            if self._where and self.store.docs[path].get(self._where[0]) != self._where[1]:
                continue
            out.append(DocRef(self.store, path).get())
            if self._limit is not None and len(out) >= self._limit:
                break
        return iter(out)


class FakeFirestore:
    def __init__(self):
        self.docs = {}
        self.times = {}
        self.clock = 0
        self.updates = []
        self.queries = 0
        self.race_on_update = {}

    def touch(self, path):
        self.clock += 1
        self.times[path] = self.clock

    def put(self, path, data):
        self.docs[path] = data
        self.touch(path)

    def document(self, path):
        return DocRef(self, path)

    def collection(self, name):
        return Query(self, prefix=f'{name}/')

    def collection_group(self, name):
        return Query(self, group=name)

    def write_option(self, last_update_time):
        return last_update_time


class Blob:
    def __init__(self, gcs, bucket, name):
        self.gcs, self.bucket, self.name = gcs, bucket, name
        self.generation = None
        self.md5_hash = None

    def _obj(self):
        return self.gcs.objects.get((self.bucket, self.name))

    def reload(self):
        obj = self._obj()
        if obj is None:
            raise NotFound(self.name)
        self.generation, self.md5_hash = obj['generation'], obj['md5']

    def exists(self):
        return self._obj() is not None

    def rewrite(self, source, token=None, if_generation_match=None):
        if if_generation_match == 0 and self._obj() is not None:
            raise PreconditionFailed('exists')
        src = source._obj()
        self.gcs.generation += 1
        self.gcs.objects[(self.bucket, self.name)] = {'md5': src['md5'], 'generation': self.gcs.generation}
        self.generation = self.gcs.generation
        return None, 1, 1

    def delete(self, if_generation_match=None):
        obj = self._obj()
        if obj is None:
            raise NotFound(self.name)
        if if_generation_match is not None and obj['generation'] != if_generation_match:
            raise PreconditionFailed('generation')
        del self.gcs.objects[(self.bucket, self.name)]


class Bucket:
    def __init__(self, gcs, name):
        self.gcs, self.name = gcs, name

    def blob(self, name):
        return Blob(self.gcs, self.name, name)


class FakeGCS:
    def __init__(self):
        self.objects = {}
        self.generation = 100

    def bucket(self, name):
        return Bucket(self, name)

    def put(self, bucket, name, md5='m'):
        self.generation += 1
        self.objects[(bucket, name)] = {'md5': md5, 'generation': self.generation}


ADJ = datetime(2026, 10, 1, tzinfo=timezone.utc)


def _frame(fs, gcs, uid, cid, fid, bucket, *, objects_in=None):
    data = {'id': fid}
    if bucket is not None:
        data['storage_bucket'] = bucket
    fs.put(f'users/{uid}/conversations/{cid}/screen_frames/{fid}', data)
    where = objects_in if objects_in is not None else (bucket or DEV)
    for path in mig.object_paths(uid, cid, fid):
        gcs.put(where, path, md5=f'{fid}-{path[-9:]}')


@pytest.fixture
def world():
    fs, gcs = FakeFirestore(), FakeGCS()
    # u1/c1: dev-stamped + unstamped legacy frames, legacy (dev) markers.
    fs.put(
        'users/u1/conversations/c1',
        {
            'screen_frames_revision': 4,
            'screen_frames_adjudicated_at': ADJ,
            'screen_frames_selection_fingerprint': 'fp-1',
        },
    )
    _frame(fs, gcs, 'u1', 'c1', 'f1', DEV)
    _frame(fs, gcs, 'u1', 'c1', 'f2', None)
    # u1/c2: prod only — untouched.
    fs.put('users/u1/conversations/c2', {})
    _frame(fs, gcs, 'u1', 'c2', 'f3', PROD)
    # u2/c3: mixed — skipped.
    fs.put('users/u2/conversations/c3', {})
    _frame(fs, gcs, 'u2', 'c3', 'f4', DEV)
    _frame(fs, gcs, 'u2', 'c3', 'f5', PROD)
    # u3/c4: dev-stamped, prod already adjudicated it (rejected everything).
    fs.put(
        'users/u3/conversations/c4',
        {
            'screen_frames_env_state': {
                PROD_KEY: {'adjudicated_at': ADJ, 'selection_fingerprint': 'fp-prod', 'revision': 7}
            }
        },
    )
    _frame(fs, gcs, 'u3', 'c4', 'f6', DEV)
    return fs, gcs


def _copy(fs, gcs, tmp_path, apply=True, **kwargs):
    return mig.run_copy(
        fs,
        gcs,
        source=DEV,
        dest=PROD,
        apply=apply,
        state_path=tmp_path / 'state.json',
        journal=mig.Journal(tmp_path / 'journal.jsonl'),
        page_size=2,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_constants_match_the_database_module():
    assert mig.LEGACY_SCREEN_FRAMES_BUCKET == screen_frames_db.LEGACY_SCREEN_FRAMES_BUCKET
    assert mig.ENV_STATE_FIELD == screen_frames_db._ENV_STATE_FIELD
    assert mig.LEGACY_STATE_FIELDS == screen_frames_db._LEGACY_STATE_FIELDS
    assert mig.state_key(PROD) == screen_frames_db._state_key(PROD) == PROD_KEY
    assert mig.FRAMES == screen_frames_db.screen_frames_subcollection


def test_scan_reports_aggregates_only(world):
    fs, _gcs = world
    result = mig.run_scan(fs, source=DEV, dest=PROD, page_size=2)
    assert result['frames_by_class'] == {'source': 3, 'unstamped': 1, 'dest': 2}
    assert result['conversations_to_move'] == 2
    assert result['frames_to_move'] == 3
    assert result['objects_to_move'] == 6
    assert result['conversations_mixed_skipped'] == 1
    assert result['frames_in_mixed_conversations'] == 1
    assert result['users_with_frames_to_move'] == 3
    assert 'u1' not in json.dumps(result)


def test_copy_dry_run_writes_nothing(world, tmp_path):
    fs, gcs = world
    before_docs, before_objects = json.dumps(fs.docs, default=str), dict(gcs.objects)
    result = _copy(fs, gcs, tmp_path, apply=False)
    assert result['frames_to_move'] == 3 and result['conversations_to_move'] == 2
    assert json.dumps(fs.docs, default=str) == before_docs
    assert gcs.objects == before_objects
    assert not (tmp_path / 'journal.jsonl').exists()
    assert not (tmp_path / 'state.json').exists()


def test_copy_moves_objects_repoints_docs_and_carries_markers(world, tmp_path):
    fs, gcs = world
    result = _copy(fs, gcs, tmp_path)
    assert result['frames_moved'] == 3
    assert result['conversations_mixed_skipped'] == 1
    assert result['complete'] is True
    for fid in ('f1', 'f2'):
        assert fs.docs[f'users/u1/conversations/c1/screen_frames/{fid}']['storage_bucket'] == PROD
        for path in mig.object_paths('u1', 'c1', fid):
            assert (PROD, path) in gcs.objects and (DEV, path) in gcs.objects
    # Mixed conversation untouched.
    assert fs.docs['users/u2/conversations/c3/screen_frames/f4']['storage_bucket'] == DEV
    # Legacy (dev) markers carried into the prod bucket's marker, revision bumped past both.
    state = fs.docs['users/u1/conversations/c1']['screen_frames_env_state'][PROD_KEY]
    assert state == {'adjudicated_at': ADJ, 'selection_fingerprint': 'fp-1', 'revision': 5}
    assert screen_frames_db.LEGACY_SCREEN_FRAMES_BUCKET == DEV
    # An existing prod adjudication is kept; only the revision moves.
    state = fs.docs['users/u3/conversations/c4']['screen_frames_env_state'][PROD_KEY]
    assert state == {'adjudicated_at': ADJ, 'selection_fingerprint': 'fp-prod', 'revision': 8}
    ops = [json.loads(line)['op'] for line in (tmp_path / 'journal.jsonl').read_text().splitlines()]
    assert ops.count('copy') == 3 and ops.count('repoint') == 3 and ops.count('markers') == 2


def test_copy_is_idempotent_and_resumes_from_the_cursor(world, tmp_path):
    fs, gcs = world
    first = _copy(fs, gcs, tmp_path, max_conversations=1)
    assert first['frames_moved'] == 2 and first['complete'] is False
    queries_before = fs.queries
    second = _copy(fs, gcs, tmp_path)
    assert second['frames_moved'] == 1 and second['complete'] is True
    assert second['conversations_visited'] == 3  # c2, c3, c4 — c1 is behind the cursor
    assert fs.queries > queries_before
    third = _copy(fs, gcs, tmp_path, rescan=True)
    assert third.get('frames_moved', 0) == 0


def test_copy_resumes_a_half_done_conversation(world, tmp_path):
    fs, gcs = world
    state = tmp_path / 'state.json'
    # A crashed run: f1 already repointed, cursor not advanced, markers not carried.
    fs.docs['users/u1/conversations/c1/screen_frames/f1']['storage_bucket'] = PROD
    for path in mig.object_paths('u1', 'c1', 'f1'):
        gcs.put(PROD, path)
    state.write_text(json.dumps({'cursor': None, 'complete': False, 'in_progress': 'users/u1/conversations/c1'}))
    result = _copy(fs, gcs, tmp_path, max_conversations=1)
    assert result['frames_moved'] == 1
    assert result.get('conversations_mixed_skipped', 0) == 0
    assert fs.docs['users/u1/conversations/c1']['screen_frames_env_state'][PROD_KEY]['adjudicated_at'] == ADJ


def test_copy_skips_frames_with_missing_source_or_conflicting_dest(world, tmp_path):
    fs, gcs = world
    del gcs.objects[(DEV, 'u1/c1/f1_thumb.jpg')]
    gcs.put(PROD, 'u1/c1/f2.jpg', md5='different')
    result = _copy(fs, gcs, tmp_path, max_conversations=1)
    assert result['frames_source_missing'] == 1 and result['frames_dest_conflict'] == 1
    assert fs.docs['users/u1/conversations/c1/screen_frames/f1']['storage_bucket'] == DEV
    assert 'storage_bucket' not in fs.docs['users/u1/conversations/c1/screen_frames/f2']


def test_repoint_retries_a_lost_compare_and_set(world, tmp_path):
    fs, gcs = world
    fs.race_on_update['users/u1/conversations/c1/screen_frames/f1'] = True
    result = _copy(fs, gcs, tmp_path, max_conversations=1)
    assert result['frames_moved'] == 2


def test_rollback_restores_docs_markers_and_deletes_only_our_copies(world, tmp_path):
    fs, gcs = world
    gcs.put(PROD, 'u1/c1/f2.jpg', md5='f2-f2.jpg')  # already present with the same bytes: not ours
    gcs.objects[(PROD, 'u1/c1/f2.jpg')]['md5'] = gcs.objects[(DEV, 'u1/c1/f2.jpg')]['md5']
    _copy(fs, gcs, tmp_path)
    journal = mig.Journal(tmp_path / 'journal.jsonl')
    dry = mig.run_rollback(fs, gcs, dest=PROD, apply=False, journal=journal)
    assert dry['frames_to_restore'] == 3
    result = mig.run_rollback(fs, gcs, dest=PROD, apply=True, journal=journal)
    assert result['frames_restored'] == 3 and result['markers_restored'] == 2
    assert fs.docs['users/u1/conversations/c1/screen_frames/f1']['storage_bucket'] == DEV
    assert 'storage_bucket' not in fs.docs['users/u1/conversations/c1/screen_frames/f2']
    assert 'screen_frames_env_state' not in fs.docs['users/u1/conversations/c1'] or not fs.docs[
        'users/u1/conversations/c1'
    ]['screen_frames_env_state'].get(PROD_KEY)
    assert fs.docs['users/u3/conversations/c4']['screen_frames_env_state'][PROD_KEY]['revision'] == 7
    assert (PROD, 'u1/c1/f1.jpg') not in gcs.objects
    assert (PROD, 'u1/c1/f2.jpg') in gcs.objects  # pre-existing object left alone
    assert (PROD, 'u1/c2/f3.jpg') in gcs.objects
    assert all((DEV, path) in gcs.objects for path in mig.object_paths('u1', 'c1', 'f1'))


def test_rollback_leaves_a_marker_changed_since(world, tmp_path):
    fs, gcs = world
    _copy(fs, gcs, tmp_path)
    fs.docs['users/u1/conversations/c1']['screen_frames_env_state'][PROD_KEY]['revision'] = 99
    result = mig.run_rollback(fs, gcs, dest=PROD, apply=True, journal=mig.Journal(tmp_path / 'journal.jsonl'))
    assert result['markers_changed_since'] == 1


def test_purge_deletes_source_only_for_verified_frames_and_drains_cleanups(world, tmp_path):
    fs, gcs = world
    fs.put(
        'screen_frame_cleanup/x',
        {'bucket': DEV, 'object_paths': ['u9/c9/f9.jpg', 'u9/c9/f9_thumb.jpg']},
    )
    gcs.put(DEV, 'u9/c9/f9.jpg')
    _copy(fs, gcs, tmp_path)
    journal = mig.Journal(tmp_path / 'journal.jsonl')
    del gcs.objects[(PROD, 'u3/c4/f6_thumb.jpg')]  # destination incomplete: keep the source
    dry = mig.run_purge(fs, gcs, source=DEV, dest=PROD, apply=False, journal=journal)
    assert dry['objects_to_purge'] == 4 and dry['cleanups_to_drain'] == 1 and dry['frames_dest_incomplete'] == 1
    result = mig.run_purge(fs, gcs, source=DEV, dest=PROD, apply=True, journal=journal)
    assert result['objects_purged'] == 4 and result['cleanups_drained'] == 1
    assert (DEV, 'u1/c1/f1.jpg') not in gcs.objects
    assert (DEV, 'u3/c4/f6.jpg') in gcs.objects
    assert (DEV, 'u2/c3/f4.jpg') in gcs.objects  # mixed, never copied
    assert (DEV, 'u9/c9/f9.jpg') not in gcs.objects and 'screen_frame_cleanup/x' not in fs.docs
    with pytest.raises(RuntimeError):
        mig.run_rollback(fs, gcs, dest=PROD, apply=True, journal=journal)


def test_cli_guards(tmp_path, monkeypatch):
    monkeypatch.setattr(mig, '_clients', lambda *_a, **_k: pytest.fail('clients must not be built'))
    with pytest.raises(SystemExit):
        mig.main(['copy'])
    with pytest.raises(SystemExit):
        mig.main(['copy', '--journal', str(tmp_path / 'j'), '--apply'])
    with pytest.raises(SystemExit):
        mig.main(['purge-source', '--journal', str(tmp_path / 'j'), '--apply'])
    with pytest.raises(ValueError):
        mig.run_copy(None, None, source=DEV, dest=DEV, apply=False, state_path=None, journal=mig.Journal(None))
