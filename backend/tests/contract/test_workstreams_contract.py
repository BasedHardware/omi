"""Dual-backend contract for workstreams (ADR-0044 facade + ADR-0002 store port).

`database/workstreams.py` is the record of a piece of ongoing work: the thread itself, its append-only
journal, the versioned artifacts hanging off it, and the checkpoints an agent resumes from. It has
exactly ONE at-risk shape — the coverage guard counts `transaction` and nothing else; its `.count(`
calls are Python list tallies, not Firestore aggregations — and every state change in the module is
built from it:

    transaction   start work, append to the journal, publish an artifact version, move an artifact
                  through review, upsert a checkpoint. Each opens `client.transaction()`, reads the
                  documents its decision depends on (the capability fence, the workstream's own
                  generation, the idempotency receipt, the journal counter, the artifact head), and
                  writes two to five documents in one commit.

What a wrong translation costs the user:

  *A thread that half exists.* Starting work writes the workstream, its first journal entry, the link
  on the originating task and the intent receipt — together. If the link can land without the thread,
  the task shows a "continue work" affordance that opens nothing; if the thread lands without the
  receipt, the next retry starts a second thread for the same task and the user's work splits in two.

  *The journal loses its order.* Every entry takes `sequence = latest_event_sequence + 1` from the
  workstream document read in the same transaction, and writes the entry and the new counter together.
  Clients page the journal with `sequence > N`, so two entries sharing a sequence means one of them is
  never delivered to the client at all, and a counter that advances without its entry leaves a hole
  that reads as lost work.

  *Two live versions of the same document.* Publishing an artifact revision reads the logical head,
  checks the new version really is the next one and really supersedes the current head, then in one
  commit writes the new descriptor, marks the old one superseded, moves the head pointer and journals
  the change. Any subset of that is a user opening what they believe is the current draft and getting
  a stale one — or a head pointing at a version that was never written.

  *A checkpoint that lies about where the work is.* An agent resumes from the checkpoint's
  `last_event_sequence`. It is fenced against the journal read in the same transaction (it may not
  claim progress past the last entry) and against its own stored value (it may not move backwards), so
  a resumed run cannot skip entries it never saw or re-do entries it already handled.

  *A revoked capability keeps writing.* Two fences, and they catch different things: the control
  document says whether the account still has task intelligence at this generation, and the
  workstream's own `account_generation` says whether THIS thread belongs to the generation the caller
  is acting for. A caller can pass the first and fail the second — that is a thread left over from
  before an account reset — which is why both are asserted separately below.

Not covered, and why: cross-transaction conflict detection under real concurrency. Firestore locks the
read set; Mongo takes a snapshot and no read lock (ADR-0070), so a same-outcome assertion for two
racing writers would be asserting something the port deliberately does not promise. Measured, not
assumed: rewriting the workstream read in `append_workstream_event` as `workstream_ref.get()` — the
read escaping the transaction entirely — leaves this suite green on both backends, because a
sequential caller reads the same committed state either way.

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

GENERATION = 1
SEEDED = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)
CONTENT_HASH = 'sha256:0123456789abcdef'


@pytest.fixture
def work(bind_store):
    """One account at generation 1 with a task, and a workstream started from that task."""
    import database.workstreams as workstreams_db
    from models.workstream import TaskOriginWorkIntent

    run = uuid.uuid4().hex[:8]
    uid = f'ws-{run}'
    task_id = f'task-{run}'

    bind_store.set(
        f'users/{uid}/task_intelligence_control/state',
        {'workflow_mode': 'write', 'account_generation': GENERATION},
    )
    bind_store.set(
        f'users/{uid}/action_items/{task_id}',
        {
            'id': task_id,
            'task_id': task_id,
            'description': 'Draft the migration plan',
            'status': 'active',
            'completed': False,
            'account_generation': GENERATION,
            'created_at': SEEDED,
            'updated_at': SEEDED,
        },
    )

    receipt = workstreams_db.resolve_work_intent(
        uid,
        TaskOriginWorkIntent(task_id=task_id),
        idempotency_key=f'start-{run}',
        account_generation=GENERATION,
    )

    yield {
        'uid': uid,
        'run': run,
        'task': task_id,
        'workstream': receipt.workstream_id,
        'receipt': receipt,
        'store': bind_store,
    }

    for collection in (
        'workstreams',
        'action_items',
        'goals',
        'task_intelligence_control',
        'work_intent_receipts',
        'workflow_mutation_receipts',
    ):
        for document in bind_store.query(f'users/{uid}/{collection}'):
            if collection == 'workstreams':
                for child in ('events', 'artifact_refs', 'artifact_heads', 'continuation_checkpoints'):
                    for grandchild in bind_store.query(f'{document.path}/{child}'):
                        bind_store.delete(grandchild.path)
            bind_store.delete(document.path)


def _doc(work, path):
    stored = work['store'].get(f"users/{work['uid']}/{path}")
    return stored.data if stored is not None and stored.exists else None


def _workstream(work, workstream_id=None):
    return _doc(work, f"workstreams/{workstream_id or work['workstream']}")


def _rows(work, path) -> list[dict]:
    return [document.data for document in work['store'].query(f"users/{work['uid']}/{path}")]


def _journal(work) -> list[dict]:
    return sorted(_rows(work, f"workstreams/{work['workstream']}/events"), key=lambda row: row['sequence'])


def _artifacts(work) -> dict[str, dict]:
    return {row['artifact_id']: row for row in _rows(work, f"workstreams/{work['workstream']}/artifact_refs")}


def _heads(work) -> list[dict]:
    return _rows(work, f"workstreams/{work['workstream']}/artifact_heads")


def _append(work, summary, *, key, kind='user_note', required_status=None, generation=GENERATION):
    import database.workstreams as workstreams_db
    from models.workstream import WorkstreamEventCreate, WorkstreamEventKind

    return workstreams_db.append_workstream_event(
        work['uid'],
        work['workstream'],
        WorkstreamEventCreate(kind=WorkstreamEventKind(kind), summary=summary),
        idempotency_key=key,
        account_generation=generation,
        required_status=required_status,
    )


# --- transaction: starting work is one commit -------------------------------------------------------


def test_starting_work_writes_the_thread_its_first_entry_and_the_task_link_together(work):
    """Four documents, one commit: the workstream, its opening journal entry, the `workstream_id` on
    the originating task, and the intent receipt. A task linked to a thread that does not exist is a
    button that opens nothing; a thread with no link is work the user cannot find again."""
    stored = _workstream(work)

    assert stored['status'] == 'open'
    assert stored['latest_event_sequence'] == 1
    assert [row['sequence'] for row in _journal(work)] == [1]
    assert _doc(work, f"action_items/{work['task']}")['workstream_id'] == work['workstream']
    assert len(_rows(work, 'work_intent_receipts')) == 1
    assert work['receipt'].newly_created is True


def test_replaying_a_work_intent_returns_the_first_receipt_instead_of_a_second_thread(work):
    """The receipt is read inside the transaction that would otherwise create the thread. Without it a
    retried tap splits one piece of work across two threads, each with half the journal.

    Note what is NOT asserted: `newly_created`. The stored receipt is replayed verbatim, so a replay
    reports the value the FIRST call recorded — `True` — and a caller cannot tell a fresh start from a
    retry by that flag. Both backends agree on it, so it is upstream semantics rather than a
    translation difference; the identity that matters here is the workstream, and there is one.
    """
    import database.workstreams as workstreams_db
    from models.workstream import TaskOriginWorkIntent

    replay = workstreams_db.resolve_work_intent(
        work['uid'],
        TaskOriginWorkIntent(task_id=work['task']),
        idempotency_key=f"start-{work['run']}",
        account_generation=GENERATION,
    )

    assert replay.receipt_id == work['receipt'].receipt_id
    assert replay.workstream_id == work['workstream']
    assert len(_rows(work, 'workstreams')) == 1
    assert len(_journal(work)) == 1
    assert len(_rows(work, 'work_intent_receipts')) == 1


def test_a_work_intent_for_a_task_that_is_not_there_writes_nothing(work):
    """The task existence read is inside the transaction with every write it guards, so a bad request
    cannot leave an orphan thread or a receipt that makes the retry look already-done."""
    import database.workstreams as workstreams_db
    from models.workstream import TaskOriginWorkIntent

    with pytest.raises(workstreams_db.WorkstreamNotFoundError):
        workstreams_db.resolve_work_intent(
            work['uid'],
            TaskOriginWorkIntent(task_id=f"ghost-{work['run']}"),
            idempotency_key=f"ghost-{work['run']}",
            account_generation=GENERATION,
        )

    assert len(_rows(work, 'workstreams')) == 1
    assert len(_rows(work, 'work_intent_receipts')) == 1, 'only the fixture receipt'


def test_an_intent_key_reused_for_a_different_request_is_refused(work):
    """Same key, different task: the stored intent wins and the caller is told, rather than being
    handed a thread for work they did not ask about."""
    import database.workstreams as workstreams_db
    from models.workstream import TaskOriginWorkIntent

    other = f"task2-{work['run']}"
    work['store'].set(
        f"users/{work['uid']}/action_items/{other}",
        {'id': other, 'description': 'Something else', 'account_generation': GENERATION, 'updated_at': SEEDED},
    )

    with pytest.raises(workstreams_db.WorkstreamConflictError):
        workstreams_db.resolve_work_intent(
            work['uid'],
            TaskOriginWorkIntent(task_id=other),
            idempotency_key=f"start-{work['run']}",
            account_generation=GENERATION,
        )

    assert len(_rows(work, 'workstreams')) == 1


def test_starting_work_from_a_goal_hangs_a_task_off_the_new_thread(work):
    """The goal-origin path writes a workstream, its first entry, a brand-new anchor task and the
    receipt in one commit — and reads the goal in the same transaction to refuse work on a goal that
    has already ended."""
    import database.goals as goals_db
    import database.workstreams as workstreams_db
    from models.workstream import GoalOriginWorkIntent

    goal_id = f"goal-{work['run']}"
    goals_db.create_goal(work['uid'], {'title': 'Ship it', 'desired_outcome': 'Shipped', 'goal_id': goal_id})

    receipt = workstreams_db.resolve_work_intent(
        work['uid'],
        GoalOriginWorkIntent(
            goal_id=goal_id, title='Ship it', objective='Get it out', anchor_task_description='Write the notes'
        ),
        idempotency_key=f"goal-start-{work['run']}",
        account_generation=GENERATION,
    )

    assert receipt.newly_created is True
    assert _workstream(work, receipt.workstream_id)['goal_id'] == goal_id
    assert _doc(work, f'action_items/{receipt.task_id}')['workstream_id'] == receipt.workstream_id


def test_work_cannot_be_started_on_a_goal_that_has_already_ended(work):
    """`_assert_goal_exists` reads the goal inside the transaction. Attaching new work to an abandoned
    goal would resurrect it in every goal-scoped view the user has already cleared."""
    import database.goals as goals_db
    import database.workstreams as workstreams_db
    from models.goal import GoalRelationshipDisposition, GoalStatus
    from models.workstream import GoalOriginWorkIntent

    goal_id = f"goal-{work['run']}"
    goals_db.create_goal(work['uid'], {'title': 'Ship it', 'desired_outcome': 'Shipped', 'goal_id': goal_id})
    goals_db.transition_goal_lifecycle(
        work['uid'],
        goal_id,
        status=GoalStatus.abandoned,
        relationship_disposition=GoalRelationshipDisposition.retain,
        idempotency_key=f"end-{work['run']}",
        account_generation=GENERATION,
    )

    with pytest.raises(workstreams_db.WorkstreamConflictError):
        workstreams_db.resolve_work_intent(
            work['uid'],
            GoalOriginWorkIntent(
                goal_id=goal_id, title='Ship it', objective='Get it out', anchor_task_description='Write the notes'
            ),
            idempotency_key=f"goal-start-{work['run']}",
            account_generation=GENERATION,
        )

    assert len(_rows(work, 'workstreams')) == 1


# --- transaction: the journal counter ---------------------------------------------------------------


def test_each_journal_entry_takes_the_sequence_after_the_one_it_read(work):
    """The counter is read from the workstream and written back with the entry in one commit. Clients
    page the journal with `sequence > N`: two entries at the same sequence means one is never
    delivered."""
    first = _append(work, 'looked at the data', key=f"e1-{work['run']}")
    second = _append(work, 'drafted the plan', key=f"e2-{work['run']}")

    assert (first.sequence, second.sequence) == (2, 3)
    assert [row['sequence'] for row in _journal(work)] == [1, 2, 3]
    assert _workstream(work)['latest_event_sequence'] == 3


def test_a_replayed_journal_entry_does_not_advance_the_counter(work):
    """A retried append returns the entry it already wrote. Advancing anyway leaves a gap the journal
    renders as work that happened and was lost."""
    first = _append(work, 'looked at the data', key=f"e1-{work['run']}")
    replay = _append(work, 'looked at the data', key=f"e1-{work['run']}")

    assert replay.event_id == first.event_id
    assert replay.sequence == 2
    assert len(_journal(work)) == 2
    assert _workstream(work)['latest_event_sequence'] == 2


def test_a_journal_key_reused_with_different_content_is_refused(work):
    """Two different things cannot occupy one entry in the record of what happened."""
    import database.workstreams as workstreams_db

    _append(work, 'looked at the data', key=f"e1-{work['run']}")

    with pytest.raises(workstreams_db.WorkstreamConflictError):
        _append(work, 'something else entirely', key=f"e1-{work['run']}")

    assert len(_journal(work)) == 2


def test_an_append_that_requires_a_status_the_thread_no_longer_has_is_refused(work):
    """`required_status` is checked against the workstream read in the same transaction. A caller that
    believed the thread was completed must not append to one that is still open — and the counter must
    not move for an entry that was never written."""
    import database.workstreams as workstreams_db
    from models.workstream import WorkstreamStatus

    with pytest.raises(workstreams_db.WorkstreamConflictError):
        _append(work, 'closing note', key=f"e1-{work['run']}", required_status=WorkstreamStatus.completed)

    assert len(_journal(work)) == 1
    assert _workstream(work)['latest_event_sequence'] == 1


def test_an_append_to_a_thread_from_an_earlier_generation_is_refused(work):
    """The fence only the WORKSTREAM's own generation can catch: the account is at generation 1 and so
    is the caller, so the control document agrees with both. The thread is the thing left over from
    before the reset. Writing to it would revive a piece of work the account already discarded."""
    import database.workstreams as workstreams_db

    work['store'].set(
        f"users/{work['uid']}/workstreams/{work['workstream']}",
        {'account_generation': GENERATION + 1},
        merge=True,
    )

    with pytest.raises(workstreams_db.WorkstreamGenerationMismatchError):
        _append(work, 'looked at the data', key=f"e1-{work['run']}")

    assert len(_journal(work)) == 1


def test_an_append_under_a_withdrawn_capability_is_refused(work):
    """The other fence: the caller and the thread agree at generation 1, and the ACCOUNT has moved to
    2. Only the control document, read in the same transaction as the write, can tell."""
    import database.workstreams as workstreams_db

    work['store'].set(
        f"users/{work['uid']}/task_intelligence_control/state",
        {'workflow_mode': 'write', 'account_generation': GENERATION + 1},
    )

    with pytest.raises(workstreams_db.WorkstreamGenerationMismatchError):
        _append(work, 'looked at the data', key=f"e1-{work['run']}")

    assert len(_journal(work)) == 1


def test_a_replayed_update_is_answered_from_its_receipt_and_not_re_applied(work):
    """The scenario only the receipt catches: the user renames the thread, renames it again, and the
    first request is then retried by a client that never saw its response. The retry must be answered
    from the receipt — re-applying it would put back a title the user has already replaced."""
    import database.workstreams as workstreams_db
    from models.workstream import WorkstreamUpdate

    key = f"rename-{work['run']}"
    original = workstreams_db.update_workstream(
        work['uid'],
        work['workstream'],
        WorkstreamUpdate(title='First name'),
        idempotency_key=key,
        account_generation=GENERATION,
    )
    workstreams_db.update_workstream(
        work['uid'],
        work['workstream'],
        WorkstreamUpdate(title='Second name'),
        idempotency_key=f"rename2-{work['run']}",
        account_generation=GENERATION,
    )

    replay = workstreams_db.update_workstream(
        work['uid'],
        work['workstream'],
        WorkstreamUpdate(title='First name'),
        idempotency_key=key,
        account_generation=GENERATION,
    )

    assert replay.title == original.title == 'First name', 'the retry gets the original answer'
    assert _workstream(work)['title'] == 'Second name', 'and the stored thread is not rewound'


# --- transaction: the artifact head chain -----------------------------------------------------------


def _publish(work, *, version, supersedes=None, evidence=None, key=None, logical_key=None):
    import database.workstreams as workstreams_db
    from models.workstream import ArtifactDescriptorCreate

    return workstreams_db.create_artifact_descriptor(
        work['uid'],
        work['workstream'],
        ArtifactDescriptorCreate(
            logical_key=logical_key or f"plan-{work['run']}",
            version=version,
            supersedes_artifact_id=supersedes,
            kind='document',
            uri=f'file:///plan-v{version}',
            content_hash=f'{CONTENT_HASH}{version}',
            evidence_event_ids=evidence or [],
        ),
        idempotency_key=key or f'artifact-{version}',
        account_generation=GENERATION,
    )


def test_the_first_artifact_version_lands_with_its_head_and_a_journal_entry(work):
    """One commit: the descriptor, the logical head pointing at it, a journal entry saying it happened,
    and the advanced counter. A head that disagrees with the descriptors is the user opening 'latest'
    and getting something else."""
    record = _publish(work, version=1)

    assert record.status.value == 'draft'
    assert list(_artifacts(work)) == [record.artifact_id]
    assert [head['artifact_id'] for head in _heads(work)] == [record.artifact_id]
    assert _workstream(work)['latest_event_sequence'] == 2
    assert _journal(work)[-1]['kind'] == 'artifact_version'


def test_a_version_that_does_not_follow_the_head_is_refused(work):
    """Version 3 on a head at version 1: the head is read inside the transaction and the next version
    is computed from it, so a client that skipped a version cannot leave a hole in the chain.

    The request is otherwise entirely valid — it supersedes the real head and cites a real journal
    entry — so the version comparison is the only thing that can refuse it. An earlier draft of this
    test also left the evidence list empty, and the evidence guard was quietly doing the work: removing
    the version check survived.
    """
    import database.workstreams as workstreams_db

    first = _publish(work, version=1)
    evidence_event = _journal(work)[-1]['event_id']

    with pytest.raises(workstreams_db.WorkstreamConflictError):
        _publish(work, version=3, supersedes=first.artifact_id, evidence=[evidence_event], key='artifact-3')

    assert [head['version'] for head in _heads(work)] == [1]


def test_a_revision_supersedes_the_current_head_in_the_same_commit(work):
    """Four documents move together: the new descriptor, the old one's status, the head pointer and the
    journal. Any subset of that leaves two versions claiming to be live."""
    first = _publish(work, version=1)
    evidence_event = _journal(work)[-1]['event_id']

    second = _publish(work, version=2, supersedes=first.artifact_id, evidence=[evidence_event], key='artifact-2')

    artifacts = _artifacts(work)
    assert artifacts[first.artifact_id]['status'] == 'superseded'
    assert artifacts[second.artifact_id]['status'] == 'draft'
    assert [head['artifact_id'] for head in _heads(work)] == [second.artifact_id]


def test_a_revision_that_cites_no_journal_evidence_is_refused(work):
    """A new version of a document has to say what caused it. The fixtures differ from the accepted
    revision above ONLY in the evidence list being empty."""
    import database.workstreams as workstreams_db

    first = _publish(work, version=1)

    with pytest.raises(workstreams_db.WorkstreamConflictError):
        _publish(work, version=2, supersedes=first.artifact_id, evidence=[], key='artifact-2')

    assert [head['version'] for head in _heads(work)] == [1]


def test_a_revision_citing_an_entry_that_is_not_in_the_journal_is_refused(work):
    """Each cited event id is read inside the transaction. A citation that points at nothing is a
    provenance chain the user cannot follow back."""
    import database.workstreams as workstreams_db

    first = _publish(work, version=1)

    with pytest.raises(workstreams_db.WorkstreamConflictError):
        _publish(work, version=2, supersedes=first.artifact_id, evidence=['wse_missing'], key='artifact-2')

    assert len(_artifacts(work)) == 1


def test_an_artifact_moves_one_review_step_at_a_time(work):
    """The allowed transition is looked up against the status read in the transaction. A draft that can
    jump straight to approved is a review that never happened."""
    import database.workstreams as workstreams_db
    from models.workstream import ArtifactStatus, ArtifactStatusTransitionRequest

    record = _publish(work, version=1)

    moved = workstreams_db.transition_artifact_status(
        work['uid'],
        work['workstream'],
        record.artifact_id,
        ArtifactStatusTransitionRequest(status=ArtifactStatus.awaiting_review),
        idempotency_key=f"review-{work['run']}",
        account_generation=GENERATION,
    )
    assert moved.status == ArtifactStatus.awaiting_review

    with pytest.raises(workstreams_db.WorkstreamConflictError):
        workstreams_db.transition_artifact_status(
            work['uid'],
            work['workstream'],
            record.artifact_id,
            ArtifactStatusTransitionRequest(status=ArtifactStatus.delivered),
            idempotency_key=f"deliver-{work['run']}",
            account_generation=GENERATION,
        )

    assert _artifacts(work)[record.artifact_id]['status'] == 'awaiting_review'


def test_re_asking_for_the_status_an_artifact_already_has_adds_no_journal_entry(work):
    """Idempotent by the status read, not by the receipt: a repeated request must not spam the journal
    with a change that did not happen."""
    import database.workstreams as workstreams_db
    from models.workstream import ArtifactStatus, ArtifactStatusTransitionRequest

    record = _publish(work, version=1)
    for attempt in range(2):
        workstreams_db.transition_artifact_status(
            work['uid'],
            work['workstream'],
            record.artifact_id,
            ArtifactStatusTransitionRequest(status=ArtifactStatus.awaiting_review),
            idempotency_key=f"review-{attempt}-{work['run']}",
            account_generation=GENERATION,
        )

    summaries = [row['summary'] for row in _journal(work)]
    moves = [summary for summary in summaries if 'moved to awaiting_review' in summary]
    assert len(moves) == 1, 'the second request journalled a change that did not happen'
    assert _workstream(work)['latest_event_sequence'] == len(summaries)


# --- transaction: continuation checkpoints ----------------------------------------------------------


def _checkpoint(work, *, sequence, summary='where we got to', key=None, runtime=None):
    import database.workstreams as workstreams_db
    from models.workstream import ContinuationCheckpointUpsert

    return workstreams_db.upsert_continuation_checkpoint(
        work['uid'],
        work['workstream'],
        ContinuationCheckpointUpsert(
            runtime_id=runtime or f"runtime-{work['run']}",
            last_event_sequence=sequence,
            context_summary=summary,
        ),
        idempotency_key=key or f'checkpoint-{sequence}-{summary}',
        account_generation=GENERATION,
    )


def test_a_checkpoint_cannot_claim_progress_the_journal_does_not_have(work):
    """`last_event_sequence` is bounded by the workstream counter read in the same transaction. A
    checkpoint past the end of the journal makes the next resumed run skip entries nobody ever
    processed."""
    import database.workstreams as workstreams_db

    with pytest.raises(workstreams_db.WorkstreamConflictError):
        _checkpoint(work, sequence=99)

    assert _rows(work, f"workstreams/{work['workstream']}/continuation_checkpoints") == []


def test_a_checkpoint_cannot_move_backwards(work):
    """The stored checkpoint is read before the new one is accepted. Moving back means the resumed run
    re-does work the user already saw happen."""
    import database.workstreams as workstreams_db

    _append(work, 'looked at the data', key=f"e1-{work['run']}")
    _checkpoint(work, sequence=2)

    with pytest.raises(workstreams_db.WorkstreamConflictError):
        _checkpoint(work, sequence=1)

    rows = _rows(work, f"workstreams/{work['workstream']}/continuation_checkpoints")
    assert [row['last_event_sequence'] for row in rows] == [2]


def test_the_same_checkpoint_sequence_with_different_content_is_refused(work):
    """Same position, two different summaries: one of them is wrong, and the resumed run would have no
    way to tell which. The fixtures differ only in the summary."""
    import database.workstreams as workstreams_db

    _append(work, 'looked at the data', key=f"e1-{work['run']}")
    _checkpoint(work, sequence=2, summary='where we got to')

    with pytest.raises(workstreams_db.WorkstreamConflictError):
        _checkpoint(work, sequence=2, summary='somewhere else entirely')

    rows = _rows(work, f"workstreams/{work['workstream']}/continuation_checkpoints")
    assert [row['context_summary'] for row in rows] == ['where we got to']


def test_a_checkpoint_advances_in_place_rather_than_accumulating(work):
    """One runtime keeps one checkpoint: the id is derived from the runtime, and the upsert reads the
    stored row before replacing it."""
    _append(work, 'looked at the data', key=f"e1-{work['run']}")
    _checkpoint(work, sequence=1)
    _checkpoint(work, sequence=2)

    rows = _rows(work, f"workstreams/{work['workstream']}/continuation_checkpoints")
    assert [row['last_event_sequence'] for row in rows] == [2]
