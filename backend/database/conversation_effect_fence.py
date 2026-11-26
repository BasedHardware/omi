"""Commit-time authority for effects planned from a conversation snapshot."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from database.account_deletion_marker import account_deletion_document
from database.account_deletion_policy import account_deletion_marker_blocks_access
from database.conversation_revisions import firestore_revision_datetime
from database.conversation_tombstones import COLLECTION as TOMBSTONES
from models.finalization_owner import ENGINE_FIELD, EPOCH_FIELD, python_owns_finalization

_SOURCE_FIELDS = ['deleted', 'discarded', 'sync_merged_into', 'sync_content_revision', ENGINE_FIELD, EPOCH_FIELD]


class ConversationEffectFenced(RuntimeError):
    """An effect lost its source or account authority before commit."""


class ConversationEffectSourceChanged(ConversationEffectFenced):
    """The conversation snapshot used to authorize or generate the effect changed."""


@dataclass(frozen=True)
class ConversationEffectSource:
    conversation_id: str
    revision: int | None
    owner_epoch: int | None

    def validate(self, transaction, client, uid: str) -> None:
        snapshot = _read_current_conversation(transaction, client, uid, self.conversation_id)
        row = snapshot.to_dict() or {}
        if (
            not python_owns_finalization(row)
            or row.get(EPOCH_FIELD) != self.owner_epoch
            or not _revision_matches(row, self.revision)
        ):
            raise ConversationEffectSourceChanged('conversation effect source changed')


@dataclass(frozen=True)
class GoConversationEffectSource(ConversationEffectSource):
    """Commit authority for a serving effect routed through the Go receiver."""

    job_id: str
    finalization_revision: int

    def validate(self, transaction, client, uid: str) -> None:
        snapshot = _read_current_conversation(
            transaction,
            client,
            uid,
            self.conversation_id,
            field_paths=[*_SOURCE_FIELDS, 'finalization_job_id', 'finalization_revision'],
        )
        row = snapshot.to_dict() or {}
        epoch, finalization_revision = row.get(EPOCH_FIELD), row.get('finalization_revision')
        if (
            row.get(ENGINE_FIELD) != 'go'
            or type(epoch) is not int
            or epoch != self.owner_epoch
            or row.get('finalization_job_id') != self.job_id
            or type(finalization_revision) is not int
            or finalization_revision != self.finalization_revision
            or not _revision_matches(row, self.revision)
        ):
            raise ConversationEffectSourceChanged('Go conversation effect source changed')


def _revision_matches(row: Mapping[str, Any], expected: int | None) -> bool:
    revision = row.get('sync_content_revision')
    return (revision is None or type(revision) is int) and revision == expected


@dataclass(frozen=True)
class ProfileConversationInput:
    conversation_id: str
    revision: int | None
    updated_at: datetime

    def validate(self, transaction, client, uid: str) -> None:
        snapshot = _read_current_conversation(transaction, client, uid, self.conversation_id)
        if not _revision_matches(snapshot.to_dict() or {}, self.revision) or (
            firestore_revision_datetime(snapshot.update_time) != self.updated_at
        ):
            raise ConversationEffectSourceChanged('profile conversation input changed')


def _read_current_conversation(transaction, client, uid: str, conversation_id: str, *, field_paths=None):
    user = client.collection('users').document(uid)
    tombstone = user.collection(TOMBSTONES).document(conversation_id).get(transaction=transaction)
    if tombstone.exists:
        raise ConversationEffectSourceChanged('conversation effect source unavailable')
    snapshot = (
        user.collection('conversations')
        .document(conversation_id)
        .get(transaction=transaction, field_paths=_SOURCE_FIELDS if field_paths is None else field_paths)
    )
    row = snapshot.to_dict() or {}
    if not snapshot.exists or row.get('deleted') or row.get('discarded') or row.get('sync_merged_into'):
        raise ConversationEffectSourceChanged('conversation effect source unavailable')
    return snapshot


def require_active_account(transaction, client, uid: str) -> None:
    snapshot = account_deletion_document(uid, firestore_client=client).get(transaction=transaction)
    if account_deletion_marker_blocks_access(
        marker_exists=snapshot.exists, raw_status=(snapshot.to_dict() or {}).get('wipe_status')
    ):
        raise ConversationEffectFenced('conversation effect account unavailable')
