"""Dual-backend contract for task Candidates (ADR-0044 facade + ADR-0002 store port).

`database/candidates.py` is the write path between "the assistant thinks you should do this" and a
task on the user's list. Every mutation it owns runs inside one transaction, and the exhaustive
compatibility scan pages with a cursor. Both shapes are at risk under the facade:

    transaction   Nothing here is a plain write. `create_candidate` reads the idempotency alias, the
                  Candidate, the semantic claim and the already-accepted task before deciding whether
                  to write, merge, or refuse; `resolve_task_candidate` reads the Candidate, the
                  resolution claim and the deterministic task before creating one. A backend that
                  wrote without honouring those reads does not error — it produces a SECOND proposal
                  for a task the user has already been asked about, resets the first-seen time of a
                  proposal on every re-capture, lets a stale worker resolve a Candidate another
                  writer has fenced, and re-arms the integration outbox so an accepted task is
                  delivered downstream twice. Each of those is silent and each is visible to the user
                  as duplicate work.
    cursor        `list_candidates_compatibility_page` pages the whole Candidate collection with
                  `start_after(<last raw snapshot>)`, and its own docstring says why the RAW page size
                  (not the parsed one) is the pagination authority: one malformed row must not make a
                  non-final page look exhausted. A cursor the backend ignores restarts the scan from
                  the top forever — which reads as progress, never terminates, and re-scores the same
                  prefix while the tail of the user's proposals is never reached.

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

BASE = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
GENERATION = 3

# Every collection `database/candidates.py` writes under ``users/<uid>/``. Named once so teardown
# cannot drift from the module: a collection left behind poisons the next run of a SHARED rig.
COLLECTIONS = (
    'candidates',
    'action_items',
    'candidate_integration_outbox',
    'candidate_idempotency_aliases',
    'candidate_pending_claims',
    'candidate_resolution_claims',
    'task_intelligence_control',
)


def _proposal(description: str, **overrides):
    """A task-create proposal, in the strict wire shape the router validates.

    No ``goal_id``/``workstream_id``: those make ``validate_task_relationship_in_transaction`` read
    goals and workstreams this suite is not about. With both None it is a no-op, so the transaction
    under test is the Candidate's own.
    """
    from models.candidate import CandidateCreate

    payload = {
        'subject_kind': 'task',
        'proposed_action': 'create',
        'task_change': {'description': description, 'owner': 'user'},
        'capture_confidence': 0.5,
        'ownership_confidence': 0.5,
        'evidence_refs': [{'kind': 'conversation', 'id': 'conversation-1', 'scope': 'canonical'}],
        'source_surface': 'conversation',
    }
    payload.update(overrides)
    return CandidateCreate.model_validate(payload)


@pytest.fixture
def account(bind_store):
    """One user whose task-intelligence control document declares generation 3."""
    run = uuid.uuid4().hex[:8]
    uid = f'cand-{run}'

    bind_store.set(
        f'users/{uid}/task_intelligence_control/state',
        {'workflow_mode': 'read', 'account_generation': GENERATION},
    )

    yield {'uid': uid, 'run': run, 'store': bind_store}

    for collection in COLLECTIONS:
        for document in bind_store.query(f'users/{uid}/{collection}'):
            bind_store.delete(document.path)


def _documents(account, collection):
    return list(account['store'].query(f"users/{account['uid']}/{collection}"))


def _document(account, collection, document_id):
    stored = account['store'].get(f"users/{account['uid']}/{collection}/{document_id}")
    return stored.data if stored is not None and stored.exists else None


# --- transaction ------------------------------------------------------------------------------------


def test_re_capturing_the_same_proposal_keeps_the_original_first_seen_time(account):
    """The read-before-write, and the only assertion that can see it.

    "One document under one id" proves nothing here: the Candidate id is DERIVED from the idempotency
    key, so a blind `set` that never read anything also lands on one document. What the in-transaction
    read buys is that the second capture returns the INCUMBENT rather than replacing it — so the
    proposal keeps the instant it was first seen. Without it a proposal re-captured by a retry looks
    brand new to every consumer that orders by `created_at`, and the reuse window that stops the same
    task being proposed twice restarts from the retry.
    """
    import database.candidates as candidates_db

    first = candidates_db.create_candidate(
        account['uid'],
        _proposal('Send the budget'),
        idempotency_key='conversation-1:item-1',
        account_generation=GENERATION,
        now=BASE,
    )
    second = candidates_db.create_candidate(
        account['uid'],
        _proposal('Send the budget'),
        idempotency_key='conversation-1:item-1',
        account_generation=GENERATION,
        now=BASE + timedelta(days=1),
    )

    assert second.candidate_id == first.candidate_id
    assert second.created_at == BASE, 'the re-capture replaced the proposal instead of returning it'
    assert _document(account, 'candidates', first.candidate_id)['created_at'] == BASE
    assert len(_documents(account, 'candidates')) == 1


def test_the_same_key_with_a_different_proposal_is_refused_rather_than_overwriting(account):
    """An idempotency key is a promise about ONE request. Re-using it for different content must fail
    loudly: silently overwriting changes the task the user is about to approve after they have seen
    it."""
    import database.candidates as candidates_db

    created = candidates_db.create_candidate(
        account['uid'],
        _proposal('Send the budget'),
        idempotency_key='conversation-1:item-1',
        account_generation=GENERATION,
        now=BASE,
    )

    with pytest.raises(candidates_db.CandidateConflictError):
        candidates_db.create_candidate(
            account['uid'],
            _proposal('Cancel the budget'),
            idempotency_key='conversation-1:item-1',
            account_generation=GENERATION,
            now=BASE,
        )

    stored = _document(account, 'candidates', created.candidate_id)
    assert stored['task_change']['description'] == 'Send the budget'


def test_a_key_already_spent_on_a_proposal_is_refused_even_when_its_alias_is_gone(account):
    """The scenario only the Candidate's own in-transaction read can catch.

    Three reads guard `create_candidate`: the idempotency alias, the Candidate at the id derived from
    the key, and the pending semantic claim. For an ordinary replay all three agree, so removing any
    one alone changes nothing (verified by mutation). They are not one guard, though — the alias lives
    in its own collection with its own lifetime, and once it is gone the Candidate is the last record
    that the key was ever spent. Re-using the key for different content then has to be refused by the
    Candidate read or the proposal the user is about to approve is silently swapped underneath them.
    """
    import database.candidates as candidates_db

    created = candidates_db.create_candidate(
        account['uid'],
        _proposal('Send the budget'),
        idempotency_key='conversation-1:item-1',
        account_generation=GENERATION,
        now=BASE,
    )
    for alias in _documents(account, 'candidate_idempotency_aliases'):
        account['store'].delete(alias.path)

    with pytest.raises(candidates_db.CandidateConflictError):
        candidates_db.create_candidate(
            account['uid'],
            _proposal('Cancel the budget'),
            idempotency_key='conversation-1:item-1',
            account_generation=GENERATION,
            now=BASE + timedelta(days=1),
        )

    stored = _document(account, 'candidates', created.candidate_id)
    assert stored['task_change']['description'] == 'Send the budget'
    assert stored['created_at'] == BASE


def test_two_captures_of_the_same_task_coalesce_into_one_proposal(account):
    """Two DIFFERENT idempotency keys, one semantic identity — the merge the transaction exists for.

    The second capture reads the pending semantic claim, reads the Candidate it points at, and UNIONS
    the annotations onto it instead of writing a new document. A backend that only wrote would leave
    the user with two identical "should I add this task?" cards, and the evidence that justified the
    first one would not be on the second.
    """
    import database.candidates as candidates_db

    first = candidates_db.create_candidate(
        account['uid'],
        _proposal('Send the budget', capture_confidence=0.4),
        idempotency_key='conversation-1:item-1',
        account_generation=GENERATION,
        now=BASE,
    )
    second = candidates_db.create_candidate(
        account['uid'],
        _proposal(
            'Send the budget',
            capture_confidence=0.9,
            evidence_refs=[{'kind': 'conversation', 'id': 'conversation-2', 'scope': 'canonical'}],
        ),
        idempotency_key='conversation-2:item-7',
        account_generation=GENERATION,
        now=BASE + timedelta(minutes=5),
    )

    assert second.candidate_id == first.candidate_id, 'the same task was proposed twice'
    assert len(_documents(account, 'candidates')) == 1

    stored = _document(account, 'candidates', first.candidate_id)
    assert {ref['id'] for ref in stored['evidence_refs']} == {'conversation-1', 'conversation-2'}
    assert stored['capture_confidence'] == 0.9, 'the stronger capture confidence must win the merge'


def test_replaying_a_capture_the_user_already_rejected_does_not_re_propose_it(account):
    """The one scenario only the idempotency-alias read can catch.

    Two guards sit at the top of `create_candidate`: the alias, and the Candidate at the id derived
    from the key. For a plain replay they agree, so removing either alone changes nothing. They part
    company after a coalesce, because the alias for the SECOND key points at the FIRST Candidate,
    which the derived id does not. Reject that Candidate and replay the second key: the semantic claim
    no longer offers reuse (a rejected proposal is not reusable), so without the alias the module
    creates a fresh pending Candidate and the user is asked again about the exact suggestion they just
    turned down.
    """
    import database.candidates as candidates_db
    from models.candidate import CandidateStatus

    first = candidates_db.create_candidate(
        account['uid'],
        _proposal('Send the budget'),
        idempotency_key='conversation-1:item-1',
        account_generation=GENERATION,
        now=BASE,
    )
    coalesced = candidates_db.create_candidate(
        account['uid'],
        _proposal('Send the budget', capture_confidence=0.6),
        idempotency_key='conversation-2:item-7',
        account_generation=GENERATION,
        now=BASE + timedelta(minutes=5),
    )
    assert coalesced.candidate_id == first.candidate_id, 'precondition: the second capture coalesced'

    candidates_db.resolve_candidate_without_mutation(
        account['uid'],
        first.candidate_id,
        status=CandidateStatus.rejected,
        reason='user_rejected',
        account_generation=GENERATION,
        now=BASE + timedelta(minutes=10),
    )

    replay = candidates_db.create_candidate(
        account['uid'],
        _proposal('Send the budget', capture_confidence=0.6),
        idempotency_key='conversation-2:item-7',
        account_generation=GENERATION,
        now=BASE + timedelta(minutes=15),
    )

    assert replay.candidate_id == first.candidate_id
    assert replay.status == CandidateStatus.rejected, 'the replay resurrected a rejected proposal'
    assert len(_documents(account, 'candidates')) == 1


def test_a_distinct_task_is_not_coalesced_into_the_first(account):
    """The other half of the claim: coalescing is keyed on the task, not on the user. A different
    description is different work and must survive as its own proposal."""
    import database.candidates as candidates_db

    first = candidates_db.create_candidate(
        account['uid'],
        _proposal('Send the budget'),
        idempotency_key='conversation-1:item-1',
        account_generation=GENERATION,
        now=BASE,
    )
    second = candidates_db.create_candidate(
        account['uid'],
        _proposal('Book the venue'),
        idempotency_key='conversation-1:item-2',
        account_generation=GENERATION,
        now=BASE + timedelta(minutes=1),
    )

    assert second.candidate_id != first.candidate_id
    assert len(_documents(account, 'candidates')) == 2


def test_accepting_a_proposal_creates_exactly_one_task_and_one_dispatch(account):
    """The whole resolution is one transaction: read the Candidate, read the resolution claim, read the
    deterministic task, then write the task, flip the Candidate, and arm the integration outbox. If any
    of that landed without the others the user would see a task with no proposal behind it, or an
    accepted proposal with no task."""
    import database.candidates as candidates_db
    from models.candidate import CandidateStatus

    candidate = candidates_db.create_candidate(
        account['uid'],
        _proposal('Send the budget'),
        idempotency_key='conversation-1:item-1',
        account_generation=GENERATION,
        now=BASE,
    )

    receipt = candidates_db.resolve_task_candidate(
        account['uid'], candidate.candidate_id, account_generation=GENERATION, now=BASE + timedelta(minutes=1)
    )

    assert receipt.newly_resolved is True
    assert receipt.status == CandidateStatus.accepted

    task = _document(account, 'action_items', receipt.task_id)
    assert task is not None and task['description'] == 'Send the budget'
    assert task['candidate_id'] == candidate.candidate_id
    assert _document(account, 'candidates', candidate.candidate_id)['status'] == 'accepted'
    assert _document(account, 'candidate_integration_outbox', candidate.candidate_id)['status'] == 'pending'


def test_re_accepting_a_proposal_does_not_re_arm_the_integration_dispatch(account):
    """The consequence a "one task exists" assertion cannot see.

    The task id is derived from the Candidate id, so a resolve that never read would still write ONE
    task document — the assertion would pass while the bug shipped. What it would also do is re-set the
    outbox row to `pending`, and the downstream integration would deliver the same accepted task a
    second time. So drive the outbox into `processing` first and assert the retry leaves it there.
    """
    import database.candidates as candidates_db

    candidate = candidates_db.create_candidate(
        account['uid'],
        _proposal('Send the budget'),
        idempotency_key='conversation-1:item-1',
        account_generation=GENERATION,
        now=BASE,
    )
    first = candidates_db.resolve_task_candidate(
        account['uid'], candidate.candidate_id, account_generation=GENERATION, now=BASE + timedelta(minutes=1)
    )
    lease = candidates_db.claim_candidate_integration_dispatch(
        account['uid'], candidate.candidate_id, account_generation=GENERATION, now=BASE + timedelta(minutes=2)
    )
    assert lease is not None

    second = candidates_db.resolve_task_candidate(
        account['uid'], candidate.candidate_id, account_generation=GENERATION, now=BASE + timedelta(minutes=3)
    )

    assert second.newly_resolved is False
    assert second.task_id == first.task_id
    dispatch = _document(account, 'candidate_integration_outbox', candidate.candidate_id)
    assert dispatch['status'] == 'processing', 'the retry re-armed a dispatch that is already in flight'
    assert dispatch['attempt_count'] == 1
    assert len(_documents(account, 'action_items')) == 1


def test_a_fenced_proposal_cannot_be_resolved_by_another_writer(account):
    """The legacy promotion path claims a Candidate before it mutates task state. A resolver that
    ignored the claim would create a second task for work the claim holder is already committing."""
    import database.candidates as candidates_db

    candidate = candidates_db.create_candidate(
        account['uid'],
        _proposal('Send the budget'),
        idempotency_key='conversation-1:item-1',
        account_generation=GENERATION,
        now=BASE,
    )
    token = candidates_db.claim_candidate_for_legacy_promotion(
        account['uid'], candidate.candidate_id, account_generation=GENERATION, now=BASE
    )
    assert token

    with pytest.raises(candidates_db.CandidateConflictError):
        candidates_db.resolve_task_candidate(
            account['uid'], candidate.candidate_id, account_generation=GENERATION, now=BASE + timedelta(seconds=1)
        )

    assert _document(account, 'candidates', candidate.candidate_id)['status'] == 'pending'
    assert _documents(account, 'action_items') == []


def test_an_expired_fence_does_not_block_the_next_writer_forever(account):
    """The other side of the fence: a lease that has run out must not pin the Candidate. A claim that
    outlived its holder would leave the proposal permanently unresolvable and the task never created."""
    import database.candidates as candidates_db

    candidate = candidates_db.create_candidate(
        account['uid'],
        _proposal('Send the budget'),
        idempotency_key='conversation-1:item-1',
        account_generation=GENERATION,
        now=BASE,
    )
    candidates_db.claim_candidate_for_legacy_promotion(
        account['uid'], candidate.candidate_id, account_generation=GENERATION, now=BASE, lease_seconds=60
    )

    receipt = candidates_db.resolve_task_candidate(
        account['uid'], candidate.candidate_id, account_generation=GENERATION, now=BASE + timedelta(minutes=5)
    )

    assert receipt.newly_resolved is True


def test_an_in_flight_dispatch_is_not_handed_to_a_second_worker(account):
    """The outbox lease, read and written in one transaction. Two holders means the accepted task is
    pushed downstream twice; a completion accepted from a worker that no longer holds the lease means
    the live attempt is marked done and its result is dropped."""
    import database.candidates as candidates_db

    candidate = candidates_db.create_candidate(
        account['uid'],
        _proposal('Send the budget'),
        idempotency_key='conversation-1:item-1',
        account_generation=GENERATION,
        now=BASE,
    )
    candidates_db.resolve_task_candidate(
        account['uid'], candidate.candidate_id, account_generation=GENERATION, now=BASE
    )

    lease = candidates_db.claim_candidate_integration_dispatch(
        account['uid'], candidate.candidate_id, account_generation=GENERATION, now=BASE, lease_seconds=300
    )
    second = candidates_db.claim_candidate_integration_dispatch(
        account['uid'],
        candidate.candidate_id,
        account_generation=GENERATION,
        now=BASE + timedelta(seconds=30),
        lease_seconds=300,
    )

    assert lease is not None
    assert second is None, 'a second worker took a dispatch that is still leased'

    assert (
        candidates_db.complete_candidate_integration_dispatch(
            account['uid'],
            candidate.candidate_id,
            account_generation=GENERATION,
            lease_token='not-the-holder',
            succeeded=True,
        )
        is False
    )
    assert (
        candidates_db.complete_candidate_integration_dispatch(
            account['uid'],
            candidate.candidate_id,
            account_generation=GENERATION,
            lease_token=lease,
            succeeded=True,
        )
        is True
    )
    assert _document(account, 'candidate_integration_outbox', candidate.candidate_id)['status'] == 'completed'


def test_a_write_for_a_retired_account_generation_is_refused(account):
    """Every transaction in the module opens by reading the control document. The generation is how a
    wiped-and-restarted account keeps the old account's in-flight proposals out: a write that skipped
    the check would resurrect them into the fresh account."""
    import database.candidates as candidates_db

    with pytest.raises(candidates_db.CandidateGenerationMismatchError):
        candidates_db.create_candidate(
            account['uid'],
            _proposal('Send the budget'),
            idempotency_key='conversation-1:item-1',
            account_generation=GENERATION + 1,
            now=BASE,
        )

    assert _documents(account, 'candidates') == []


# --- cursor -----------------------------------------------------------------------------------------


def _seed_scan(account, total=5):
    """`total` Candidates with distinct created_at, so the (created_at DESC, __name__) keyset is total.

    Distinct DESCRIPTIONS as well: identical ones would coalesce into a single proposal through the
    semantic claim, and the scan would have nothing to page.
    """
    import database.candidates as candidates_db

    return [
        candidates_db.create_candidate(
            account['uid'],
            _proposal(f'task {index}'),
            idempotency_key=f'scan:{index}',
            account_generation=GENERATION,
            now=BASE + timedelta(minutes=index),
        ).candidate_id
        for index in range(total)
    ]


def test_the_compatibility_scan_pages_without_repeating_or_skipping(account):
    """Five Candidates, two at a time. The three pages must together yield five DISTINCT ids: a cursor
    the backend ignores returns the same first page forever, which the caller reads as progress and
    never finishes — the compatibility rescore loops on the newest two proposals and the rest are never
    scored."""
    import database.candidates as candidates_db

    seeded = set(_seed_scan(account))

    seen: list[str] = []
    cursor = None
    for _page in range(3):
        records, raw, cursor = candidates_db.list_candidates_compatibility_page(
            account['uid'], account_generation=GENERATION, limit=2, cursor=cursor
        )
        assert raw == len(records)
        seen.extend(record.candidate_id for record in records)

    assert len(seen) == len(set(seen)), 'a later page repeated a Candidate from an earlier one'
    assert set(seen) == seeded


def test_the_compatibility_scan_reports_exhaustion_at_the_tail(account):
    """A short page is how the caller knows to stop. Reporting a full one at the tail is an endless
    scan; reporting a short one early stops before the oldest proposal."""
    import database.candidates as candidates_db

    seeded = _seed_scan(account)

    records, raw, cursor = candidates_db.list_candidates_compatibility_page(
        account['uid'], account_generation=GENERATION, limit=50
    )

    assert raw == len(seeded)
    assert {record.candidate_id for record in records} == set(seeded)

    tail, tail_raw, tail_cursor = candidates_db.list_candidates_compatibility_page(
        account['uid'], account_generation=GENERATION, limit=50, cursor=cursor
    )
    assert (tail, tail_raw, tail_cursor) == ([], 0, None)


def test_a_malformed_row_does_not_make_a_full_page_look_exhausted(account):
    """The module's own reason for returning the RAW page size next to the parsed records.

    `parse_snapshots` drops a document it cannot validate. If the caller paginated on the PARSED count,
    a page of two containing one corrupt row would look like a final page of one and every later
    proposal would be invisible to the compatibility scan. The raw count and the raw-snapshot cursor
    are what keep the scan going past the corruption.
    """
    import database.candidates as candidates_db

    seeded = _seed_scan(account, total=3)
    corrupt_id = f"broken-{account['run']}"
    account['store'].set(
        f"users/{account['uid']}/candidates/{corrupt_id}",
        {
            'candidate_id': corrupt_id,
            'account_generation': GENERATION,
            'created_at': BASE + timedelta(minutes=10),
            'subject_kind': 'task',
        },
    )

    records, raw, cursor = candidates_db.list_candidates_compatibility_page(
        account['uid'], account_generation=GENERATION, limit=2
    )

    assert raw == 2, 'the corrupt row must still count against the page'
    assert len(records) == 1, 'precondition: the corrupt row is dropped by the read boundary'

    # Bounded, and the bound is part of the assertion: four rows at two per page is three pages
    # including the short one. A scan that needs more than that is not paging, and a `while` here would
    # hang the suite instead of reporting it.
    remaining: set[str] = {record.candidate_id for record in records}
    pages = 1
    while cursor is not None and raw == 2:
        assert pages < 3, 'the scan is not advancing — it re-read a page it had already consumed'
        records, raw, cursor = candidates_db.list_candidates_compatibility_page(
            account['uid'], account_generation=GENERATION, limit=2, cursor=cursor
        )
        remaining.update(record.candidate_id for record in records)
        pages += 1

    assert remaining == set(seeded), 'the scan stopped at the corrupt row and never reached the tail'


def test_the_scan_keeps_its_generation_filter_on_every_page(account):
    """Filter and cursor compose, or they do not. A backend that dropped the equality filter once the
    keyset was applied would start handing the compatibility scan proposals from the account the user
    already wiped."""
    import database.candidates as candidates_db

    seeded = set(_seed_scan(account, total=3))
    stranger = f"old-{account['run']}"
    account['store'].set(
        f"users/{account['uid']}/candidates/{stranger}",
        {
            'candidate_id': stranger,
            'account_generation': GENERATION - 1,
            'created_at': BASE - timedelta(days=1),
            'subject_kind': 'task',
            'proposed_action': 'create',
            'task_change': {'description': 'from the old account', 'owner': 'user'},
            'capture_confidence': 0.5,
            'ownership_confidence': 0.5,
            'evidence_refs': [{'kind': 'conversation', 'id': 'conversation-old', 'scope': 'canonical'}],
            'source_surface': 'conversation',
            'status': 'pending',
            'idempotency_key': 'idem_old',
        },
    )

    # One row per page, four pages to drain three Candidates and see the empty tail. The bound is an
    # assertion, not a safety net: a cursor the backend ignores would otherwise spin here forever.
    seen: set[str] = set()
    cursor = None
    for page in range(4):
        records, raw, cursor = candidates_db.list_candidates_compatibility_page(
            account['uid'], account_generation=GENERATION, limit=1, cursor=cursor
        )
        seen.update(record.candidate_id for record in records)
        if raw < 1:
            break
        assert page < 3, 'the scan never reached its tail — the cursor is not advancing'

    assert seen == seeded
    assert stranger not in seen
