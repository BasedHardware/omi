"""Paid notes must pass the member visibility snapshot fence before publication."""

from datetime import timedelta
from types import SimpleNamespace

import pytest

from config import episodes as config
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreDocument
from tests.unit.test_episode_composer import UID, T0, _c, _episode, _row
from utils.episodes import composer


@pytest.fixture
def paid_store(monkeypatch):
    for name in (
        config.EPISODE_COMPOSER_ENV,
        config.EPISODE_COMPOSE_SETTLE_ENABLED_ENV,
        config.EPISODE_COMPOSER_THRIFT_ENV,
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(composer, 'episode_single_member_compose_enabled', lambda: False)
    monkeypatch.setattr(composer, 'episode_late_compose_enabled', lambda: False)
    for name in ('_deferred', '_recent'):
        monkeypatch.setattr(composer, name, {})
    for name in ('_foreground', '_inflight', '_rerun'):
        monkeypatch.setattr(composer, name, set())
    episode_path = ('users', UID, 'episodes', 'ep1')
    member_paths = {cid: ('users', UID, 'conversations', cid) for cid in ('c1', 'c2')}
    rows = [_row('c1', T0, 180), _row('c2', T0 + timedelta(minutes=181), 8)]
    end = T0 + timedelta(minutes=189)
    episode = _episode(last_activity_at=end, member_activity={'c1': T0 + timedelta(minutes=180), 'c2': end})
    db = StrictFirestore(
        {episode_path: composer.episodes_db.seal(UID, episode), **{member_paths[r['id']]: r for r in rows}}
    )
    revisions = {path: T0 for path in member_paths.values()}
    reads = []
    original_get = StrictFirestoreDocument.get

    def get(ref, transaction=None, **kwargs):
        snapshot = original_get(ref, transaction=transaction, **kwargs)
        snapshot.update_time = revisions.get(ref.path)
        if ref.path in revisions:
            reads.append((ref.path, transaction))
        return snapshot

    monkeypatch.setattr(StrictFirestoreDocument, 'get', get)

    def read_member(uid, cid, *, firestore_client=None):
        ref = db.collection('users').document(uid).collection('conversations').document(cid)
        return composer.conversations_db.document_data_with_revision(ref.get())

    monkeypatch.setattr(composer.conversations_db, 'get_conversation', read_member)
    calls = []
    c = _c(calls=calls)
    c.firestore_client = db
    return SimpleNamespace(
        db=db, c=c, calls=calls, revisions=revisions, episode_path=episode_path, paths=member_paths, reads=reads
    )


def _episode_now(s):
    return composer.episodes_db.get_episode(UID, 'ep1', firestore_client=s.db)


@pytest.mark.parametrize('fallback', [False, True])
def test_unchanged_paid_members_write_in_the_same_transaction(paid_store, monkeypatch, fallback):
    s = paid_store
    original_update = composer.episodes_db.update_episode
    attempts = []

    def update(*args, **kwargs):
        if 'composed_fingerprint' in kwargs['updates']:
            attempts.append(kwargs)
            if fallback and 'member_activity' in kwargs['updates']:
                raise composer.episodes_db.EpisodeConflict('member_window_refused')
        return original_update(*args, **kwargs)

    monkeypatch.setattr(composer.episodes_db, 'update_episode', update)
    assert composer.compose(UID, 'ep1', collaborators=s.c) == 'composed'
    assert len(s.calls) == 1
    assert _episode_now(s)['title'] == 'Omi app bugs and labeling tool'
    assert len(attempts) == (4 if fallback else 1)
    assert all(a['expected_member_revisions'] == {'c1': T0, 'c2': T0} for a in attempts)
    published_tx = s.db.transactions[-1]
    assert all((path, published_tx) in s.reads for path in s.paths.values())


@pytest.mark.parametrize('fallback', [False, True])
@pytest.mark.parametrize('change', ['deleted_document', 'deleted', 'discarded', 'merged', 'revision'])
def test_paid_member_change_between_visibility_read_and_write_is_never_published(
    paid_store, monkeypatch, change, fallback
):
    s = paid_store
    original_update = composer.episodes_db.update_episode
    attempts = []

    def update(*args, **kwargs):
        if 'composed_fingerprint' in kwargs['updates']:
            attempts.append(kwargs)
            if fallback and 'member_activity' in kwargs['updates']:
                raise composer.episodes_db.EpisodeConflict('member_window_refused')
            path = s.paths['c1']
            if change == 'deleted_document':
                del s.db.rows[path]
            elif change == 'merged':
                s.db.rows[path]['sync_merged_into'] = 'other'
            elif change != 'revision':
                s.db.rows[path][change] = True
            s.revisions[path] += timedelta(seconds=1)
        return original_update(*args, **kwargs)

    monkeypatch.setattr(composer.episodes_db, 'update_episode', update)
    assert composer.compose(UID, 'ep1', collaborators=s.c) == 'superseded'
    assert len(attempts) == (4 if fallback else 1)  # no retry of a refused member snapshot
    assert len(s.calls) == 1
    episode = _episode_now(s)
    assert episode['title'] == 'old' and not episode['lede'] and not episode['moments']
    assert not episode.get('composed_fingerprint') and not episode.get('compose_lease')
    assert all('composed_fingerprint' not in row for tx in s.db.transactions for _, row in tx.sets)


@pytest.mark.parametrize('change', ['hidden', 'notes'])
def test_change_during_final_visibility_read_refuses_even_when_fingerprint_was_unchanged(
    paid_store, monkeypatch, change
):
    s = paid_store
    original_read = composer.conversations_db.get_conversation
    reads_after_call = []

    def read(*args, **kwargs):
        if s.calls:
            reads_after_call.append(args[1])
            if len(reads_after_call) == 3:  # _members read both; now the original-member visibility check
                if change == 'hidden':
                    s.db.rows[s.paths['c1']]['discarded'] = True
                else:
                    s.db.rows[s.paths['c1']]['structured']['overview'] = 'Newer visible notes'
                s.revisions[s.paths['c1']] += timedelta(seconds=1)
        return original_read(*args, **kwargs)

    monkeypatch.setattr(composer.conversations_db, 'get_conversation', read)
    assert composer.compose(UID, 'ep1', collaborators=s.c) == 'superseded'
    assert not _episode_now(s).get('composed_fingerprint')
    assert _episode_now(s)['title'] == 'old'
    assert not _episode_now(s).get('compose_lease')
    assert all('composed_fingerprint' not in row for tx in s.db.transactions for _, row in tx.sets)


@pytest.mark.parametrize('boundary', ['write', 'visibility'])
@pytest.mark.parametrize('settle', [True, False])
def test_member_fence_refusal_reuses_bounded_recompose_scheduling(paid_store, monkeypatch, settle, boundary):
    s = paid_store
    # Reach the existing latency cap so the first background attempt is paid.
    assert composer.compose(UID, 'ep1', collaborators=s.c, background=True) == 'settling'
    s.db.rows[s.episode_path]['compose_pending_since'] -= timedelta(minutes=26)
    composer._deferred.clear()
    if not settle:
        monkeypatch.setenv(config.EPISODE_COMPOSE_SETTLE_ENABLED_ENV, 'off')
    original_update = composer.episodes_db.update_episode

    def update(*args, **kwargs):
        if 'composed_fingerprint' in kwargs['updates']:
            s.revisions[s.paths['c1']] += timedelta(seconds=1)
        return original_update(*args, **kwargs)

    if boundary == 'write':
        monkeypatch.setattr(composer.episodes_db, 'update_episode', update)
    else:
        original_read = composer.conversations_db.get_conversation
        visibility_reads = {}

        def read(*args, **kwargs):
            if s.calls:
                call = len(s.calls)
                visibility_reads[call] = visibility_reads.get(call, 0) + 1
                if visibility_reads[call] == 3:  # after both fingerprint snapshot reads
                    s.db.rows[s.paths['c1']]['structured']['overview'] = f'Newer notes {call}'
                    s.revisions[s.paths['c1']] += timedelta(seconds=1)
            return original_read(*args, **kwargs)

        monkeypatch.setattr(composer.conversations_db, 'get_conversation', read)
    monkeypatch.setattr(composer._executor, 'submit', lambda fn: fn())
    outcomes = []
    monkeypatch.setattr(composer.metrics, 'record_compose', lambda result, seconds, **_: outcomes.append(result))
    assert composer.schedule(UID, 'ep1', collaborators=s.c)
    assert len(s.calls) == (1 if settle else 3)
    assert outcomes == (['superseded', 'settling'] if settle else ['superseded'] * 3)
    assert not composer._inflight and not composer._rerun
    assert bool(composer._deferred) is settle
    assert not _episode_now(s).get('composed_fingerprint')
    assert all('composed_fingerprint' not in row for tx in s.db.transactions for _, row in tx.sets)
    if settle:
        assert 590 < composer.settle_delay(_episode_now(s)) <= 600
