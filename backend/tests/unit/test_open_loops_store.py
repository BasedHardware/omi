"""Open-loop store rules: identity, expiry, dedupe, cooldown, ranking, persistence.

Pure-logic coverage for ``utils/open_loops/store.py`` plus the encrypted
at-rest contract of ``database/open_loops.py`` (loop docs and the per-day
cards doc are one protected JSON blob each — never plaintext in Firestore).
"""

from datetime import date, datetime, timedelta, timezone

import database.open_loops as open_loops_db
from tests.support.open_loops_store_fake import FakeFirestore
from utils.open_loops import store

TODAY = date(2026, 10, 26)  # Monday
NOW = datetime(2026, 10, 26, 14, 0, tzinfo=timezone.utc)


def _loop(**overrides):
    loop = {
        'id': store.stable_key('owed_to_user', 'Maya', 'send the vendor write-up'),
        'stable_key': store.stable_key('owed_to_user', 'Maya', 'send the vendor write-up'),
        'kind': 'owed_to_user',
        'who': 'Maya',
        'what': 'send the vendor write-up',
        'by_when': None,
        'evidence': 'I will send it over tomorrow',
        'status': 'opened',
        'history': [{'date': '2026-10-20', 'status': 'opened', 'evidence': 'asked Maya'}],
        'times_surfaced': 0,
        'created_at': '2026-10-20T09:00:00+00:00',
        'last_activity_at': '2026-10-20T09:00:00+00:00',
        'source_conversation_ids': ['c1'],
        'source_title': 'Pricing sync',
    }
    loop.update(overrides)
    return loop


def test_stable_key_ignores_case_and_punctuation():
    assert store.stable_key('owed_to_user', 'Maya', 'Send the vendor write-up!') == store.stable_key(
        'owed_to_user', 'maya', 'send the  vendor write-up'
    )
    assert store.stable_key('owed_to_user', 'Maya', 'a') != store.stable_key('own_commitment', 'Maya', 'a')


def test_find_task_match_links_paraphrase_and_containment():
    tasks = [
        {'task_id': 't1', 'title': 'Send Tyler the Stably bullets'},
        {'task_id': 't2', 'title': 'send the vendor write-up today please'},
    ]
    # containment: the loop's wording sits inside the longer task title
    assert store.find_task_match({'who': None, 'what': 'send the vendor write-up'}, tasks)['task_id'] == 't2'
    assert store.find_task_match({'who': 'Tyler', 'what': 'send Tyler the Stably bullets'}, tasks)['task_id'] == 't1'
    # unrelated wording is not linked
    assert store.find_task_match({'who': 'Ann', 'what': 'book the dentist'}, tasks) is None


def test_find_task_match_requires_both_thresholds_and_a_compatible_who():
    """The wrong-task completion blocker: "Tyler: send deck" must not link to
    "send deck to investors" — both Jaccard AND containment must pass, and a
    who named on both sides must agree."""
    tasks = [{'task_id': 't-inv', 'title': 'send deck to investors'}]
    # jaccard({tyler,send,deck},{send,deck,investors}) = 0.5 < 0.6: no link
    assert store.find_task_match({'who': 'Tyler', 'what': 'send deck'}, tasks) is None
    # an unattributed short restatement still links by containment — but only
    # ever as an ask-only heuristic link (Done never completes from it)
    assert store.find_task_match({'who': None, 'what': 'send deck'}, tasks)['task_id'] == 't-inv'
    # when both sides name a who, it must be the same person
    assert (
        store.find_task_match(
            {'who': 'Tyler', 'what': 'send deck'}, [{'task_id': 't-ann', 'who': 'Ann', 'title': 'send deck'}]
        )
        is None
    )
    # the same deliverable, same person, still links
    assert (
        store.find_task_match(
            {'who': 'Tyler', 'what': 'send deck'}, [{'task_id': 't-tyler', 'title': 'send deck to Tyler'}]
        )['task_id']
        == 't-tyler'
    )


def test_loops_match_requires_same_who_and_stricter_overlap():
    # "Tyler send deck" vs "Tyler send invoice": two-thirds shared is not a merge
    assert not store.loops_match({'who': 'Tyler', 'what': 'send deck'}, {'who': 'Tyler', 'what': 'send invoice'})
    # a deliverable from Tyler is not a deliverable from Ann
    assert not store.loops_match({'who': 'Tyler', 'what': 'send deck'}, {'who': 'Ann', 'what': 'send deck'})
    # same person, same deliverable in different wording still merges
    assert store.loops_match(
        {'who': 'Maya', 'what': 'send the vendor write-up'}, {'who': 'Maya', 'what': 'send the vendor write-up please'}
    )
    # who absent on one side stays linkable
    assert store.loops_match(
        {'who': None, 'what': 'send the vendor write-up'}, {'who': 'Maya', 'what': 'send the vendor write-up'}
    )


def test_merge_duplicates_never_merges_a_terminal_loop():
    """A closed loop must stay closed: even an exact-wording duplicate writes
    alongside it, never into it."""
    dropped = _loop(id='ol-dropped', status='dropped', who='Tyler', what='send deck')
    fresh = _loop(id='ol-fresh', status='opened', who='Tyler', what='send deck')
    merged = store.merge_duplicates([dropped, fresh])
    assert [loop['id'] for loop in merged] == ['ol-dropped', 'ol-fresh']
    assert [loop['status'] for loop in merged] == ['dropped', 'opened']


def test_remention_blocked_only_within_the_cooldown():
    dropped_recent = _loop(
        status='dropped',
        history=[{'date': (TODAY - timedelta(days=3)).isoformat(), 'status': 'dropped', 'evidence': ''}],
    )
    assert store.remention_blocked(
        [dropped_recent], kind='owed_to_user', who='Maya', what='send the vendor write-up', today=TODAY
    )
    # same follow-up after the cool-off is free to open a NEW loop
    dropped_old = _loop(
        status='dropped',
        history=[{'date': (TODAY - timedelta(days=20)).isoformat(), 'status': 'dropped', 'evidence': ''}],
    )
    assert not store.remention_blocked(
        [dropped_old], kind='owed_to_user', who='Maya', what='send the vendor write-up', today=TODAY
    )
    # an open loop never blocks anything, whatever the wording
    open_loop = _loop()
    assert not store.remention_blocked(
        [open_loop], kind='owed_to_user', who='Maya', what='send the vendor write-up', today=TODAY
    )
    # a different follow-up is never blocked by a terminal one
    assert not store.remention_blocked(
        [dropped_recent], kind='owed_to_user', who='Ann', what='book the dentist', today=TODAY
    )


def test_text_names_task_gates_completion_on_the_card_text():
    title = 'send Tyler the bullets for the Stably write-up'
    assert store.text_names_task('Did you send Tyler the bullets for the Stably write-up? (your task from Thu)', title)
    assert not store.text_names_task('Did you follow up with Tyler?', title)
    assert not store.text_names_task('', title)


def test_card_view_renders_the_task_only_for_strong_links():
    strong = _loop(
        linked_task_id='task-9',
        task_link='model',
        linked_task_title='send Tyler the bullets',
        linked_task_created_at='2026-10-22T09:00:00+00:00',
    )
    view = store.card_view(strong)
    assert view['what'] == 'send Tyler the bullets'  # the task's own description
    assert view['related_task']['opened_on'] == '2026-10-22T09:00:00+00:00'
    heuristic = _loop(linked_task_id='task-9', task_link='heuristic', linked_task_title='send deck to investors')
    view = store.card_view(heuristic)
    assert view['what'] == 'send the vendor write-up'  # the loop's wording, not the task's
    assert 'related_task' not in view


def test_claim_daily_pass_is_atomic_and_bounds_retries():
    fake = FakeFirestore()
    uid, day = 'u1', '2026-10-26'
    # fresh: exactly one of two concurrent claims wins (create-if-absent)
    results = [open_loops_db.claim_daily_pass(uid, day, now=NOW, firestore_client=fake) for _ in range(2)]
    assert results == [True, False]
    # a live claim blocks the retry path too
    assert not open_loops_db.claim_daily_pass(uid, day, now=NOW + timedelta(minutes=5), firestore_client=fake)
    # a failed day releases for exactly one more attempt
    open_loops_db.mark_daily_pass_failed(uid, day, firestore_client=fake)
    assert open_loops_db.claim_daily_pass(uid, day, now=NOW + timedelta(minutes=6), firestore_client=fake)
    # ... and after the second attempt fails, the day is spent
    open_loops_db.mark_daily_pass_failed(uid, day, firestore_client=fake)
    assert not open_loops_db.claim_daily_pass(uid, day, now=NOW + timedelta(minutes=7), firestore_client=fake)
    # a stale claim (abandoned worker) may be taken over once
    stale_fake = FakeFirestore()
    stale_fake.collection('users').document(uid).collection('open_loop_claims').document(day).set(
        {'date': day, 'state': 'claimed', 'attempts': 1, 'updated_at': (NOW - timedelta(hours=1)).isoformat()}
    )
    assert open_loops_db.claim_daily_pass(uid, day, now=NOW, firestore_client=stale_fake)
    # a ran day never pays again
    open_loops_db.mark_daily_pass_ran(uid, day, firestore_client=fake)
    assert not open_loops_db.claim_daily_pass(uid, day, now=NOW + timedelta(hours=2), firestore_client=fake)


def test_merge_duplicates_prefers_the_task_linked_survivor():
    plain = _loop(what='send the vendor write-up')
    linked = _loop(id='task-9', linked_task_id='9', what='send the vendor write-up', times_surfaced=2)
    merged = store.merge_duplicates([plain, linked])
    assert [loop['id'] for loop in merged] == ['task-9']
    assert merged[0]['times_surfaced'] == 2  # counters survive the merge


def test_merge_loop_accumulates_sources_and_keeps_fresher_wording():
    existing = _loop(source_conversation_ids=['c1'])
    incoming = _loop(source_conversation_ids=['c1', 'c2'], evidence='Maya said Friday', by_when='2026-10-30')
    merged = store.merge_loop(existing, incoming)
    assert merged['source_conversation_ids'] == ['c1', 'c2']
    assert merged['evidence'] == 'Maya said Friday'
    assert merged['by_when'] == '2026-10-30'


def test_expiry_windows_by_kind():
    def aged(kind, days):
        last = (TODAY - timedelta(days=days)).isoformat()
        return _loop(kind=kind, last_activity_at=last, status='progressing')

    # issue_or_blocker/default: 7 days
    assert store.expiry_due(aged('issue_or_blocker', 7), TODAY)
    assert not store.expiry_due(aged('issue_or_blocker', 6), TODAY)
    # own_commitment: 10 days
    assert not store.expiry_due(aged('own_commitment', 9), TODAY)
    assert store.expiry_due(aged('own_commitment', 10), TODAY)
    # owed_to_user: 14 days
    assert not store.expiry_due(aged('owed_to_user', 13), TODAY)
    assert store.expiry_due(aged('owed_to_user', 14), TODAY)
    # terminal loops are never re-expired
    assert not store.expiry_due(_loop(status='resolved'), TODAY)


def test_sweep_expires_deletes_and_enforces_the_cap():
    stale = _loop(id='stale', last_activity_at=(TODAY - timedelta(days=20)).isoformat())
    fresh = _loop(id='fresh', last_activity_at=TODAY.isoformat())
    resolved_old = _loop(
        id='done-old',
        status='resolved',
        last_activity_at=(TODAY - timedelta(days=30)).isoformat(),
        history=[{'date': (TODAY - timedelta(days=30)).isoformat(), 'status': 'resolved', 'evidence': ''}],
    )
    resolved_recent = _loop(
        id='done-new',
        status='resolved',
        last_activity_at=(TODAY - timedelta(days=2)).isoformat(),
        history=[{'date': (TODAY - timedelta(days=2)).isoformat(), 'status': 'resolved', 'evidence': ''}],
    )
    writes, deletes = store.sweep([stale, fresh, resolved_old, resolved_recent], TODAY)
    assert deletes == ['done-old']  # terminal docs leave after retention
    assert [w['id'] for w in writes] == ['stale']
    assert writes[0]['status'] == 'expired'

    # cap: with every loop inside the expiry window, the oldest open loops
    # expire first until only OPEN_LOOP_STORE_CAP remain
    many = [
        _loop(id=f'l{i:02d}', last_activity_at=(TODAY - timedelta(days=i % 6)).isoformat())
        for i in range(store.OPEN_LOOP_STORE_CAP + 3)
    ]
    writes, _ = store.sweep(many, TODAY)
    expired = {w['id'] for w in writes if w['status'] == 'expired'}
    assert len(expired) == 3
    # oldest first: day-five loops go before day-four ones
    assert {'l05', 'l11', 'l17'} == expired


def test_open_loop_count_never_exceeds_the_cap():
    # invariants after sweep: open loops <= cap regardless of input size
    many = [_loop(id=f'hot{i}', last_activity_at=(TODAY - timedelta(days=1)).isoformat()) for i in range(200)]
    writes, _ = store.sweep(many, TODAY)
    open_after = sum(1 for loop in many if store.is_open(loop)) - len(writes)
    assert open_after <= store.OPEN_LOOP_STORE_CAP


def test_cooldown_blocks_recent_surface_except_due_soon():
    asked_yesterday = _loop(last_surfaced_at=(TODAY - timedelta(days=1)).isoformat())
    assert not store.surfaceable(asked_yesterday, TODAY)
    asked_yesterday_due = _loop(last_surfaced_at=(TODAY - timedelta(days=1)).isoformat(), status='due_soon')
    assert store.surfaceable(asked_yesterday_due, TODAY)
    asked_three_days_ago = _loop(last_surfaced_at=(TODAY - timedelta(days=2)).isoformat())
    assert store.surfaceable(asked_three_days_ago, TODAY)


def test_terminal_and_snoozed_loops_never_surface():
    assert not store.surfaceable(_loop(status='resolved'), TODAY)
    assert not store.surfaceable(_loop(status='dropped'), TODAY)
    assert not store.surfaceable(_loop(status='expired'), TODAY)
    assert not store.surfaceable(_loop(snoozed_until=(TODAY + timedelta(days=1)).isoformat()), TODAY)
    assert store.surfaceable(_loop(snoozed_until=(TODAY - timedelta(days=1)).isoformat()), TODAY)


def test_select_surface_cards_filters_ranks_and_caps():
    low_value = {'loop': _loop(id='low'), 'value': 2}
    due_soon_low = {'loop': _loop(id='due', status='due_soon'), 'value': 3}
    work = {'loop': _loop(id='work', work_related=True), 'value': 5}
    personal = {'loop': _loop(id='play', work_related=False), 'value': 5}
    personal2 = {'loop': _loop(id='play2', work_related=False), 'value': 4}
    selected = store.select_surface_cards([low_value, due_soon_low, work, personal, personal2], TODAY)
    assert [c['loop']['id'] for c in selected] == ['due', 'work', 'play']
    # a snoozed candidate is filtered even with a high value
    snoozed = {'loop': _loop(id='z', snoozed_until=(TODAY + timedelta(days=1)).isoformat()), 'value': 5}
    assert store.select_surface_cards([snoozed], TODAY) == []


def test_carried_view_and_relevance_put_due_soon_first():
    due = store.carried_view(_loop(status='due_soon', by_when='2026-10-27'), TODAY)
    assert due['status'] == 'due_soon' and due['times_surfaced'] == 0 and due['age_days'] == 6
    ordering = sorted(
        [_loop(id='a', status='stale'), _loop(id='b', status='due_soon'), _loop(id='c', status='opened')],
        key=store.carried_relevance,
    )
    assert [loop['id'] for loop in ordering] == ['b', 'a', 'c']


def test_mark_surfaced_counts_without_faking_activity():
    loop = _loop()
    marked = store.mark_surfaced(loop, TODAY)
    assert marked['times_surfaced'] == 1 and marked['last_surfaced_at'] == TODAY.isoformat()
    assert marked['history'] == loop['history']  # surfacing is not owner follow-up
    assert marked['last_activity_at'] == loop['last_activity_at']


def test_loop_doc_roundtrip_is_encrypted_at_rest():
    fake = FakeFirestore()
    loop = _loop()
    open_loops_db.upsert_loop('u1', loop, firestore_client=fake)
    raw = fake.raw_doc('users', 'u1', 'open_loops', loop['id'])
    blob = raw[open_loops_db.DATA_FIELD]
    assert isinstance(blob, str) and 'Maya' not in blob and 'vendor' not in blob
    assert raw['status'] == 'opened'  # plain triage mirror only
    decoded = open_loops_db.get_loops('u1', firestore_client=fake)
    assert decoded == [loop]


def test_get_loops_skips_undecodable_documents():
    fake = FakeFirestore()
    open_loops_db.upsert_loop('u1', _loop(), firestore_client=fake)
    fake.collection('users').document('u1').collection('open_loops').document('junk').set(
        {'id': 'junk', open_loops_db.DATA_FIELD: 'not-encrypted', open_loops_db.DATA_COMPRESSED_FIELD: True}
    )
    decoded = open_loops_db.get_loops('u1', firestore_client=fake)
    assert [loop['id'] for loop in decoded] and 'junk' not in [loop['id'] for loop in decoded]


def test_cards_doc_roundtrip_and_absence_semantics():
    fake = FakeFirestore()
    assert open_loops_db.get_cards('u1', '2026-10-26', firestore_client=fake) is None  # pass not run
    cards = [{'id': 'ol-1', 'question': 'Did Maya send it?', 'state': 'pending'}]
    open_loops_db.set_cards('u1', '2026-10-26', cards, firestore_client=fake)
    raw = fake.raw_doc('users', 'u1', 'open_loop_cards', '2026-10-26')
    assert 'Did Maya' not in raw[open_loops_db.DATA_FIELD]  # encrypted at rest
    assert open_loops_db.get_cards('u1', '2026-10-26', firestore_client=fake) == cards
    # empty cards still mark the pass as run
    open_loops_db.set_cards('u1', '2026-10-27', [], firestore_client=fake)
    assert open_loops_db.get_cards('u1', '2026-10-27', firestore_client=fake) == []
    assert open_loops_db.get_cards_doc('u1', '2026-10-27', firestore_client=fake) is not None
