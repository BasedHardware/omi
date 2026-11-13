"""G2 conservative classifier and exact guard proof, opt-in by dependency injection.

There is deliberately no environment/config activation here. The caller supplies
the customer-data client, primary fence and mode. No retry of transactional or
transform-bearing Commits is hidden inside the interceptor (H-24).
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import re

from google.cloud.firestore_v1.types import Document, DocumentMask, DocumentTransform, Precondition, Value, Write

from database.batch_privacy_attempt import CONVERSATION_AUTHORITY_FIELDS
from database.batch_privacy_write_fence import authority_path
from database.privacy_fence.protocol import owner_key, conversation_key

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Narrowing:
    uid: str
    conversation: str | None = None
    state: str = 'closed'
    reason: str = 'unknown'
    hashed: bool = False


def _value(value):
    name = Value.pb(value).WhichOneof('value_type')
    if name in {'boolean_value', 'string_value', 'integer_value'}:
        return getattr(value, name)
    return None


def classify(write):
    """None only when the write is provably non-narrowing. Legal holds never close P."""
    path = write.delete or write.update.name or write.transform.document
    parts = path.split('/documents/', 1)
    if len(parts) != 2:
        return None
    bits = parts[1].split('/')
    if len(bits) not in {2, 4}:
        return None
    family, uid = bits[:2]
    masked = Write.pb(write).HasField('update_mask')
    fields = write.update.fields
    transforms = [*write.update_transforms, *write.transform.field_transforms]
    touched = {authority_path(p)[0] for p in write.update_mask.field_paths}
    touched.update(authority_path(t.field_path)[0] for t in transforms)
    transform_fields = {authority_path(t.field_path)[0] for t in transforms}
    if family == 'batch_pipeline_privacy' and len(bits) == 2:
        if not re.fullmatch('[0-9a-f]{64}', uid):
            raise ValueError('privacy authority requires an owner hash')
        authorities = {'generation', 'blocked', 'purging'}
        # Opaque token mint/rotation alone does not close P recursively. Every
        # authority-state write (including transforms and field deletes) does.
        if write.delete or not masked or touched & authorities:
            return Narrowing(uid, reason='data_protection', hashed=True)
        return None
    if family == 'account_deletions' and len(bits) == 2:
        safe = (
            masked
            and not write.delete
            and touched == {'wipe_status'}
            and not transform_fields
            and _value(fields.get('wipe_status', Value())) in {'cancelled', 'billing_failed'}
        )
        return None if safe else Narrowing(uid, reason='deleted')
    if family != 'users':
        return None
    if len(bits) == 2:
        authorities = {'data_protection_level', 'migration_status', 'private_cloud_sync_enabled'}
        if write.delete or transform_fields & authorities:
            return Narrowing(uid, reason='data_protection')
        checks = touched & authorities if masked else authorities
        for field in checks:
            value = _value(fields.get(field, Value()))
            safe = (
                value in {'standard', 'enhanced'}
                if field == 'data_protection_level'
                else (
                    value is True
                    if field == 'private_cloud_sync_enabled'
                    else field in fields and Value.pb(fields[field]).WhichOneof('value_type') == 'null_value'
                )
            )
            if not safe:
                return Narrowing(uid, reason='data_protection')
        return None
    _, _, collection, cid = bits
    if collection == 'deleted_conversations':
        # Even a tombstone deletion is conservative: it does not reopen PC.
        return Narrowing(uid, cid, 'deleted', 'deleted')
    if collection != 'conversations':
        return None
    if write.delete:
        return Narrowing(uid, cid, 'deleted', 'deleted')
    authorities = set(CONVERSATION_AUTHORITY_FIELDS)
    checks = touched & authorities if masked else authorities
    if transform_fields & authorities:
        return Narrowing(uid, cid)
    safe_values = {'deleted': False, 'uses_custom_stt': False, 'private_cloud_sync_enabled': True}
    # Replacement defaults match the live walk, except ownership/redirect fields:
    # their presence always narrows. A missing field in a masked write is a delete.
    for field in checks:
        if field not in fields and not masked:
            continue
        if field not in safe_values or field not in fields or _value(fields[field]) is not safe_values[field]:
            state = 'redirected' if field == 'sync_merged_into' else 'closed'
            return Narrowing(uid, cid, state, 'recording_privacy')
    return None


class Coordinator:
    def __init__(self, client, fence):
        self.client = client
        self.fence = fence

    def prepare(self, request):
        """Mutate a copied Commit, return closes. Failure prevents the original RPC."""
        grouped = {}
        for write in request.writes:
            narrowing = classify(write)
            if narrowing:
                owner = narrowing.uid if narrowing.hashed else owner_key(narrowing.uid)
                grouped.setdefault(owner, set()).add(narrowing)
        receipts = []
        for owner, changes in sorted(grouped.items()):
            ref = self.client.collection('batch_pipeline_privacy_fence').document(owner)
            snapshot = ref.get()
            version = snapshot.update_time if snapshot.exists else None
            sequences = []
            for change in sorted(changes, key=lambda c: (c.conversation or '', c.state, c.reason)):
                seq = self.fence.close(
                    owner,
                    reason=change.reason,
                    guard_version=version,
                    conversation=conversation_key(owner, change.conversation) if change.conversation else None,
                    state=change.state,
                )
                sequences.append(seq)
                receipts.append((owner, seq))
            precondition = Precondition(update_time=version) if version is not None else Precondition(exists=False)
            request.writes.append(
                Write(
                    update=Document(name=ref._document_path),
                    update_mask=DocumentMask(field_paths=[]),
                    current_document=precondition,
                    update_transforms=[
                        DocumentTransform.FieldTransform(
                            field_path='landed',
                            append_missing_elements={'values': [Value(integer_value=s) for s in sequences]},
                        )
                    ],
                )
            )
        return receipts

    def acknowledge(self, receipts):
        for owner, seq in receipts:
            try:
                self.fence.settle(owner, seq, 'landed')
            except Exception as error:
                # The FS Commit already succeeded. Do not turn a lost PG ack
                # into a blind retry of the caller's potentially non-idempotent
                # transforms. G.landed is durable proof; Q resolves the pending
                # row while admission stays closed.
                logger.warning('event=privacy_fence_ack outcome=pending exception_type=%s', type(error).__name__)

    def reconcile(self, owner, seq):
        """Dependency from §10 item 3: exact membership or a preconditioned kill.

        Conflict/error propagates for bounded caller retry; no high-water inference.
        This must use a raw guard Commit that never classifies as authority.
        """
        ref = self.client.collection('batch_pipeline_privacy_fence').document(owner)
        snapshot = ref.get()
        if seq in (snapshot.to_dict() or {}).get('landed', []):
            self.fence.settle(owner, seq, 'landed')
            return 'landed'
        precondition = Precondition(update_time=snapshot.update_time) if snapshot.exists else Precondition(exists=False)
        self.client._firestore_api.commit(
            metadata=self.client._rpc_metadata,
            request={
                'database': self.client._database_string,
                'writes': [
                    Write(
                        update=Document(name=ref._document_path),
                        update_mask=DocumentMask(field_paths=[]),
                        current_document=precondition,
                        update_transforms=[
                            DocumentTransform.FieldTransform(field_path='killed', increment=Value(integer_value=1))
                        ],
                    )
                ],
            },
        )
        self.fence.settle(owner, seq, 'abandoned')
        return 'abandoned'
