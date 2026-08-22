"""Dual-backend contract for the account-deletion transitions (ADR-0044 facade + ADR-0002 port).

`database/account_deletion_transitions.py` owns the last few states of "delete my account": the
`account_deletions/{uid}` marker moves to `completed` only when nothing is left to reclaim, and a
provider VM created too late to be caught by the sweep is parked on that same marker so a
reconciliation worker comes back for it. Both moves are `@firestore.transactional`, and both read the
marker inside the transaction before deciding.

    transaction  Three bodies, one shape. `mark_wipe_completed` reads the marker and refuses to write
                 `completed` when a `late_agent_vm_cleanup` is parked on it; `record_late_agent_vm_cleanup`
                 reads the marker's status and refuses to park anything unless an admitted deletion
                 actually owns the cleanup; `adopt_legacy_late_agent_vm_cleanup` reads the parked
                 record and only fences it with a provider instance id when it matches exactly.

                 Each read is load-bearing in a different direction, and each has a user-visible
                 failure:

                 * a completion that does not re-read wins the race against a late VM record and
                   marks the account `completed` while a machine holding that user's data is still
                   running — and nothing retries, because "completed" is what the reconciliation
                   worker skips. The user was told their data was deleted and it was not.
                 * a late-VM record written without re-reading the status parks a destructive
                   cleanup on an account whose deletion was CANCELLED (status `cancelled` restores
                   access), so the next reconciliation pass deletes the VM of a user who is still
                   using the product. Same for an account with no deletion marker at all: nothing
                   may be parked, and no marker may be conjured into existence by parking it.
                 * the adoption is a compare-and-set on the provider identity. It writes one nested
                   field, `late_agent_vm_cleanup.expectedInstanceId`, and it must not overwrite a
                   fence that is already there or attach one to a record whose vmName/zone do not
                   match — the fence is the only thing standing between "delete instance 123" and
                   "delete whatever instance now answers to that name".

    (`read_agent_vm_migration_journals` is a plain `stream()` read, not one of the eight counted
    shapes, but it is the input to the same destructive path and it is asserted here: the journal's
    identity must come from the document id on both backends, and a journal whose stored
    `migrationId` disagrees with its id must be refused rather than acted on.)

Known limitation, reported rather than hidden. Only ONE of the three transactional reads is
mutation-provable here: the completion's. Dropping ``transaction=`` from the reads in
``record_late_agent_vm_cleanup`` or ``adopt_legacy_late_agent_vm_cleanup`` leaves every test below
green. The reason is the emulator, not the assertions: Firestore takes a read LOCK in a read-write
transaction, so the only interleaving that can distinguish a transactional read from a plain one is
"first reader commits last" — and for those two bodies the writer that would have to move underneath
them is itself blocked on that lock, which makes the discriminating ordering unreachable from a test.
Sequentially the two reads behave identically either way. The completion's read, which IS provable
that way, is proved below on both backends.

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime

import pytest


@pytest.fixture
def deletion(bind_store):
    run = uuid.uuid4().hex[:8]
    uid = f'del-{run}'

    yield {
        'uid': uid,
        'run': run,
        'store': bind_store,
        'marker': f'account_deletions/{uid}',
        'vm': f'vm-{run}',
        'zone': 'europe-west1-b',
    }

    # `account_deletions` is a TOP-LEVEL collection shared with every other run on this rig: delete
    # exactly the two paths this test made, never the collection.
    bind_store.delete(f'account_deletions/{uid}')
    for document in bind_store.query(f'users/{uid}/agentVmMigrations'):
        bind_store.delete(document.path)


def _marker(deletion):
    stored = deletion['store'].get(deletion['marker'])
    return stored.data if stored is not None and stored.exists else None


def _seed_marker(deletion, **fields):
    deletion['store'].set(deletion['marker'], dict(fields))


def _refs(deletion):
    """The client handle and marker reference, built exactly the way ``database/users.py`` builds them."""
    import database.account_deletion_transitions as transitions_db

    client = transitions_db.get_firestore_client()
    return client, client.collection('account_deletions').document(deletion['uid'])


# --- the journal read that feeds the destructive path ------------------------------------------------


def test_migration_journals_come_back_identified_by_their_document_id(deletion):
    """The journal drives provider deletes, so its identity has to be the one the store guarantees —
    the document id — and the order has to be stable across backends or a partial cleanup resumes in
    a different place on Mongo than it did on Firestore."""
    import database.account_deletion_transitions as transitions_db

    for suffix in ('b', 'a', 'c'):
        deletion['store'].set(
            f"users/{deletion['uid']}/agentVmMigrations/mig-{suffix}",
            {'vmName': f'vm-{suffix}', 'zone': deletion['zone']},
        )

    journals = transitions_db.read_agent_vm_migration_journals(deletion['uid'])

    assert [journal['migrationId'] for journal in journals] == ['mig-a', 'mig-b', 'mig-c']
    assert journals[0]['vmName'] == 'vm-a'
    assert transitions_db.read_agent_vm_migration_journals(f"other-{deletion['run']}") == []


def test_a_journal_whose_identity_disagrees_with_its_id_is_refused(deletion):
    """An ambiguous journal is not a journal to act on: whichever of the two identities the caller
    trusted, the other one names a machine that would be missed or a machine that is not ours."""
    import database.account_deletion_transitions as transitions_db

    deletion['store'].set(
        f"users/{deletion['uid']}/agentVmMigrations/mig-a",
        {'migrationId': 'mig-somewhere-else', 'vmName': 'vm-a', 'zone': deletion['zone']},
    )

    with pytest.raises(RuntimeError):
        transitions_db.read_agent_vm_migration_journals(deletion['uid'])


# --- transaction: completing the wipe ----------------------------------------------------------------


def test_a_wipe_with_nothing_left_to_reclaim_completes(deletion):
    import database.account_deletion_transitions as transitions_db

    _seed_marker(deletion, wipe_status='running')
    client, doc_ref = _refs(deletion)

    assert transitions_db.mark_wipe_completed(client.transaction(), doc_ref) is True

    marker = _marker(deletion)
    assert marker['wipe_status'] == 'completed'
    assert isinstance(marker['wipe_completed_at'], datetime)


def test_a_wipe_with_a_parked_vm_refuses_to_complete_and_keeps_the_parked_record(deletion):
    """The refusal the transaction exists for. `completed` is what the reconciliation worker skips,
    so writing it while a VM is still parked strands that machine — and the user's data on it —
    forever. The parked record must come through untouched, because it is the retry."""
    import database.account_deletion_transitions as transitions_db

    _seed_marker(
        deletion,
        wipe_status='running',
        late_agent_vm_cleanup={'vmName': deletion['vm'], 'zone': deletion['zone']},
    )
    client, doc_ref = _refs(deletion)

    assert transitions_db.mark_wipe_completed(client.transaction(), doc_ref) is False

    marker = _marker(deletion)
    assert marker['wipe_status'] == 'failed'
    assert 'wipe_completed_at' not in marker, 'a refused completion must not leave a completion stamp'
    assert marker['late_agent_vm_cleanup'] == {'vmName': deletion['vm'], 'zone': deletion['zone']}


# --- transaction: parking a late VM ------------------------------------------------------------------


def test_an_admitted_deletion_parks_its_late_vm(deletion):
    import database.account_deletion_transitions as transitions_db

    _seed_marker(deletion, wipe_status='running')
    client, doc_ref = _refs(deletion)

    assert (
        transitions_db.record_late_agent_vm_cleanup(
            client.transaction(), doc_ref, deletion['vm'], deletion['zone'], '4242'
        )
        is True
    )

    marker = _marker(deletion)
    assert marker['late_agent_vm_cleanup'] == {
        'vmName': deletion['vm'],
        'zone': deletion['zone'],
        'expectedInstanceId': '4242',
    }
    assert marker['wipe_status'] == 'failed', 'a parked VM re-opens the wipe so a worker comes back for it'


def test_a_cancelled_deletion_parks_nothing(deletion):
    """`cancelled` is one of the two statuses that RESTORE access: the user changed their mind and is
    still using the product. Parking a cleanup here would hand a live user's VM to the next
    reconciliation pass, so the transaction must read the status and write nothing at all."""
    import database.account_deletion_transitions as transitions_db

    _seed_marker(deletion, wipe_status='cancelled')
    client, doc_ref = _refs(deletion)

    assert (
        transitions_db.record_late_agent_vm_cleanup(
            client.transaction(), doc_ref, deletion['vm'], deletion['zone'], '4242'
        )
        is False
    )

    assert _marker(deletion) == {'wipe_status': 'cancelled'}, 'the refused write must leave no trace'


def test_an_account_with_no_deletion_marker_gets_none_invented(deletion):
    """No marker means no admitted deletion. A write here would not just park a cleanup, it would
    CREATE the deletion marker — turning "this user never asked to be deleted" into a document whose
    mere existence blocks their access."""
    import database.account_deletion_transitions as transitions_db

    client, doc_ref = _refs(deletion)

    assert (
        transitions_db.record_late_agent_vm_cleanup(
            client.transaction(), doc_ref, deletion['vm'], deletion['zone'], '4242'
        )
        is False
    )

    assert _marker(deletion) is None


def test_a_non_numeric_instance_identity_is_rejected_before_anything_is_parked(deletion):
    """The instance id is a provider fence; a non-numeric one is not a fence at all. It is validated
    inside the transaction, so the rejection also has to roll back — a half-written record would park
    a cleanup with no usable identity."""
    import database.account_deletion_transitions as transitions_db

    _seed_marker(deletion, wipe_status='running')
    client, doc_ref = _refs(deletion)

    with pytest.raises(ValueError):
        transitions_db.record_late_agent_vm_cleanup(
            client.transaction(), doc_ref, deletion['vm'], deletion['zone'], 'not-a-number'
        )

    assert _marker(deletion) == {'wipe_status': 'running'}


# --- transaction: adopting a pre-fence record --------------------------------------------------------


def test_a_pre_fence_record_is_adopted_without_losing_the_rest_of_it(deletion):
    """One nested field is written — `late_agent_vm_cleanup.expectedInstanceId`. The dotted path has
    to reach INTO the parked record on both backends: a translation that treats it as a top-level key
    (or that replaces the whole map) loses the vmName and zone the retry needs, and the VM becomes
    unfindable."""
    import database.account_deletion_transitions as transitions_db

    _seed_marker(
        deletion,
        wipe_status='failed',
        late_agent_vm_cleanup={'vmName': deletion['vm'], 'zone': deletion['zone']},
    )
    client, doc_ref = _refs(deletion)

    assert (
        transitions_db.adopt_legacy_late_agent_vm_cleanup(
            client.transaction(), doc_ref, deletion['vm'], deletion['zone'], '4242'
        )
        is True
    )

    marker = _marker(deletion)
    assert marker['late_agent_vm_cleanup'] == {
        'vmName': deletion['vm'],
        'zone': deletion['zone'],
        'expectedInstanceId': '4242',
    }
    assert marker['wipe_status'] == 'failed'


def test_adopting_a_record_for_a_different_vm_changes_nothing(deletion):
    """ "Exact" means exact. Fencing the parked record with an id observed for a DIFFERENT machine is
    how a delete gets aimed at the wrong instance."""
    import database.account_deletion_transitions as transitions_db

    _seed_marker(
        deletion,
        wipe_status='failed',
        late_agent_vm_cleanup={'vmName': deletion['vm'], 'zone': deletion['zone']},
    )
    client, doc_ref = _refs(deletion)

    assert (
        transitions_db.adopt_legacy_late_agent_vm_cleanup(
            client.transaction(), doc_ref, f"{deletion['vm']}-other", deletion['zone'], '4242'
        )
        is False
    )

    assert _marker(deletion)['late_agent_vm_cleanup'] == {'vmName': deletion['vm'], 'zone': deletion['zone']}


def test_an_existing_fence_is_never_overwritten_by_a_different_identity(deletion):
    """The compare-and-set. A record already fenced to instance 4242 must not be re-pointed at 9999:
    the incumbent fence is the evidence of which machine was actually observed."""
    import database.account_deletion_transitions as transitions_db

    parked = {'vmName': deletion['vm'], 'zone': deletion['zone'], 'expectedInstanceId': '4242'}
    _seed_marker(deletion, wipe_status='failed', late_agent_vm_cleanup=parked)
    client, doc_ref = _refs(deletion)

    assert (
        transitions_db.adopt_legacy_late_agent_vm_cleanup(
            client.transaction(), doc_ref, deletion['vm'], deletion['zone'], '9999'
        )
        is False
    )

    assert _marker(deletion)['late_agent_vm_cleanup'] == parked


def test_re_adopting_the_same_identity_is_idempotent(deletion):
    """A retried adoption from the worker that already fenced this record is not a conflict."""
    import database.account_deletion_transitions as transitions_db

    parked = {'vmName': deletion['vm'], 'zone': deletion['zone'], 'expectedInstanceId': '4242'}
    _seed_marker(deletion, wipe_status='failed', late_agent_vm_cleanup=parked)
    client, doc_ref = _refs(deletion)

    assert (
        transitions_db.adopt_legacy_late_agent_vm_cleanup(
            client.transaction(), doc_ref, deletion['vm'], deletion['zone'], '4242'
        )
        is True
    )

    assert _marker(deletion)['late_agent_vm_cleanup'] == parked


def test_a_cancelled_deletion_cannot_have_its_cleanup_adopted(deletion):
    """Same fence as parking: the account is back in the user's hands, so nothing about its cleanup
    may be advanced towards a provider delete."""
    import database.account_deletion_transitions as transitions_db

    parked = {'vmName': deletion['vm'], 'zone': deletion['zone']}
    _seed_marker(deletion, wipe_status='cancelled', late_agent_vm_cleanup=parked)
    client, doc_ref = _refs(deletion)

    assert (
        transitions_db.adopt_legacy_late_agent_vm_cleanup(
            client.transaction(), doc_ref, deletion['vm'], deletion['zone'], '4242'
        )
        is False
    )

    assert _marker(deletion)['late_agent_vm_cleanup'] == parked


# --- transaction: the race the two writers exist to survive ------------------------------------------


class _SequencedClock:
    """A stand-in for the module's ``datetime``, used to order two concurrent transactions.

    Both racing bodies call ``datetime.now(timezone.utc)`` once, after their read and inside the
    ``transaction.set`` they are about to issue — the only point in either body where a test can get
    a word in without editing ``database/account_deletion_transitions.py``. Each thread's hook fires
    at most once (it is popped), so a decorator-driven retry runs straight through instead of waiting
    for a partner that has already finished.
    """

    def __init__(self, real, hooks):
        self._real = real
        self._hooks = hooks

    def now(self, tz=None):
        hook = self._hooks.pop(threading.current_thread().name, None)
        if hook is not None:
            hook()
        return self._real.now(tz)


def test_a_completion_racing_a_late_vm_record_never_strands_the_machine(deletion, monkeypatch):
    """Interleave the two writers so the completion has already read "nothing parked" when the late
    VM is parked, and the completion commits last.

    That ordering is the whole reason `mark_wipe_completed` reads inside its transaction. If the read
    escapes the transaction, the completion's commit has nothing to conflict with and lands on top of
    the parked record: the marker says `completed` while a machine holding this user's data is still
    running, and the reconciliation worker — which skips completed markers — never comes back. The
    only outcomes allowed here are ones where the parked VM survives and the account does NOT read as
    completed. Which of the two writers commits, and whether the loser is refused by a retry or by a
    raw ``Aborted`` from Mongo's write conflict, is backend-specific and deliberately not asserted.
    """
    import database.account_deletion_transitions as transitions_db

    _seed_marker(deletion, wipe_status='running')
    client, doc_ref = _refs(deletion)

    completion_has_read = threading.Event()
    vm_is_parked = threading.Event()
    outcomes: dict[str, object] = {}

    hooks = {
        'completion': lambda: (completion_has_read.set(), vm_is_parked.wait(timeout=2.0)),
        'parking': lambda: completion_has_read.wait(timeout=2.0),
    }
    monkeypatch.setattr(transitions_db, 'datetime', _SequencedClock(datetime, hooks))

    def complete() -> None:
        try:
            outcomes['completion'] = transitions_db.mark_wipe_completed(client.transaction(), doc_ref)
        except Exception as error:  # reported through the outcome map, never swallowed
            outcomes['completion'] = error

    def park() -> None:
        try:
            outcomes['parking'] = transitions_db.record_late_agent_vm_cleanup(
                client.transaction(), doc_ref, deletion['vm'], deletion['zone'], '4242'
            )
        except Exception as error:
            outcomes['parking'] = error
        finally:
            vm_is_parked.set()

    threads = [
        threading.Thread(target=complete, name='completion'),
        threading.Thread(target=park, name='parking'),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
        assert not thread.is_alive(), 'a deletion transition never finished'

    marker = _marker(deletion)
    assert marker['late_agent_vm_cleanup'] == {
        'vmName': deletion['vm'],
        'zone': deletion['zone'],
        'expectedInstanceId': '4242',
    }, f'the late VM must survive the race, outcomes={outcomes}'
    assert (
        marker['wipe_status'] == 'failed'
    ), f'an account with an unreclaimed VM must never read as completed, outcomes={outcomes}'
    assert 'wipe_completed_at' not in marker or marker['wipe_status'] != 'completed'
