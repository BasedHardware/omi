"""Dual-backend contract for task recommendations (ADR-0044 facade + ADR-0002 store port).

`database/task_recommendations.py` persists "what matters now" — the shortlist the product puts in
front of the user, the interventions it attributes their reaction to, and the device context those
decisions were made from. Two of the eight at-risk shapes live here, and they are adjacent: one
`save_projection` call publishes inside a transaction and then prunes inside a batch.

    transaction   Every entry point opens by reading the account-generation control document, and the
                  publishing ones then read what is already stored before deciding to overwrite it.
                  That read is the whole product behaviour: it is what makes a slower evaluation that
                  finishes second lose to the one that finished first (two devices asking at the same
                  moment must converge on ONE shortlist, not flap between two), what keeps an
                  intervention's first-seen time stable across every re-publication so attribution
                  measures the right interval, and what stops a device's context upload from arriving
                  late and rewinding the user's context to an older state. None of those failures
                  raises: they just quietly produce a different, wrong answer.
    batch         After a successful publish, the decision-audit history for that device is pruned in
                  one batch: rows that have expired, and rows past the retention cap. A batch the
                  facade dropped leaves the audit trail growing without bound — every evaluation the
                  user's device has ever run, kept for good, in a collection nobody reads and nothing
                  else trims. The chunking is NOT what these tests hold: neither the emulator nor Mongo
                  enforces Firestore's 500-writes-per-commit limit, so a build that never rolled over
                  passes here too (same as the folders and memories suites). They hold COMPLETENESS —
                  that the rows which should go, go, and the rows which should stay, stay.

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

NOW = datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)
DEVICE = 'device-1'

# `save_projection` defaults to generation 0, and a missing control document parses as generation 0,
# so the default path needs no seed. The generation test seeds a control document that disagrees.
COLLECTIONS = (
    'task_interventions',
    'task_recommendation_projections',
    'task_recommendation_decisions',
    'task_feedback',
    'task_attention_overrides',
    'task_context_snapshots',
    'task_open_loop_snapshots',
    'task_snapshot_receipts',
    'task_intelligence_control',
)


@pytest.fixture
def account(bind_store):
    run = uuid.uuid4().hex[:8]
    uid = f'trec-{run}'

    yield {'uid': uid, 'run': run, 'store': bind_store}

    for collection in COLLECTIONS:
        for document in bind_store.query(f'users/{uid}/{collection}'):
            bind_store.delete(document.path)


def _recommendation(intervention_id: str, **overrides):
    from models.action_item import EvidenceKind, EvidenceRef, EvidenceScope
    from models.task_recommendation import FeedbackSubjectKind, Recommendation, RecommendationSubjectKind

    fields = {
        'intervention_id': intervention_id,
        'output_version': 'output-1',
        'subject_kind': RecommendationSubjectKind.task,
        'subject_id': 'task-1',
        'feedback_subject_kind': FeedbackSubjectKind.task,
        'feedback_subject_id': 'task-1',
        'headline': 'Do the thing',
        'why_now': 'It is ready.',
        'recommended_action': 'Continue',
        'evidence_preview': 'Due soon.',
        'evidence_refs': [EvidenceRef(kind=EvidenceKind.external, id='evidence-1', scope=EvidenceScope.canonical)],
        'dedupe_key': 'task-1:v1',
        'expires_at': NOW + timedelta(minutes=30),
    }
    fields.update(overrides)
    return Recommendation(**fields)


def _projection(evaluation_id: str, *, generated_at=NOW, ttl=timedelta(minutes=30), material=None, recommendations=()):
    from models.task_recommendation import WhatMattersNowProjection

    return WhatMattersNowProjection(
        evaluation_id=evaluation_id,
        output_version=f'output-{evaluation_id}',
        material_version=material or f'material-{evaluation_id}',
        generated_at=generated_at,
        expires_at=generated_at + ttl,
        recommendations=list(recommendations),
    )


def _documents(account, collection):
    return list(account['store'].query(f"users/{account['uid']}/{collection}"))


def _decision_evaluation_ids(account):
    return {
        (document.data or {}).get('evaluation_id') for document in _documents(account, 'task_recommendation_decisions')
    }


def _seed_decision_history(account, total, *, device_scope=DEVICE):
    """`total` audit rows for one device, all still live and all older than a publish at NOW.

    Seeded through the store rather than by publishing `total` times: the retention cap is a property
    of one batch over an existing history, and driving it through the transaction as well would make a
    failure ambiguous about which of the two shapes broke.
    """
    ids = []
    for index in range(total):
        evaluation_id = f'seed-{index:03d}'
        account['store'].set(
            f"users/{account['uid']}/task_recommendation_decisions/decision-{device_scope}-{index:03d}-{account['run']}",
            {
                'device_scope': device_scope,
                'account_generation': 0,
                'evaluation_id': evaluation_id,
                'evaluated_at': NOW - timedelta(minutes=total - index),
                'expires_at': NOW + timedelta(days=30),
                'decisions': [],
            },
        )
        ids.append(evaluation_id)
    return ids


# --- transaction ------------------------------------------------------------------------------------


def test_a_second_evaluation_of_the_same_material_loses_to_the_one_already_published(account):
    """Read-before-write, and the reason the product needs it.

    Two devices ask "what matters now?" at the same moment. Both evaluations reach the same MATERIAL
    version, so both are equally correct — but only one may be published, or the two devices show
    different wording for the same advice and the shortlist flaps every time it is refreshed. The
    transaction reads the stored projection and hands the loser the incumbent. A write that never read
    would let the last writer win, and which one that is depends on network timing.
    """
    import database.task_recommendations as recommendations_db

    first = _projection('eval-1', material='material-shared')
    competing = _projection('eval-2', material='material-shared', generated_at=NOW + timedelta(minutes=1))

    published = recommendations_db.save_projection(account['uid'], device_scope=DEVICE, projection=first, decisions=[])
    runner_up = recommendations_db.save_projection(
        account['uid'], device_scope=DEVICE, projection=competing, decisions=[]
    )

    assert published == first
    assert runner_up == first, 'the second publication of the same material replaced the incumbent'
    assert recommendations_db.get_projection(account['uid'], device_scope=DEVICE, now=NOW) == first


def test_an_evaluation_that_finished_late_does_not_rewind_the_shortlist(account):
    """A slow evaluation completing after a newer one must not be published over it: the user would
    watch their shortlist go backwards to advice that has already been superseded."""
    import database.task_recommendations as recommendations_db

    newer = _projection('eval-new', generated_at=NOW + timedelta(minutes=10))
    older = _projection('eval-old', generated_at=NOW)

    recommendations_db.save_projection(account['uid'], device_scope=DEVICE, projection=newer, decisions=[])
    result = recommendations_db.save_projection(account['uid'], device_scope=DEVICE, projection=older, decisions=[])

    assert result == newer
    assert recommendations_db.get_projection(account['uid'], device_scope=DEVICE, now=NOW) == newer


def test_re_publishing_keeps_the_first_seen_time_of_an_intervention(account):
    """The in-transaction read of the intervention, and the only assertion that can see it.

    "One intervention document per id" proves nothing: the id comes from the recommendation, so a
    blind `set` also lands on one document. What the read buys is `created_at`. Attribution measures
    the interval between the user first being shown a recommendation and their reaction to it; if
    every re-publication resets that instant, the interval is measured from the last refresh and every
    reaction looks instantaneous.
    """
    import database.task_recommendations as recommendations_db

    recommendation = _recommendation(f"intervention-{account['run']}")
    first = _projection('eval-1', recommendations=[recommendation])
    refreshed = _projection('eval-2', generated_at=NOW + timedelta(minutes=31), recommendations=[recommendation])

    recommendations_db.save_projection(account['uid'], device_scope=DEVICE, projection=first, decisions=[])
    recommendations_db.save_projection(account['uid'], device_scope=DEVICE, projection=refreshed, decisions=[])

    stored = recommendations_db.get_intervention(account['uid'], recommendation.intervention_id)

    assert stored is not None
    assert stored['created_at'] == NOW, 'the refresh reset the moment the user was first shown this'
    assert stored['evaluation_id'] == 'eval-2', 'precondition: the refresh really did republish'


def test_a_replayed_intervention_request_is_not_created_a_second_time(account):
    """The idempotency read. A client that retries a request whose response it never saw must get the
    SAME intervention back — a second one would attribute the user's single reaction twice."""
    import database.task_recommendations as recommendations_db
    from models.task_recommendation import FeedbackSubjectKind, InterventionCreate, InterventionSurface

    request = InterventionCreate(
        surface=InterventionSurface.what_matters_now,
        subject_kind=FeedbackSubjectKind.task,
        subject_id='task-1',
        dedupe_key='task-1:v1',
        expires_at=NOW + timedelta(minutes=30),
    )

    record, created = recommendations_db.create_intervention(account['uid'], request, idempotency_key='key-1', now=NOW)
    replay, created_again = recommendations_db.create_intervention(
        account['uid'], request, idempotency_key='key-1', now=NOW + timedelta(minutes=5)
    )

    assert created is True
    assert created_again is False
    assert replay == record
    assert len(_documents(account, 'task_interventions')) == 1


def test_the_same_key_for_a_different_intervention_is_refused(account):
    """An idempotency key stands for ONE request. Re-using it for different content has to fail rather
    than silently rewrite an intervention the user has already been shown."""
    import database.task_recommendations as recommendations_db
    from models.task_recommendation import FeedbackSubjectKind, InterventionCreate, InterventionSurface

    request = InterventionCreate(
        surface=InterventionSurface.what_matters_now,
        subject_kind=FeedbackSubjectKind.task,
        subject_id='task-1',
        dedupe_key='task-1:v1',
        expires_at=NOW + timedelta(minutes=30),
    )
    recommendations_db.create_intervention(account['uid'], request, idempotency_key='key-1', now=NOW)

    with pytest.raises(recommendations_db.IdempotencyConflictError):
        recommendations_db.create_intervention(
            account['uid'],
            request.model_copy(update={'subject_id': 'task-2', 'dedupe_key': 'task-2:v1'}),
            idempotency_key='key-1',
            now=NOW,
        )

    stored = _documents(account, 'task_interventions')
    assert len(stored) == 1
    assert stored[0].data['subject_id'] == 'task-1', 'the replay rewrote the intervention in place'


def test_a_device_context_upload_that_arrives_late_cannot_rewind_the_context(account):
    """Context snapshots are replaced wholesale, so the transaction has to read the stored one first.

    A phone that lost connectivity uploads what it saw ten minutes ago. Accepting it would make the
    recommendations reason about a room the user has already left. The module refuses the older
    snapshot and keeps the newer one; the refusal is explicit so the caller knows nothing was stored.
    """
    import database.task_recommendations as recommendations_db
    from models.task_recommendation import NormalizedContextSnapshot

    newer = NormalizedContextSnapshot(
        device_id=DEVICE,
        snapshot_id='context-new',
        matches=[],
        generated_at=NOW + timedelta(minutes=10),
        expires_at=NOW + timedelta(minutes=40),
    )
    older = newer.model_copy(
        update={'snapshot_id': 'context-old', 'generated_at': NOW, 'expires_at': NOW + timedelta(minutes=30)}
    )

    recommendations_db.replace_context_snapshot(account['uid'], newer, idempotency_key='upload-new')

    with pytest.raises(recommendations_db.StaleSnapshotError):
        recommendations_db.replace_context_snapshot(account['uid'], older, idempotency_key='upload-old')

    stored = recommendations_db.get_context_snapshot(account['uid'], DEVICE, now=NOW + timedelta(minutes=11))
    assert stored is not None and stored.snapshot_id == 'context-new'


def test_a_replayed_context_upload_returns_its_original_receipt(account):
    """The receipt read, and why `replaced` has to come from it.

    The receipt tells the device whether its upload overwrote earlier state. A retry of the SAME upload
    must return the same answer — recomputing it would report `replaced=True` on the retry (the
    snapshot is now there, put there by the first attempt) and the device would conclude it had
    clobbered a peer's context when it had not.
    """
    import database.task_recommendations as recommendations_db
    from models.task_recommendation import NormalizedContextSnapshot

    snapshot = NormalizedContextSnapshot(
        device_id=DEVICE,
        snapshot_id='context-1',
        matches=[],
        generated_at=NOW,
        expires_at=NOW + timedelta(minutes=30),
    )

    first = recommendations_db.replace_context_snapshot(account['uid'], snapshot, idempotency_key='upload-1')
    replay = recommendations_db.replace_context_snapshot(account['uid'], snapshot, idempotency_key='upload-1')

    assert first.replaced is False
    assert replay == first, 'the retry reported a different outcome than the request it repeats'


def test_the_same_upload_key_for_different_content_is_refused(account):
    """The other half of the receipt read: the key identifies the request, not the device."""
    import database.task_recommendations as recommendations_db
    from models.task_recommendation import NormalizedContextSnapshot

    snapshot = NormalizedContextSnapshot(
        device_id=DEVICE,
        snapshot_id='context-1',
        matches=[],
        generated_at=NOW,
        expires_at=NOW + timedelta(minutes=30),
    )
    recommendations_db.replace_context_snapshot(account['uid'], snapshot, idempotency_key='upload-1')

    with pytest.raises(recommendations_db.IdempotencyConflictError):
        recommendations_db.replace_context_snapshot(
            account['uid'],
            snapshot.model_copy(update={'snapshot_id': 'context-2', 'generated_at': NOW + timedelta(minutes=1)}),
            idempotency_key='upload-1',
        )


def test_a_publication_for_a_retired_account_generation_is_refused(account):
    """Every transaction here opens by reading the control document. The generation is how an account
    the user wiped keeps its old recommendations out of the new one: a publish that skipped the check
    would put the previous account's shortlist back on their screen."""
    import database.task_recommendations as recommendations_db

    account['store'].set(
        f"users/{account['uid']}/task_intelligence_control/state",
        {'workflow_mode': 'read', 'account_generation': 7},
    )

    with pytest.raises(recommendations_db.RecommendationGenerationMismatchError):
        recommendations_db.save_projection(
            account['uid'], device_scope=DEVICE, projection=_projection('eval-1'), decisions=[]
        )

    assert _documents(account, 'task_recommendation_projections') == []


# --- batch ------------------------------------------------------------------------------------------


def test_publishing_prunes_the_decision_records_that_have_expired(account):
    """The batch, and the only thing that ever trims this collection.

    Every published evaluation leaves a debug-audit row behind. Nothing else deletes them, so if the
    batch does not commit they accumulate for the lifetime of the account — one row per evaluation per
    device, holding a full copy of the projection, in a collection the product never reads back.
    """
    import database.task_recommendations as recommendations_db

    recommendations_db.save_projection(
        account['uid'], device_scope=DEVICE, projection=_projection('eval-1'), decisions=[]
    )
    assert _decision_evaluation_ids(account) == {'eval-1'}, 'precondition'

    recommendations_db.save_projection(
        account['uid'],
        device_scope=DEVICE,
        projection=_projection('eval-2', generated_at=NOW + timedelta(minutes=31)),
        decisions=[],
    )

    assert _decision_evaluation_ids(account) == {'eval-2'}, 'the expired audit row was never deleted'


def test_a_live_decision_record_for_another_device_survives_the_prune(account):
    """Scoped, or the batch is a data-loss bug rather than a retention one. The prune reads only the
    publishing device's own history; another device's live audit row is not its to delete."""
    import database.task_recommendations as recommendations_db

    recommendations_db.save_projection(
        account['uid'], device_scope='device-2', projection=_projection('eval-other'), decisions=[]
    )
    recommendations_db.save_projection(
        account['uid'],
        device_scope=DEVICE,
        projection=_projection('eval-1', generated_at=NOW + timedelta(minutes=31)),
        decisions=[],
    )

    assert _decision_evaluation_ids(account) == {'eval-other', 'eval-1'}


def test_the_decision_history_is_capped_per_device(account):
    """The retention cap, exercised independently of expiry: every seeded row is still live.

    Thirty rows that have NOT expired, then one publish. The batch must delete down to the cap, so
    what is left is the newest history plus the row just written. Without it the collection is
    unbounded and every evaluation the device has ever run stays forever.

    What this holds is COMPLETENESS, not the chunking. Neither the emulator nor Mongo enforces
    Firestore's 500-writes-per-commit limit, so a build that never rolled over passes here too (same
    as the folders and memories suites); the rollover belongs to the unit suite.
    """
    import database.task_recommendations as recommendations_db

    cap = recommendations_db.MAX_DECISION_HISTORY_PER_DEVICE
    seeded = cap + 6
    _seed_decision_history(account, seeded)

    recommendations_db.save_projection(
        account['uid'], device_scope=DEVICE, projection=_projection('eval-fresh'), decisions=[]
    )

    remaining = _decision_evaluation_ids(account)

    assert len(remaining) == cap, f'the audit history was not trimmed to {cap} rows'
    assert 'eval-fresh' in remaining
    # The rows kept are the newest ones: an oldest-first prune would throw away the history the debug
    # view is actually asked for.
    assert remaining == {'eval-fresh'} | {f'seed-{index:03d}' for index in range(seeded - (cap - 1), seeded)}


def test_a_publication_that_lost_the_race_does_not_prune(account):
    """The batch runs only behind a successful publish, and the cap is where that becomes visible.

    A loser wrote nothing, so it has no history of its own to make room for — but it would still count
    the winner's row against the cap and evict the oldest evaluation the user could still ask about.
    Two devices refreshing in a loop would then trim the audit trail at twice the intended rate, and
    nothing would say so. Sitting the history exactly ON the cap makes one extra prune a one-row
    difference this test can see.

    A "the winner's row survives" assertion cannot see it: the winner's row is the NEWEST, so it is the
    last thing an over-eager prune would remove.
    """
    import database.task_recommendations as recommendations_db

    cap = recommendations_db.MAX_DECISION_HISTORY_PER_DEVICE
    _seed_decision_history(account, cap - 1)

    recommendations_db.save_projection(
        account['uid'],
        device_scope=DEVICE,
        projection=_projection('eval-winner', material='material-shared'),
        decisions=[],
    )
    assert len(_decision_evaluation_ids(account)) == cap, 'precondition: the history sits exactly on the cap'

    loser = _projection('eval-loser', material='material-shared', generated_at=NOW + timedelta(minutes=1))
    assert (
        recommendations_db.save_projection(
            account['uid'], device_scope=DEVICE, projection=loser, decisions=[]
        ).evaluation_id
        == 'eval-winner'
    ), 'precondition: the second publication lost'

    remaining = _decision_evaluation_ids(account)
    assert len(remaining) == cap, 'a publication that stored nothing still evicted an audit row'
    assert 'eval-winner' in remaining
