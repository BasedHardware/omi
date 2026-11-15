"""Hermetic source-boundary tests: compact reads, migration and privacy fences."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json

import pytest

from database import home_feed
from utils.home_feed.projection import stamp, reveal_display
from utils.encryption import encrypt

AT = datetime(2026, 11, 15, tzinfo=timezone.utc)


class Snapshot:
    def __init__(self, store, path, fields=None):
        self.reference = Ref(store, path)
        self.id = path.rsplit('/', 1)[-1]
        self.exists = path in store.docs
        self.data = deepcopy(store.docs.get(path, {}))
        if fields is not None:
            # Real Firestore reconstructs nested selected fields. Tests exercise
            # the boundary but retain nested maps for readability.
            roots = {field.split('.')[0] for field in fields}
            self.data = {k: v for k, v in self.data.items() if k in roots}
        self.update_time = store.versions.get(path, AT) if self.exists else None
        self.create_time = AT if self.exists else None

    def to_dict(self):
        return deepcopy(self.data)


class Ref:
    def __init__(self, store, path):
        self.store, self.path = store, path
        self.id = path.rsplit('/', 1)[-1]

    def collection(self, name):
        return Query(self.store, self.path + '/' + name)

    def get(self, field_paths=None, transaction=None):
        if transaction:
            assert not transaction.writes, 'Firestore forbids reads after writes'
        self.store.reads.append((self.path, field_paths))
        return Snapshot(self.store, self.path, field_paths)


class Query:
    def __init__(self, store, path):
        self.store, self.path, self.filters, self.orders = store, path, [], []
        self.cap, self.after, self.fields = 10000, None, None

    def document(self, key):
        return Ref(self.store, self.path + '/' + key)

    def where(self, *, filter):
        self.filters.append((filter.field_path, filter.value))
        return self

    def order_by(self, field, direction=None):
        self.orders.append((field, direction))
        return self

    def limit(self, value):
        self.cap = value
        return self

    def start_after(self, value):
        self.after = value
        return self

    def select(self, fields):
        self.fields = fields
        return self

    def stream(self, transaction=None):
        if transaction:
            assert not transaction.writes
        rows = []
        for path, row in self.store.docs.items():
            if not path.startswith(self.path + '/') or path.count('/') != self.path.count('/') + 1:
                continue
            if not all(row.get(field) == value for field, value in self.filters):
                continue
            if any(field != '__name__' and field not in row for field, _ in self.orders):
                continue
            rows.append(Snapshot(self.store, path, self.fields))

        def key(doc):
            raw = self.store.docs[doc.reference.path]
            return tuple(doc.id if field == '__name__' else raw[field] for field, _ in self.orders)

        reverse = bool(self.orders and self.orders[0][1] == 'DESCENDING')
        rows.sort(key=key, reverse=reverse)
        if self.after:
            after = tuple(
                self.after[field].id if field == '__name__' else self.after[field] for field, _ in self.orders
            )
            rows = [doc for doc in rows if key(doc) < after] if reverse else [doc for doc in rows if key(doc) > after]
        for doc in rows[: self.cap]:
            self.store.reads.append((doc.reference.path, self.fields))
            yield doc


class Tx:
    def __init__(self, store):
        self.store, self.writes = store, []

    def update(self, ref, data):
        assert ref.path in self.store.docs, 'update requires existing source'
        self.writes.append((ref.path, data, True))

    def set(self, ref, data, merge=False):
        self.writes.append((ref.path, data, merge))

    def commit(self):
        for path, data, merge in self.writes:
            self.store.docs[path] = {**(self.store.docs.get(path, {}) if merge else {}), **deepcopy(data)}
            self.store.versions[path] = self.store.versions.get(path, AT) + timedelta(microseconds=1)


class Store:
    def __init__(self):
        self.docs, self.versions, self.reads = {}, {}, []

    def collection(self, name):
        return Query(self, name)

    def put(self, path, data):
        self.docs[path] = data
        self.versions[path] = AT


@pytest.fixture
def store(monkeypatch):
    db = Store()

    def transaction(client, body):
        tx = Tx(client)
        # Match the production runner contract: it receives a Firestore
        # transactional callable, which begins/commits the real SDK transaction.
        assert hasattr(body, 'to_wrap')
        result = body.to_wrap(tx)
        client.last_writes = len(tx.writes)
        tx.commit()
        return result

    monkeypatch.setattr(home_feed, 'run_transactional', transaction)
    return db


def conversation(title='A useful conversation', **extra):
    return dict(
        started_at=AT,
        created_at=AT,
        finished_at=AT + timedelta(minutes=1),
        status='completed',
        record_projection_revision='done',
        structured={'title': title, 'overview': 'Useful notes'},
        **extra,
    )


def drain(store):
    for _ in range(200):
        result = home_feed.prepare('u', firestore_client=store)
        if result['ready']:
            return
    pytest.fail('bounded preparation failed to finish')


def test_prepare_preserves_legacy_missing_started_at_and_late_import_order(store):
    old = conversation('Old imported recording')
    old['started_at'] = AT - timedelta(days=30)
    old['created_at'] = AT + timedelta(days=1)
    store.put('users/u/conversations/old', old)
    missing = conversation('Legacy history')
    missing.pop('started_at')
    store.put('users/u/conversations/legacy', missing)
    with pytest.raises(home_feed.PreparationRequired):
        home_feed.feed('u', firestore_client=store)
    drain(store)
    result = home_feed.feed('u', firestore_client=store)
    assert [item['detail_id'] for item in result['items']] == ['legacy', 'old']
    assert result['has_more'] is False
    assert result['items'][0]['started_at'] is None
    assert result['items'][0]['sort_at'] == AT
    assert result['items'][1]['started_at'] == old['started_at']
    assert 'recorded_start' not in store.docs['users/u/conversations/legacy']


def test_projected_get_never_reads_members_transcripts_or_calls_generation(store, monkeypatch):
    store.put('users/u/conversations/c', conversation())
    drain(store)
    store.reads.clear()
    monkeypatch.setattr(home_feed, 'content', lambda *args: pytest.fail('GET must not build projections'))
    result = home_feed.feed('u', firestore_client=store)
    assert result['items'][0]['title'] == 'A useful conversation'
    source_reads = [(path, fields) for path, fields in store.reads if '/conversations/' in path]
    assert len(source_reads) == 1 and source_reads[0][1] == home_feed.FEED_FIELDS
    assert not any('transcript' in field for field in home_feed.FEED_FIELDS)


def test_legacy_episode_redacts_locked_member_and_suppresses_only_when_group_visible(store):
    store.put('users/u/conversations/c', conversation(is_locked=True, episode_id='e'))
    store.put('users/u/episode_links/c', {'episode_id': 'e'})
    store.put(
        'users/u/episodes/e',
        {'started_at': AT, 'composed_at': AT, 'status': 'closed', 'conversation_ids': ['c'], 'content': 'untrusted'},
    )
    drain(store)
    result = home_feed.feed('u', firestore_client=store)
    assert len(result['items']) == 1
    assert result['items'][0]['kind'] == 'episode'
    assert result['items'][0]['title'] == '' and result['items'][0]['preview'] == ''
    assert result['items'][0]['is_locked'] is True
    unadmitted = home_feed.feed('u', episodes_admitted=False, firestore_client=store)
    assert unadmitted['items'][0]['kind'] == 'conversation'


@pytest.mark.parametrize('unsafe', [None, 'deleted', 'locked', 'edited', 'newer', 'membership', 'invalid_ciphertext'])
def test_legacy_composed_display_requires_unchanged_visible_members(store, monkeypatch, unsafe):
    # Migration's metadata-only writes change Firestore update_time; retain the
    # original source revision across bounded chunks to validate legacy content.
    monkeypatch.setattr(home_feed, 'MEMBERS_PER_PREPARE', 1)
    ids = ['a', 'b']
    for cid in ids:
        store.put(f'users/u/conversations/{cid}', conversation(f'Member {cid}', episode_id='e'))
        store.put(f'users/u/episode_links/{cid}', {'episode_id': 'e'})
    episode = {
        'started_at': AT,
        'status': 'closed',
        'conversation_ids': ids,
        'composed_member_ids': ids,
        'composed_membership': ids,
        'composed_at': AT + timedelta(seconds=1),
        'content': encrypt(json.dumps({'title': 'Saved episode title', 'lede': 'Saved episode preview'}), 'u'),
    }
    member = store.docs['users/u/conversations/b']
    if unsafe == 'deleted':
        member['deleted'] = True
    elif unsafe == 'locked':
        member['is_locked'] = True
    elif unsafe == 'edited':
        member['home_source_version'] = 'changed-after-compose'
    elif unsafe == 'newer':
        store.versions['users/u/conversations/b'] = AT + timedelta(seconds=2)
    elif unsafe == 'membership':
        episode['composed_member_ids'] = ['a']
    elif unsafe == 'invalid_ciphertext':
        episode['content'] = 'invalid-ciphertext'
    store.put('users/u/episodes/e', episode)
    drain(store)
    store.reads.clear()
    card = home_feed.feed('u', firestore_client=store)['items'][0]
    if unsafe is None:
        assert (card['title'], card['preview']) == ('Saved episode title', 'Saved episode preview')
    else:
        assert 'Saved episode' not in card['title'] + card['preview']
    assert not any('content' in (fields or []) for _, fields in store.reads)
    if unsafe is None:
        # A later member edit must revoke the newly established legacy proof.
        member = store.docs['users/u/conversations/b']
        member['home_source_version'] = 'later-edit'
        store.docs['users/u/episode_links/b']['home_dirty'] = True
        store.docs['users/u/episode_links/home_feed_control']['ready'] = False
        drain(store)
        card = home_feed.feed('u', firestore_client=store)['items'][0]
        assert 'Saved episode' not in card['title'] + card['preview']


def test_dirty_deleted_member_cannot_leak_old_episode_text(store):
    store.put('users/u/conversations/c', conversation())
    store.put(
        'users/u/episodes/e', {'started_at': AT, 'composed_at': AT, 'status': 'closed', 'conversation_ids': ['c']}
    )
    store.put('users/u/episode_links/c', {'episode_id': 'e'})
    drain(store)
    store.docs.pop('users/u/conversations/c')
    store.docs['users/u/episode_links/c']['home_dirty'] = True
    store.docs['users/u/episode_links/home_feed_control']['ready'] = False
    drain(store)
    assert home_feed.feed('u', firestore_client=store)['items'] == []


def test_account_deletion_blocks_prepare_and_get_without_any_writes(store):
    store.put('account_deletions/u', {'wipe_status': 'wiping'})
    before = deepcopy(store.docs)
    with pytest.raises(home_feed.AccountUnavailable, match='account_unavailable'):
        home_feed.prepare('u', firestore_client=store)
    with pytest.raises(home_feed.AccountUnavailable, match='account_unavailable'):
        home_feed.feed('u', firestore_client=store)
    assert store.docs == before


def test_projection_content_is_encrypted_and_invalid_ciphertext_never_returns_text():
    row = stamp('u', conversation(), 'conversation')
    assert 'A useful conversation' not in row['home_display']
    assert reveal_display('u', row['home_display'])['title'] == 'A useful conversation'
    assert reveal_display('other', row['home_display']) is None
    assert reveal_display('u', 'not-ciphertext') is None


def test_oversized_episode_finishes_preparation_and_keeps_member_history(store, monkeypatch):
    monkeypatch.setattr(home_feed, 'MAX_MEMBERS', 2)
    monkeypatch.setattr(home_feed, 'PREPARE_LIMIT', 2)
    ids = ['c0', 'c1', 'c2', 'c3', 'c4']
    for cid in ids:
        store.put(f'users/u/conversations/{cid}', conversation(cid, episode_id='e'))
        store.put(f'users/u/episode_links/{cid}', {'episode_id': 'e'})
    store.put('users/u/episodes/e', {'started_at': AT, 'composed_at': AT, 'status': 'closed', 'conversation_ids': ids})
    drain(store)
    result = home_feed.feed('u', firestore_client=store)
    assert {item['detail_id'] for item in result['items']} == set(ids)
    assert all(item['kind'] == 'conversation' for item in result['items'])
    assert store.docs['users/u/episodes/e']['home_compatibility_reason'] == 'membership_budget'


def test_prepared_member_migration_skips_rehydrating_its_episode(store, monkeypatch):
    monkeypatch.setattr(home_feed, 'PREPARE_LIMIT', 1)
    for cid in ['a', 'b']:
        store.put(f'users/u/conversations/{cid}', conversation(cid, episode_id='e'))
        store.put(f'users/u/episode_links/{cid}', {'episode_id': 'e'})
    store.put(
        'users/u/episodes/e', {'started_at': AT, 'composed_at': AT, 'status': 'closed', 'conversation_ids': ['a', 'b']}
    )
    home_feed.prepare('u', firestore_client=store)
    store.reads.clear()
    home_feed.prepare('u', firestore_client=store)
    assert not any(path == 'users/u/episodes/e' for path, _ in store.reads)


def test_deleted_old_cursor_anchor_and_mutation_generation_do_not_invalidate_scope(store):
    for cid in ['a', 'b', 'c']:
        store.put(f'users/u/conversations/{cid}', conversation(cid))
    drain(store)
    page = home_feed.feed('u', limit=1, firestore_client=store)
    assert page['has_more']
    store.docs.pop(f'users/u/conversations/{page["items"][0]["detail_id"]}')
    store.docs['users/u/episode_links/home_feed_control']['generation'] = 'new-generation'
    rest = home_feed.feed('u', limit=10, cursor=page['next_cursor'], firestore_client=store)
    assert len(rest['items']) == 2
    assert rest['generation'] == 'new-generation'


def test_authoritative_owner_change_does_not_show_old_aggregate(store):
    store.put('users/u/conversations/c', conversation(episode_id='new'))
    store.put('users/u/episode_links/c', {'episode_id': 'new'})
    for eid in ['old', 'new']:
        store.put(
            f'users/u/episodes/{eid}',
            {'started_at': AT, 'composed_at': AT, 'status': 'closed', 'conversation_ids': ['c']},
        )
    drain(store)
    assert [item['detail_id'] for item in home_feed.feed('u', firestore_client=store)['items']] == ['new']


def test_normal_large_episode_prepares_in_chunks_and_stays_grouped(store, monkeypatch):
    monkeypatch.setattr(home_feed, 'MEMBERS_PER_PREPARE', 20)
    ids = [f'c{i:03d}' for i in range(120)]
    for cid in ids:
        store.put(f'users/u/conversations/{cid}', conversation(cid, episode_id='e'))
        store.put(f'users/u/episode_links/{cid}', {'episode_id': 'e'})
    store.put('users/u/episodes/e', {'started_at': AT, 'composed_at': AT, 'status': 'closed', 'conversation_ids': ids})
    for _ in range(100):
        store.reads.clear()
        result = home_feed.prepare('u', firestore_client=store)
        assert len(store.reads) <= 400
        assert store.last_writes <= 400
        if result['ready']:
            break
    else:
        pytest.fail('normal large episode never finished')
    page = home_feed.feed('u', firestore_client=store)
    assert len(page['items']) == 1 and page['items'][0]['kind'] == 'episode'
    assert page['items'][0]['member_count'] == 120


def test_episode_hard_delete_recovers_member_conversations(store):
    store.put('users/u/conversations/c', conversation(episode_id='e'))
    store.put('users/u/episode_links/c', {'episode_id': 'e'})
    store.put(
        'users/u/episodes/e', {'started_at': AT, 'composed_at': AT, 'status': 'closed', 'conversation_ids': ['c']}
    )
    drain(store)
    store.docs.pop('users/u/episodes/e')
    store.docs['users/u/episode_links/home_feed_control'].update(ready=False, policy_dirty=True, policy_epoch='delete')
    drain(store)
    assert [item['id'] for item in home_feed.feed('u', firestore_client=store)['items']] == ['conversation:c']


@pytest.mark.parametrize('member', [False, True])
def test_authoritative_visibility_parity_for_failed_short_bridge_and_curated(member):
    failed = conversation()
    failed['status'] = 'failed'
    assert home_feed._visible(failed, episode_member=member) is member
    hidden = conversation(sync_bridge_pending={'expires_at': 9999999999})
    assert not home_feed._visible(hidden, episode_member=member)
    hidden['starred'] = True
    assert home_feed._visible(hidden, episode_member=member)
    floor = conversation(relevance_decision={'reason': 'content_below_floor'})
    assert not home_feed._visible(floor, episode_member=member)
    floor['user_title'] = 'User kept title'
    assert home_feed._visible(floor, episode_member=member)


def test_prepare_reserves_query_limit_before_early_stream_cancel(store, monkeypatch):
    monkeypatch.setattr(home_feed, 'MAX_PREPARE_BYTES', 16000)
    for index in range(50):
        store.put(f'users/u/conversations/c{index:03d}', {**conversation(), 'structured': {'overview': 'x' * 10000}})
    counter = home_feed.WORK.labels(kind='requested_read_upper_bound')
    before = counter._value.get()
    result = home_feed.prepare('u', firestore_client=store)
    requested = counter._value.get() - before
    assert not result['ready']
    assert result['processed'] < 50
    assert 53 <= requested <= home_feed.MAX_PREPARE_READS
    # Only consumed snapshots count as processed; the reservation also includes
    # source snapshots the SDK may have prefetched before iterator cancellation.
    assert requested > len(store.reads)


@pytest.mark.parametrize('live', [False, True])
@pytest.mark.parametrize('composed', [False, True])
@pytest.mark.parametrize('enabled', [False, True])
def test_ready_member_cards_replace_atomically_without_detail_reads(store, monkeypatch, live, composed, enabled):
    monkeypatch.setattr(home_feed, 'home_step_projection_enabled', lambda: enabled)
    # This test owns representation transitions, not the wall-clock age policy.
    monkeypatch.setattr(home_feed.home_step, '_older_than', lambda _anchor, _seconds: False)
    # A one-member prepare budget forces the replacement across chunks. GET
    # must reject every partial state rather than publish both representations.
    monkeypatch.setattr(home_feed, 'MEMBERS_PER_PREPARE', 1)
    for cid, raw in [('ready', conversation()), ('pending', conversation())]:
        raw['episode_id'] = 'e'
        if cid == 'pending':
            raw['status'] = 'processing'
        store.put(f'users/u/conversations/{cid}', raw)
        store.put(f'users/u/episode_links/{cid}', {'episode_id': 'e'})
    episode = {'started_at': AT, 'status': 'live' if live else 'closed', 'conversation_ids': ['ready', 'pending']}
    if composed:
        episode['composed_at'] = AT
    store.put('users/u/episodes/e', episode)
    drain(store)
    store.reads.clear()
    cards = home_feed.feed('u', firestore_client=store)['items']
    separate = enabled and (live or not composed)
    assert {c['kind'] for c in cards} == ({'conversation'} if separate else {'episode'})
    assert len(cards) == (2 if separate else 1)
    assert all(fields == home_feed.FEED_FIELDS for path, fields in store.reads if '/conversations/' in path)
    if separate:
        assert {c['detail_id'] for c in cards} == {'ready', 'pending'}
        episode.update(status='closed', composed_at=AT)
        store.docs['users/u/episodes/e'].update(episode, home_needs_prepare=True, home_content_epoch='composed')
        store.docs['users/u/episode_links/home_feed_control']['ready'] = False
        result = home_feed.prepare('u', firestore_client=store)
        assert not result['ready']
        with pytest.raises(home_feed.PreparationRequired):
            home_feed.feed('u', firestore_client=store)
        drain(store)
        cards = home_feed.feed('u', firestore_client=store)['items']
        assert [(c['kind'], c['member_count']) for c in cards] == [('episode', 2)]


def test_ready_member_policy_rollback_requires_fully_prepared_replacement(store, monkeypatch):
    store.put('users/u/conversations/c', conversation(episode_id='e'))
    store.put('users/u/episode_links/c', {'episode_id': 'e'})
    store.put('users/u/episodes/e', {'started_at': AT, 'status': 'closed', 'conversation_ids': ['c']})
    drain(store)
    assert home_feed.feed('u', firestore_client=store)['items'][0]['kind'] == 'conversation'
    monkeypatch.setattr(home_feed, 'home_step_projection_enabled', lambda: False)
    with pytest.raises(home_feed.PreparationRequired):
        home_feed.feed('u', firestore_client=store)
    drain(store)
    assert home_feed.feed('u', firestore_client=store)['items'][0]['kind'] == 'episode'
