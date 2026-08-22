"""Dual-backend contract for the account cutover control document (ADR-0044 facade + ADR-0002 port).

`database/account_cutover.py` holds ONE document per account — `users/{uid}/account_cutover/state` —
and that document decides which data plane the account's traffic goes to: `legacy`, `migrating`,
`new`, or `rolled_back_stranded`. Everything else in the module exists to move that document from one
state to the next without losing a concurrent operator's move.

    transaction   `cas_set_account_cutover_record` is a compare-and-set: inside a
                  `@firestore.transactional` body it re-reads the control document, compares the
                  stored `account_generation` (and, for an existing tokened checkpoint, the
                  `checkpoint_token`) against what the caller expected, and only then writes. The
                  read is the whole point. If the translation drops it — a write that never reads, or
                  a read taken outside the transaction — two coordinators that both observed
                  generation N both pass the CAS and both write generation N+1. The one that loses
                  the last-write-wins race is told it SUCCEEDED. Concretely: a coordinator advancing
                  an account to `new` and a rollback coordinator returning it to `legacy` can each be
                  told they won, and the account ends up pointed at the plane the other one thought
                  it had left. For the user that is an account that opens empty (traffic on legacy,
                  data written to new) or a migration that runs twice over the same conversations.
                  The same read is what makes `require_existing` mean anything: a control document
                  deleted mid-migration must abort the CAS, not silently re-create itself at whatever
                  generation the caller happened to remember.

    read boundary The strict parse is not one of the eight counted shapes, but it rides the same
                  translation and fails in the same direction, so it is asserted here: a control
                  document that does not parse — or whose embedded `uid` does not match its path —
                  must raise `MalformedDocError` rather than project as the legacy default. Reading a
                  corrupt cutover doc as "legacy" reopens product traffic against the plane the
                  account has already left.

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import threading
import uuid

import pytest


def _payload(uid: str, **overrides) -> dict:
    """A control document the way ``AccountCutoverRecord.persisted_payload`` writes one."""
    data = {
        'schema_version': 1,
        'uid': uid,
        'state': 'legacy',
        'account_generation': 0,
        'ui_generation': 0,
        'api_generation': 0,
        'stranded_new_data': False,
        'offline_queue_instruction': 'none',
        'checkpoint_phase': 'not_started',
        'checkpoint_token': None,
        'manifest_id': None,
        'destination_backend_bound': False,
    }
    data.update(overrides)
    return data


@pytest.fixture
def cutover(bind_store):
    run = uuid.uuid4().hex[:8]
    uid = f'cut-{run}'

    yield {'uid': uid, 'run': run, 'store': bind_store, 'path': f'users/{uid}/account_cutover/state'}

    bind_store.delete(f'users/{uid}/account_cutover/state')


def _control(cutover):
    stored = cutover['store'].get(cutover['path'])
    return stored.data if stored is not None and stored.exists else None


def _record(uid: str, **overrides):
    from models.account_cutover import AccountCutoverRecord

    return AccountCutoverRecord(uid=uid, **overrides)


def _rendezvous(parties: int = 2, timeout: float = 1.5):
    """A one-shot barrier used to hold each writer between its read and its write.

    Bounded and forgiving on purpose, because the two backends serialise contention at different
    moments and neither ordering is wrong. On Mongo the loser's write conflicts with the winner's
    still-uncommitted write and raises before it ever reaches the barrier; on Firestore a read-write
    transaction may hold a read lock, so the second reader blocks server-side. Either way the wait
    expires and the transitions run one after the other. The assertion below is written to hold for
    every one of those orderings — what it does NOT tolerate is both writers succeeding, which is
    exactly what happens when the read stops being part of the transaction.
    """
    barrier = threading.Barrier(parties)
    passed = threading.Event()

    def gate() -> None:
        if passed.is_set():  # a retried attempt must not wait for a partner that is already gone
            return
        try:
            barrier.wait(timeout=timeout)
        except threading.BrokenBarrierError:
            pass
        passed.set()

    return gate


# --- reads: a control document that does not parse must not read as legacy -------------------------


def test_a_missing_control_document_reads_as_legacy(cutover):
    """No document means the account never started a cutover — legacy, generation 0. The optional
    reader has to keep "missing" distinguishable from "explicitly legacy", because the coordinator
    uses that difference to decide whether a first CAS write is a create."""
    import database.account_cutover as cutover_db
    from models.account_cutover import AccountCutoverState

    record = cutover_db.get_account_cutover_record(cutover['uid'])

    assert record.state is AccountCutoverState.legacy
    assert record.account_generation == 0
    assert cutover_db.get_account_cutover_record_optional(cutover['uid']) is None


def test_a_written_record_round_trips_through_the_store(cutover):
    """Enums, the null token and the null manifest id all have to survive the backend unchanged: the
    reader is strict, so a backend that stores `None` as a missing key or an enum as anything but its
    value turns the next read into a fail-closed MalformedDocError."""
    import database.account_cutover as cutover_db
    from models.account_cutover import AccountCutoverCheckpointPhase, AccountCutoverState, OfflineQueueInstruction

    written = _record(
        cutover['uid'],
        state=AccountCutoverState.migrating,
        account_generation=3,
        ui_generation=2,
        api_generation=1,
        offline_queue_instruction=OfflineQueueInstruction.quarantine,
        checkpoint_phase=AccountCutoverCheckpointPhase.exporting,
        checkpoint_token=None,
        manifest_id=None,
    )
    cutover_db.set_account_cutover_record(cutover['uid'], written)

    assert cutover_db.get_account_cutover_record(cutover['uid']) == written
    assert cutover_db.get_account_cutover_record_optional(cutover['uid']) == written


def test_a_malformed_control_document_fails_closed_instead_of_reading_as_legacy(cutover):
    """A control document nobody can parse is not evidence that the account is on the legacy plane.
    Projecting it as legacy is how an account mid-migration gets its product traffic reopened against
    the plane its data is no longer on."""
    import database.account_cutover as cutover_db
    from database.read_boundary import MalformedDocError

    cutover['store'].set(cutover['path'], _payload(cutover['uid'], state='somewhere_else'))

    with pytest.raises(MalformedDocError):
        cutover_db.get_account_cutover_record(cutover['uid'])
    with pytest.raises(MalformedDocError):
        cutover_db.get_account_cutover_record_optional(cutover['uid'])


def test_a_uid_that_does_not_match_the_path_fails_closed(cutover):
    """The embedded uid is bound to the path uid, so a document copied (or restored) under the wrong
    account cannot hand one user another user's cutover state."""
    import database.account_cutover as cutover_db
    from database.read_boundary import MalformedDocError

    cutover['store'].set(cutover['path'], _payload(f"other-{cutover['run']}", state='new', account_generation=4))

    with pytest.raises(MalformedDocError) as raised:
        cutover_db.get_account_cutover_record(cutover['uid'])

    assert raised.value.error_types == ('uid_binding_mismatch',)


# --- transaction: the compare-and-set ---------------------------------------------------------------


def test_the_first_cas_write_creates_the_control_document(cutover):
    """Generation 0 with no document is the implicit-legacy start state, so the first transition is a
    create. The transactional read has to report "missing" as 0/None rather than raising."""
    import database.account_cutover as cutover_db
    from models.account_cutover import AccountCutoverState

    written = cutover_db.cas_set_account_cutover_record(
        cutover['uid'],
        _record(cutover['uid'], state=AccountCutoverState.migrating, account_generation=1, checkpoint_token='tok-1'),
        expected_account_generation=0,
    )

    assert written.state is AccountCutoverState.migrating
    stored = _control(cutover)
    assert stored['state'] == 'migrating'
    assert stored['account_generation'] == 1
    assert stored['checkpoint_token'] == 'tok-1'


def test_a_stale_generation_is_refused_and_the_incumbent_state_survives(cutover):
    """The transaction's whole job. A coordinator that read generation 1, then lost the race, must be
    refused when it writes — and must not leave a trace. If it were allowed through, the account
    would be rolled back to a plane it has already migrated off while the winning coordinator was
    told the migration completed."""
    import database.account_cutover as cutover_db
    from models.account_cutover import AccountCutoverState

    cutover_db.cas_set_account_cutover_record(
        cutover['uid'],
        _record(cutover['uid'], state=AccountCutoverState.migrating, account_generation=1),
        expected_account_generation=0,
    )
    cutover_db.cas_set_account_cutover_record(
        cutover['uid'],
        _record(cutover['uid'], state=AccountCutoverState.new, account_generation=2),
        expected_account_generation=1,
    )

    with pytest.raises(cutover_db.AccountCutoverConcurrencyError) as raised:
        cutover_db.cas_set_account_cutover_record(
            cutover['uid'],
            _record(cutover['uid'], state=AccountCutoverState.legacy, account_generation=2),
            expected_account_generation=1,
        )

    assert raised.value.code == 'cutover_generation_cas_mismatch'
    stored = _control(cutover)
    assert stored['state'] == 'new', 'the refused rollback must not land'
    assert stored['account_generation'] == 2


def test_a_wrong_checkpoint_token_is_refused_and_the_incumbent_state_survives(cutover):
    """Two coordinators can share a generation and still be different writers, so an existing
    checkpoint token has to match exactly. Without it, a resumed migration overwrites the checkpoint
    of the one that is actually running and the export restarts from the wrong phase."""
    import database.account_cutover as cutover_db
    from models.account_cutover import AccountCutoverCheckpointPhase, AccountCutoverState

    cutover_db.cas_set_account_cutover_record(
        cutover['uid'],
        _record(
            cutover['uid'],
            state=AccountCutoverState.migrating,
            account_generation=1,
            checkpoint_phase=AccountCutoverCheckpointPhase.exporting,
            checkpoint_token='tok-live',
        ),
        expected_account_generation=0,
    )

    with pytest.raises(cutover_db.AccountCutoverConcurrencyError) as raised:
        cutover_db.cas_set_account_cutover_record(
            cutover['uid'],
            _record(
                cutover['uid'],
                state=AccountCutoverState.migrating,
                account_generation=1,
                checkpoint_phase=AccountCutoverCheckpointPhase.importing,
                checkpoint_token='tok-other',
            ),
            expected_account_generation=1,
            expected_checkpoint_token='tok-stale',
        )

    assert raised.value.code == 'cutover_checkpoint_cas_mismatch'
    stored = _control(cutover)
    assert stored['checkpoint_token'] == 'tok-live'
    assert stored['checkpoint_phase'] == 'exporting'


def test_a_writer_expecting_no_token_cannot_overwrite_a_tokened_checkpoint(cutover):
    """The token-less form is only legal for a document that has no token. Letting it through would
    make "I did not check the token" the easiest way to win every checkpoint race."""
    import database.account_cutover as cutover_db
    from models.account_cutover import AccountCutoverState

    cutover_db.cas_set_account_cutover_record(
        cutover['uid'],
        _record(cutover['uid'], state=AccountCutoverState.migrating, account_generation=1, checkpoint_token='tok-live'),
        expected_account_generation=0,
    )

    with pytest.raises(cutover_db.AccountCutoverConcurrencyError) as raised:
        cutover_db.cas_set_account_cutover_record(
            cutover['uid'],
            _record(cutover['uid'], state=AccountCutoverState.new, account_generation=1),
            expected_account_generation=1,
        )

    assert raised.value.code == 'cutover_checkpoint_cas_mismatch'
    assert _control(cutover)['state'] == 'migrating'


def test_require_existing_refuses_when_the_control_document_is_missing(cutover):
    """A checkpoint update is an update: if the document it is checkpointing has been deleted, the
    CAS must abort rather than re-create the account's cutover state from the caller's memory of it."""
    import database.account_cutover as cutover_db
    from models.account_cutover import AccountCutoverState

    with pytest.raises(cutover_db.AccountCutoverConcurrencyError) as raised:
        cutover_db.cas_set_account_cutover_record(
            cutover['uid'],
            _record(cutover['uid'], state=AccountCutoverState.migrating, account_generation=1),
            expected_account_generation=0,
            require_existing=True,
        )

    assert raised.value.code == 'cutover_missing_during_cas'
    assert _control(cutover) is None, 'a refused CAS must not create the document it refused to update'


def test_a_malformed_document_is_not_overwritten_by_a_cas_write(cutover):
    """The CAS reads through the same strict boundary, so a corrupt control document is preserved for
    an operator to look at instead of being flattened by whichever coordinator writes next."""
    import database.account_cutover as cutover_db
    from database.read_boundary import MalformedDocError
    from models.account_cutover import AccountCutoverState

    cutover['store'].set(cutover['path'], _payload(cutover['uid'], state='somewhere_else', account_generation=7))

    with pytest.raises(MalformedDocError):
        cutover_db.cas_set_account_cutover_record(
            cutover['uid'],
            _record(cutover['uid'], state=AccountCutoverState.legacy, account_generation=8),
            expected_account_generation=7,
        )

    assert _control(cutover)['state'] == 'somewhere_else', 'the corrupt document must survive untouched'


def test_two_concurrent_transitions_leave_exactly_one_winner(cutover, monkeypatch):
    """Both coordinators read the same generation before either writes; only one may commit.

    This is the test a write-that-never-reads cannot pass. Both writers are handed the same expected
    generation and the same expected token, so both would clear the CAS on a stale read — the
    refusal can only come from the transaction itself. The winner's state is on the document and the
    loser is refused.

    DIVERGENCE, asserted as-is and reported rather than papered over: *how* the loser is refused is
    not the same on the two backends. On Firestore the SDK's ``@transactional`` retries the aborted
    body, the retry re-reads generation 2 and the caller gets the module's own
    ``AccountCutoverConcurrencyError``. On Mongo the conflict surfaces on the ``_set`` INSIDE the
    body, where ``firestore_facade._txn_write_errors`` maps it to ``google.api_core.Aborted`` —
    which the SDK decorator only retries around ``transaction._commit()``, never around the body
    (``_Transactional._pre_commit`` sits outside the ``except retryable_exceptions``). So on Mongo
    the raw ``Aborted`` reaches the caller and the body is never replayed. Both refuse the losing
    write, which is the invariant that matters here; the exception type a caller has to catch is not
    yet the same, and that is a facade-level divergence, not something this suite may fix.
    """
    from google.api_core.exceptions import Aborted

    import database.account_cutover as cutover_db
    from models.account_cutover import AccountCutoverState

    cutover_db.cas_set_account_cutover_record(
        cutover['uid'],
        _record(cutover['uid'], state=AccountCutoverState.migrating, account_generation=1, checkpoint_token='tok-0'),
        expected_account_generation=0,
    )

    # The seam: hold each coordinator between its transactional read and its write, so both really
    # have read the same generation before either writes. `_read_current_generation_and_token` is the
    # first statement after the read in both CAS bodies, and it is patched here, in the test — nothing
    # in `database/account_cutover.py` changes. Without this, two unsynchronised threads interleave
    # rarely enough that a CAS with no transaction around it would pass almost every run.
    gate = _rendezvous(parties=2)
    read_current = cutover_db._read_current_generation_and_token

    def gated_read(*args, **kwargs):
        current = read_current(*args, **kwargs)
        gate()
        return current

    monkeypatch.setattr(cutover_db, '_read_current_generation_and_token', gated_read)
    outcomes: dict[str, object] = {}

    def transition(name: str, state) -> None:
        try:
            cutover_db.cas_set_account_cutover_record(
                cutover['uid'],
                _record(cutover['uid'], state=state, account_generation=2, checkpoint_token=f'tok-{name}'),
                expected_account_generation=1,
                expected_checkpoint_token='tok-0',
            )
            outcomes[name] = 'committed'
        except cutover_db.AccountCutoverConcurrencyError as error:
            outcomes[name] = error.code
        except Exception as error:  # reported, never swallowed
            outcomes[name] = error

    threads = [
        threading.Thread(target=transition, args=('a', AccountCutoverState.new)),
        threading.Thread(target=transition, args=('b', AccountCutoverState.rolled_back_stranded)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
        assert not thread.is_alive(), 'a cutover transition never finished'

    committed = sorted(name for name, outcome in outcomes.items() if outcome == 'committed')
    assert len(committed) == 1, f'exactly one transition may commit, got {outcomes}'
    refused = outcomes['b' if committed == ['a'] else 'a']
    assert isinstance(refused, Aborted) or refused in {
        'cutover_generation_cas_mismatch',
        'cutover_checkpoint_cas_mismatch',
    }, f'the losing coordinator must be told it lost, got {refused!r}'

    stored = _control(cutover)
    assert stored['checkpoint_token'] == f'tok-{committed[0]}', "the surviving document must be exactly the winner's"
    assert stored['account_generation'] == 2
