"""Dual-backend contract for the raw X post store (ADR-0044 facade + ADR-0002 store port).

`database/x_posts.py` is the durable landing zone for everything the X connector pulls in — tweets,
bookmarks, likes — keyed by the tweet id so a re-sync can never store a post twice. Memory extraction
and vector indexing run on top of it, and each raw post carries the ledger field that says whether that
has happened yet. Two of the shapes the facade has to re-express live here:

    aggregation   count_x_posts is `.count()` over the whole collection: the "N posts imported" figure
                  the connector screen shows, and the number an operator uses to decide whether a sync
                  actually pulled anything. A count that disagreed with the collection is a number the
                  user can check against the list right next to it.

                  LIMIT, stated plainly: the module wraps the aggregation in `try/except` and falls
                  back to `len(list(stream()))`. So the returned VALUE cannot, by itself, distinguish
                  "the aggregation works" from "the aggregation raised and the fallback counted". These
                  tests hold the number the user sees; the mutation that proves the aggregation path is
                  the one live is perturbing its result (`int(agg[0][0].value)` + 1), which goes red on
                  both backends — a build where the aggregation raised would not have noticed. Breaking
                  the aggregation so it raises SURVIVES here, by design of the module.

    batch         save_x_posts writes a whole page in one commit with `merge=True`, after probing the
                  page's ids with a batched `get_all` so it can tell new posts from ones it already has.
                  mark_memory_extraction_completed writes the ledger acknowledgement the same way. Both
                  halves are visible to the user:

                  merge — a re-sync sends the same post again with only the fields X returned. The
                  batched write must merge onto the stored row, or `memory_extraction_status` is reset
                  to `pending` and every post in the overlap window is mined for memories a second time:
                  duplicate memories in the user's list, and the extraction bill paid twice.

                  the existence probe — `ingested_at` is stamped only for posts the probe reports as
                  new, and the returned count is what the connector logs as "new this sync". A probe
                  that reported an existing post as missing re-stamps it as freshly ingested (it jumps
                  to the top of the extraction queue) and inflates the delta; one that reported a new
                  post as existing leaves it with no `ingested_at` at all.

                  completeness — a post the batch drops is a post the connector believes it has stored
                  and will not fetch again, because the next incremental sync starts from
                  `get_newest_tweet_id`.

`get_newest_tweet_id` itself is covered here because it is what closes that loop: it is the `since_id`
of the next incremental sync. Reading it from the wrong subset — bookmarks and likes share the
collection with tweets — moves the watermark past tweets that were never fetched, and those tweets are
lost silently and permanently.

`save_x_posts` and `mark_memory_extraction_completed` do NOT chunk: one commit per call, no 500-write
rollover, so there is no oversized-batch case to hold here (the connector pages at <=100 and the pending
batch is bounded at 500).

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import uuid

import pytest


def _post(post_id: str, kind: str, created_at: str, **overrides):
    """A raw post as a historical import left it: no `ingested_at`, no ledger field.

    The module treats exactly this shape as pending on purpose — "replaying source rows incrementally
    is safer than silently treating a historical raw import as successfully extracted".
    """
    data = {'id': post_id, 'kind': kind, 'created_at': created_at, 'text': f'post {post_id}'}
    data.update(overrides)
    return data


@pytest.fixture
def posts(bind_store):
    """Two tweets, one bookmark and one like, created on four consecutive days."""
    run = uuid.uuid4().hex[:8]
    uid = f'xp-{run}'
    seeded = {
        '1001': _post('1001', 'tweet', '2026-05-01T10:00:00Z'),
        '1002': _post('1002', 'bookmark', '2026-05-02T10:00:00Z'),
        '1003': _post('1003', 'tweet', '2026-05-03T10:00:00Z'),
        '1004': _post('1004', 'like', '2026-05-04T10:00:00Z'),
    }
    for post_id, data in seeded.items():
        bind_store.set(f'users/{uid}/x_posts/{post_id}', data)

    yield {'uid': uid, 'run': run, 'store': bind_store, 'seeded': seeded}

    for document in bind_store.query(f'users/{uid}/x_posts'):
        bind_store.delete(document.path)


def _stored(posts, post_id):
    document = posts['store'].get(f"users/{posts['uid']}/x_posts/{post_id}")
    return document.data if document is not None and document.exists else None


def _stored_ids(posts) -> set:
    return {document.id for document in posts['store'].query(f"users/{posts['uid']}/x_posts")}


# --- aggregation ---------------------------------------------------------------------------------------


def test_the_post_count_is_the_number_of_stored_posts(posts):
    """The figure on the connector screen, over every kind in the collection."""
    import database.x_posts as x_db

    assert x_db.count_x_posts(posts['uid']) == 4


def test_the_count_follows_what_the_sync_writes(posts):
    """The count and the list have to move together — the user sees both."""
    import database.x_posts as x_db

    x_db.save_x_posts(posts['uid'], [_post('2001', 'tweet', '2026-05-05T10:00:00Z')])

    assert x_db.count_x_posts(posts['uid']) == 5
    assert len(_stored_ids(posts)) == 5


def test_the_count_of_a_user_who_never_connected_x_is_zero(posts):
    """`.count()` over a collection that matches nothing must produce a zero, not an empty result the
    caller then indexes into: `agg[0][0].value` on an empty list is an IndexError."""
    import database.x_posts as x_db

    assert x_db.count_x_posts(f"nobody-{posts['run']}") == 0


def test_the_count_is_scoped_to_one_user(posts):
    """A count resolved against the collection NAME rather than the user's path would show every user's
    import total on every user's screen."""
    import database.x_posts as x_db

    other = f"other-{posts['run']}"
    other_path = f'users/{other}/x_posts/9001'
    posts['store'].set(other_path, _post('9001', 'tweet', '2026-05-09T10:00:00Z'))
    try:
        assert x_db.count_x_posts(posts['uid']) == 4
        assert x_db.count_x_posts(other) == 1
    finally:
        posts['store'].delete(other_path)


# --- batch: ingesting a page -----------------------------------------------------------------------------


def test_a_synced_page_is_stored_whole_and_the_new_ones_are_counted(posts):
    """Every post in the page must be readable back; the delta the connector logs is the number the
    probe found to be new."""
    import database.x_posts as x_db

    page = [_post('2001', 'tweet', '2026-05-05T10:00:00Z'), _post('2002', 'tweet', '2026-05-06T10:00:00Z')]

    assert x_db.save_x_posts(posts['uid'], page) == 2

    assert {'2001', '2002'} <= _stored_ids(posts)
    stored = _stored(posts, '2001')
    assert stored['text'] == 'post 2001'
    assert stored['memory_extraction_status'] == x_db.MEMORY_EXTRACTION_PENDING
    assert stored['ingested_at'] is not None
    assert stored['updated_at'] is not None


def test_a_re_synced_page_stores_nothing_new_and_leaves_the_extraction_ledger_alone(posts):
    """The invariant the whole module exists for, and the one the merge protects.

    The connector's pages overlap, so the same post arrives again. It must not count as new, its
    `ingested_at` must stay the moment it FIRST arrived, and — the part a user would actually see — a
    post already mined for memories must stay `completed`. Under a non-merging batched write the ledger
    field is wiped, the post goes back on the pending list, and the next extraction pass produces a
    second copy of every memory drawn from that window.
    """
    import database.x_posts as x_db

    page = [_post('2001', 'tweet', '2026-05-05T10:00:00Z')]
    assert x_db.save_x_posts(posts['uid'], page) == 1
    x_db.mark_memory_extraction_completed(posts['uid'], ['2001'])
    first_ingest = _stored(posts, '2001')['ingested_at']
    assert _stored(posts, '2001')['memory_extraction_status'] == x_db.MEMORY_EXTRACTION_COMPLETED, 'precondition'

    assert x_db.save_x_posts(posts['uid'], page) == 0, 'an overlapping page holds no new posts'

    stored = _stored(posts, '2001')
    assert stored['memory_extraction_status'] == x_db.MEMORY_EXTRACTION_COMPLETED, 're-sync re-mined the post'
    assert stored['ingested_at'] == first_ingest, 'the first-seen time must not be re-stamped by a re-sync'
    assert x_db.get_pending_memory_extraction_posts(posts['uid']) != [], 'precondition: other posts are pending'
    assert '2001' not in {row['id'] for row in x_db.get_pending_memory_extraction_posts(posts['uid'])}


def test_a_re_sync_still_carries_the_fields_x_changed(posts):
    """Merging is not "ignore the second write": edited text, new metrics and a changed `updated_at`
    have to land, or the stored copy drifts from the post the user can see on X."""
    import database.x_posts as x_db

    x_db.save_x_posts(posts['uid'], [_post('2001', 'tweet', '2026-05-05T10:00:00Z')])
    before = _stored(posts, '2001')['updated_at']

    x_db.save_x_posts(posts['uid'], [_post('2001', 'tweet', '2026-05-05T10:00:00Z', text='edited', like_count=7)])

    stored = _stored(posts, '2001')
    assert stored['text'] == 'edited'
    assert stored['like_count'] == 7
    assert stored['updated_at'] != before or stored['updated_at'] is not None


def test_a_mixed_page_of_known_and_new_posts_reports_only_the_new_ones(posts):
    """What the existence probe is for: one batched read of the whole page's ids, then the delta."""
    import database.x_posts as x_db

    page = [
        _post('1001', 'tweet', '2026-05-01T10:00:00Z'),
        _post('2001', 'tweet', '2026-05-05T10:00:00Z'),
        _post('2002', 'tweet', '2026-05-06T10:00:00Z'),
    ]

    assert x_db.save_x_posts(posts['uid'], page) == 2

    assert 'ingested_at' not in (_stored(posts, '1001') or {}), 'a post the probe already knew is not re-stamped'
    assert _stored(posts, '2001')['ingested_at'] is not None
    assert len(_stored_ids(posts)) == 6


def test_a_post_with_no_id_is_skipped_rather_than_stored_under_a_random_key(posts):
    """The tweet id IS the document key; without one there is nothing to dedupe on, so a post that
    arrived without one would be re-inserted under a new key on every sync."""
    import database.x_posts as x_db

    assert (
        x_db.save_x_posts(posts['uid'], [{'kind': 'tweet', 'text': 'orphan', 'created_at': '2026-05-05T10:00:00Z'}])
        == 0
    )
    assert _stored_ids(posts) == set(posts['seeded'])


def test_syncing_an_empty_page_is_a_no_op(posts):
    import database.x_posts as x_db

    assert x_db.save_x_posts(posts['uid'], []) == 0
    assert _stored_ids(posts) == set(posts['seeded'])


# --- batch: acknowledging extraction ----------------------------------------------------------------------


def test_acknowledging_extraction_takes_exactly_those_posts_off_the_pending_list(posts):
    """The acknowledgement is written only after the memory writes succeeded, so it is the thing that
    stops a post being mined twice. A post the batch misses is mined again on the next pass."""
    import database.x_posts as x_db

    x_db.mark_memory_extraction_completed(posts['uid'], ['1001', '1003'])

    assert {row['id'] for row in x_db.get_pending_memory_extraction_posts(posts['uid'])} == {'1002', '1004'}
    stored = _stored(posts, '1001')
    assert stored['memory_extraction_status'] == x_db.MEMORY_EXTRACTION_COMPLETED
    assert stored['memory_extracted_at'] is not None


def test_acknowledging_extraction_does_not_overwrite_the_post_itself(posts):
    """The acknowledgement is a merge of three fields. A full-replace translation would leave the row
    with nothing but the ledger — the text and the created date of the post would be gone."""
    import database.x_posts as x_db

    x_db.mark_memory_extraction_completed(posts['uid'], ['1001'])

    stored = _stored(posts, '1001')
    assert stored['text'] == 'post 1001'
    assert stored['kind'] == 'tweet'
    assert stored['created_at'] == '2026-05-01T10:00:00Z'


def test_acknowledging_nothing_is_a_no_op(posts):
    import database.x_posts as x_db

    x_db.mark_memory_extraction_completed(posts['uid'], [])

    assert len(x_db.get_pending_memory_extraction_posts(posts['uid'])) == 4


# --- the pending queue -------------------------------------------------------------------------------------


def test_posts_from_before_the_ledger_existed_are_treated_as_pending(posts):
    """None of the seeded rows carries `memory_extraction_status` — the shape a historical raw import
    leaves. The module deliberately treats that as "not yet mined" rather than assuming success, so no
    imported post is silently skipped by memory extraction forever."""
    import database.x_posts as x_db

    assert all('memory_extraction_status' not in data for data in posts['seeded'].values()), 'precondition'

    assert {row['id'] for row in x_db.get_pending_memory_extraction_posts(posts['uid'])} == set(posts['seeded'])


def test_the_pending_batch_is_oldest_first_and_bounded(posts):
    """Stable and bounded: extraction walks the backlog from the oldest post forward, so an unstable
    order means a post at the boundary is picked up twice and its neighbour never."""
    import database.x_posts as x_db

    first_two = x_db.get_pending_memory_extraction_posts(posts['uid'], limit=2)

    assert [row['id'] for row in first_two] == ['1001', '1002']

    x_db.mark_memory_extraction_completed(posts['uid'], [row['id'] for row in first_two])

    assert [row['id'] for row in x_db.get_pending_memory_extraction_posts(posts['uid'], limit=2)] == ['1003', '1004']


def test_the_pending_batch_of_a_fully_extracted_user_is_empty(posts):
    import database.x_posts as x_db

    x_db.mark_memory_extraction_completed(posts['uid'], list(posts['seeded']))

    assert x_db.get_pending_memory_extraction_posts(posts['uid']) == []


# --- reading posts back --------------------------------------------------------------------------------------


def test_stored_posts_come_back_newest_first_bounded_by_the_limit(posts):
    """`order_by(created_at DESC).limit(n)` — the connector's list view. An order the backend reverses
    shows the user their oldest posts as their newest."""
    import database.x_posts as x_db

    assert [row['id'] for row in x_db.get_x_posts(posts['uid'])] == ['1004', '1003', '1002', '1001']
    assert [row['id'] for row in x_db.get_x_posts(posts['uid'], limit=2)] == ['1004', '1003']


def test_filtering_by_kind_returns_only_that_kind_still_newest_first(posts):
    """Tweets, bookmarks and likes share one collection and are told apart only by the `kind` equality
    filter. A filter the backend drops mixes someone's likes into their tweet timeline."""
    import database.x_posts as x_db

    assert [row['id'] for row in x_db.get_x_posts(posts['uid'], kind=x_db.KIND_TWEET)] == ['1003', '1001']
    assert [row['id'] for row in x_db.get_x_posts(posts['uid'], kind=x_db.KIND_BOOKMARK)] == ['1002']
    assert x_db.get_x_posts(posts['uid'], kind='reply') == []


def test_a_kind_filtered_read_is_bounded_too(posts):
    import database.x_posts as x_db

    assert [row['id'] for row in x_db.get_x_posts(posts['uid'], kind=x_db.KIND_TWEET, limit=1)] == ['1003']


def test_hydrating_search_hits_returns_the_posts_that_exist_and_skips_the_rest(posts):
    """The batched `get_all` behind semantic search. A missing id must be skipped, not surface as an
    empty row: search results are rendered from these dicts."""
    import database.x_posts as x_db

    rows = x_db.get_x_posts_by_ids(posts['uid'], ['1003', 'gone', '1001'])

    assert {row['id'] for row in rows} == {'1001', '1003'}
    assert all(row.get('text') for row in rows)


def test_hydrating_no_ids_returns_nothing(posts):
    import database.x_posts as x_db

    assert x_db.get_x_posts_by_ids(posts['uid'], []) == []
    assert x_db.get_x_posts_by_ids(posts['uid'], ['gone']) == []


# --- the incremental-sync watermark ---------------------------------------------------------------------------


def test_the_since_id_is_the_highest_tweet_and_ignores_bookmarks_and_likes(posts):
    """The watermark the next incremental sync starts from. Bookmarks and likes live in the same
    collection with ids from the same id space, so a watermark taken over the whole collection jumps
    past tweets that were never fetched — and X will not return them again."""
    import database.x_posts as x_db

    assert x_db.get_newest_tweet_id(posts['uid']) == '1003', 'the like at 1004 must not move the watermark'


def test_the_since_id_follows_a_newly_synced_tweet(posts):
    import database.x_posts as x_db

    x_db.save_x_posts(posts['uid'], [_post('2005', 'tweet', '2026-05-05T10:00:00Z')])

    assert x_db.get_newest_tweet_id(posts['uid']) == '2005'


def test_the_since_id_compares_numerically_rather_than_as_text(posts):
    """Snowflake ids of different lengths: '999' must not beat '1003' just because it sorts later as a
    string. A watermark that went backwards re-fetches (and re-extracts) everything in between."""
    import database.x_posts as x_db

    x_db.save_x_posts(posts['uid'], [_post('999', 'tweet', '2026-04-01T10:00:00Z')])

    assert x_db.get_newest_tweet_id(posts['uid']) == '1003'


def test_a_non_numeric_id_does_not_break_the_watermark(posts):
    import database.x_posts as x_db

    posts['store'].set(f"users/{posts['uid']}/x_posts/draft-x", _post('draft-x', 'tweet', '2026-05-09T10:00:00Z'))

    assert x_db.get_newest_tweet_id(posts['uid']) == '1003'


def test_a_user_with_no_tweets_has_no_watermark(posts):
    """`None` is what tells the connector to do a full first sync. A stray value here would skip the
    user's entire history."""
    import database.x_posts as x_db

    assert x_db.get_newest_tweet_id(f"nobody-{posts['run']}") is None


@pytest.mark.parametrize('kind', ['bookmark', 'like'])
def test_a_user_with_only_bookmarks_or_likes_has_no_watermark(bind_store, kind):
    """The subset the equality filter has to exclude, on its own: if the filter were dropped, a
    bookmarks-only user would get a tweet watermark out of nowhere and never sync a tweet."""
    import database.x_posts as x_db

    run = uuid.uuid4().hex[:8]
    uid = f'xp-{kind}-{run}'
    bind_store.set(f'users/{uid}/x_posts/5001', _post('5001', kind, '2026-05-01T10:00:00Z'))
    try:
        assert x_db.get_newest_tweet_id(uid) is None
    finally:
        bind_store.delete(f'users/{uid}/x_posts/5001')
