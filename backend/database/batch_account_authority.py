"""Atomic, replayable account-policy mutations on the customer Firestore plane."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
from typing import Any
from uuid import uuid4

from google.cloud import firestore

from config.policy.kill_switches import kill_switch
from database.batch_account_authority_schema import (
    ACCOUNT_EPOCH,
    ACCOUNT_FIELD_GROUPS,
    ACCOUNT_HEAD,
    ACCOUNT_OPERATIONS,
    ACCOUNT_STATE_COLLECTION,
    PRIVACY_COLLECTION,
    USER_COLLECTION,
)
from database.batch_pipeline_privacy import privacy_owner_key, privacy_purge_patch

ACCOUNT_OPERATION_RETENTION = timedelta(days=90)


class ErasedAccountMutationRefused(RuntimeError):
    """A privacy writer cannot recreate a permanently erased account."""


@dataclass(frozen=True)
class AccountMutationResult:
    epoch: int
    purge_generation: int | None
    applied: bool


def account_authority_writer_enabled() -> bool:
    return kill_switch('BATCH_ACCOUNT_PRIVACY_WRITER_ENABLED', log=False)


def _write_source(writer, reference, data, merge):
    """Preserve the original SDK operation, including its existence precondition."""
    args = (reference,) if writer is not reference else ()
    if data is None:
        writer.delete(*args)
    elif merge is None:
        writer.update(*args, data)
    else:
        writer.set(*args, data, merge=merge)


def mutate_account_authority(
    transaction: Any,
    reference: Any,
    operation_id: str,
    data: dict | None,
    *,
    client: Any,
    preimage: Any = None,
    merge: bool | None = None,
    begin_purge: bool = False,
    validate: Callable[[Any, dict], None] | None = None,
) -> AccountMutationResult:
    """Write one account authority and its epoch in a single transaction.

    The caller allocates the operation ID before opening a retryable transaction.
    Receipts hold counters and an expiry, keyed by a hash of the source family
    and operation ID. They handle delayed replay within the retention window.
    The head survives older binaries replacing the parent privacy document.
    """
    family = reference.parent.id
    if family not in ACCOUNT_FIELD_GROUPS or reference.parent.parent is not None:
        raise ValueError('expected a root account authority document')
    if not operation_id or len(operation_id.encode()) > 256:
        raise ValueError('bounded account operation ID required')
    if preimage is None:
        preimage = reference.get(transaction=transaction)
    owner = client.collection(PRIVACY_COLLECTION).document(privacy_owner_key(reference.id))
    owner_snapshot = owner.get(transaction=transaction)
    previous = owner_snapshot.to_dict() or {}
    head = owner.collection(ACCOUNT_STATE_COLLECTION).document(ACCOUNT_HEAD)
    head_snapshot = head.get(transaction=transaction)
    state = head_snapshot.to_dict() or {}
    digest = hashlib.sha256(f'{family}/{operation_id}'.encode()).hexdigest()
    receipt = owner.collection(ACCOUNT_OPERATIONS).document(digest)
    replay = receipt.get(transaction=transaction).to_dict()
    if replay is not None:
        purge_generation = replay.get('purge_generation')
        if (purge_generation is not None) != begin_purge:
            raise ValueError('account operation ID was used for a different mutation kind')
        return AccountMutationResult(replay[ACCOUNT_EPOCH], purge_generation, False)
    if validate is not None:
        validate(preimage, previous)
    if family == USER_COLLECTION and data is not None and not preimage.exists and previous.get('blocked'):
        raise ErasedAccountMutationRefused('permanently erased account cannot be recreated by a privacy writer')

    epochs = (state.get(ACCOUNT_EPOCH, 0), previous.get(ACCOUNT_EPOCH, 0), previous.get('generation', 0))
    if any(type(value) is not int or value < 0 for value in epochs):
        raise ValueError('invalid account privacy generation')
    epoch = max(epochs) + 1
    owner_patch: dict[str, Any] = {ACCOUNT_EPOCH: epoch}
    purge_generation = None
    if begin_purge:
        owner_patch.update(privacy_purge_patch(previous, blocked=False))
        purge_generation = owner_patch['generation']
    if begin_purge and data is not None and 'migration_status' in data:
        # Bind new migration starts to the privacy choice that admitted them.
        # Keep the original timestamp in the binding so old merge writers
        # replacing started_at continue to use their legacy migration shape.
        migration = data['migration_status']
        data = {
            **data,
            'migration_status': {
                **migration,
                'batch_purge_binding': {'started_at': migration['started_at'], 'generation': purge_generation},
            },
        }

    # The Commit observer recognizes this exact per-source sequence. An extra
    # raw write, even to the same owner in this transaction, stays uncertified.
    _write_source(transaction, reference, data, merge)
    if owner_snapshot.exists:
        transaction.update(owner, owner_patch)
    else:
        transaction.create(owner, {'generation': 0, 'blocked': False, 'purging': False, **owner_patch})
    if head_snapshot.exists:
        transaction.update(head, {ACCOUNT_EPOCH: epoch})
    else:
        transaction.create(head, {ACCOUNT_EPOCH: epoch})
    transaction.create(
        receipt,
        {
            ACCOUNT_EPOCH: epoch,
            'purge_generation': purge_generation,
            'expires_at': datetime.now(timezone.utc) + ACCOUNT_OPERATION_RETENTION,
        },
    )
    return AccountMutationResult(epoch, purge_generation, True)


def write_account_authority(transaction, reference, data, *, operation_id: str, preimage=None, merge=None, client=None):
    """Route an existing transaction after its other reads have completed."""
    if not account_authority_writer_enabled():
        _write_source(transaction, reference, data, merge)
        return None
    if client is None:
        client = getattr(transaction, '_client')
    return mutate_account_authority(
        transaction, reference, operation_id, data, client=client, preimage=preimage, merge=merge
    )


def merge_account_authority(client, reference, data, *, operation_id=None):
    """Route a standalone merge, preserving the single write when switched off."""
    if not account_authority_writer_enabled():
        _write_source(reference, reference, data, True)
        return None

    from database._client import run_transactional

    stable_id = operation_id or uuid4().hex

    @firestore.transactional
    def commit(transaction):
        return mutate_account_authority(transaction, reference, stable_id, data, client=client, merge=True)

    return run_transactional(client, commit, transient=True)
