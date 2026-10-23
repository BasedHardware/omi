"""One replay-fenced assignment part; cursor advance belongs to the last part."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from google.cloud import firestore

from config.firestore_read_levers import lever_enabled
from database.batch_pipeline_privacy import assert_batch_write_allowed, BatchPrivacyMemo
from database.batch_pipeline_projection_protocol import (
    ProjectionBlocked,
    ProjectionPredecessorPending,
    ProjectionReplay,
    normalized_binding,
)

from database.sync_ledger import sync_content_ledger_ref, batch_projection_ledger_owner_matches, LEDGER_RETENTION_DAYS
from utils.batch_pipeline.contracts import ProjectionBinding
from utils.batch_pipeline.scheduler import owner_key
from utils.sync.capture import chunk_identity

if TYPE_CHECKING:
    from database.batch_pipeline_projection import ProjectionStore


class ProjectionSession:
    def __init__(
        self,
        store: ProjectionStore,
        segment_id: str,
        binding: ProjectionBinding,
        now: float,
        *,
        part_index: int | None = None,
        part_count: int = 1,
        policy=None,
    ):
        self.store, self.segment_id, self.binding, self.now = store, segment_id, binding, now
        self.policy = policy or store.policy(segment_id)
        self.client = store.client
        self.result_ref = store.ref('results', segment_id)
        self.owner_ref = store.ref('owners', owner_key(binding.owner_id))
        self.ledger_ref = sync_content_ledger_ref(self.client, binding.owner_id, binding.content_id)
        self.entry: dict[str, Any] = {}
        self.ledger: dict[str, Any] = {}
        self.job: dict[str, Any] = {}
        self.incoming_segment_count = 0
        self.speech_seconds = 0.0
        self.erased_predecessors: list[Any] = []
        self.part_index, self.part_count = part_index, part_count
        self.capture_at: float | None = None
        self.audio_end: float | None = None
        self.speaker_scope: str | None = None
        self.total_speech_seconds = 0.0
        self._naming_guard_snapshots = {}
        self._naming_snapshot = None
        self._naming_fingerprint = None
        self.incoming_segment_ids = set()

    def receipt(self) -> dict:
        parts = self.entry.get('projection_parts') or {}
        if self.part_index is not None and parts:
            return parts.get(str(self.part_index)) or {}
        return self.entry.get('projection') or {}

    def write_receipt(self, transaction, receipt):
        """Ready acknowledgment and summary share one result-keyed receipt."""
        parts = dict(self.entry.get('projection_parts') or {})
        if self.part_index is None or not parts:
            transaction.update(self.result_ref, {'projection': receipt, 'projection_state': receipt['state']})
            return
        parts[str(self.part_index)] = receipt
        changes: dict[str, Any] = {'projection_parts': parts}
        summary = dict(self.entry.get('projection') or {})
        if summary and all(part.get('state') == 'ready' for part in parts.values()):
            summary['state'] = 'ready'
            changes.update(projection=summary, projection_state='ready')
        transaction.update(self.result_ref, changes)

    def guard(self, transaction, conversation_ids=()):
        options = {}
        if lever_enabled('batch_privacy_memoize', self.binding.owner_id):
            options['memo'] = getattr(self, '_privacy_memo', None)
        snapshots = {}
        generation = assert_batch_write_allowed(
            self.client,
            transaction,
            self.binding.owner_id,
            conversation_ids=conversation_ids,
            expected_generation=self.binding.privacy_generation,
            snapshots=snapshots,
            **options,
        )
        self._naming_guard_snapshots = snapshots
        if self._naming_snapshot is not None:
            current = self.loaded_naming_snapshot()
            if current is None or self._snapshot_fingerprint(current) != self._naming_fingerprint:
                raise ProjectionBlocked('batch naming snapshot changed')
            validate = self._naming_snapshot.validate
            if validate is not None and validate(transaction, snapshots) is not True:
                raise ProjectionBlocked('batch naming enrollment revoked')
        return generation

    @staticmethod
    def _snapshot_fingerprint(snapshot):
        import hashlib
        import json

        return hashlib.sha256(
            json.dumps(
                {
                    'owner': snapshot.owner_profile.get('speaker_embedding'),
                    'owner_updated_at': snapshot.owner_profile.get('speaker_embedding_updated_at'),
                    'generation': snapshot.privacy_generation,
                },
                sort_keys=True,
                default=str,
            ).encode()
        ).hexdigest()

    def loaded_naming_snapshot(self):
        from utils.stt.batch_naming import NamingSnapshot

        snapshots = self._naming_guard_snapshots
        if 'user' not in snapshots:
            return None
        # These canonical conversations and user were already read by the
        # privacy guard. No enrollment/profile fetch or new read is introduced.
        from utils.manual_speaker_assignments import manual_owner_reserved

        reserved = any(
            manual_owner_reserved(row.get('manual_speaker_assignments') or {})
            for row in snapshots.get('conversations', {}).values()
        )
        receipt = {'speakers': {'reserved': {'is_user': True}}} if reserved else {}
        return NamingSnapshot(
            owner_id=self.binding.owner_id,
            privacy_generation=self.binding.privacy_generation,
            owner_profile=snapshots['user'],
            manual_receipt=receipt,
        )

    def freeze_naming_snapshot(self, snapshot):
        from utils.stt.batch_naming import NamingSnapshot

        if (
            isinstance(snapshot, NamingSnapshot)
            and snapshot.owner_id == self.binding.owner_id
            and snapshot.privacy_generation == self.binding.privacy_generation
        ):
            self._naming_snapshot = snapshot
            self._naming_fingerprint = self._snapshot_fingerprint(snapshot)

    def prepare(self, transaction, *, replay=True):
        if lever_enabled('batch_privacy_memoize', self.binding.owner_id):
            # A session may survive the pre-check and assignment retries. Only
            # prepare and validate_plan within this attempt may share snapshots.
            self._privacy_memo = BatchPrivacyMemo(self.client, transaction)
        elif hasattr(self, '_privacy_memo'):
            del self._privacy_memo
        self.job = self.store.ref('jobs', self.segment_id).get(transaction=transaction).to_dict() or {}
        self.entry = self.result_ref.get(transaction=transaction).to_dict() or {}
        owner = self.owner_ref.get(transaction=transaction).to_dict() or {}
        self.ledger = self.ledger_ref.get(transaction=transaction).to_dict() or {}
        if (
            not self.job.get('projection_binding')
            or normalized_binding(self.job['projection_binding']) != self.binding
            or self.segment_id not in self.binding.segment_ids
            or self.job.get('owner_id') != self.binding.owner_id
            or self.entry.get('owner_key') != owner_key(self.binding.owner_id)
            or self.entry.get('protocol_version') != 1
            or self.entry.get('segment_id') != self.segment_id
            or self.entry.get('capture_at') != self.job.get('capture_at')
            or self.job.get('privacy_generation') != self.binding.privacy_generation
            or self.job.get('result') != self.entry.get('result')
            or 'previous_segment_id' not in self.entry
        ):
            raise ProjectionBlocked('immutable result binding mismatch')
        ids = [
            chunk_identity(
                self.binding.owner_id,
                self.binding.source,
                self.binding.client_device_id,
                self.binding.is_locked,
                self.job['capture_at'],
            )
        ]
        if self.binding.target_conversation_id:
            ids.append(self.binding.target_conversation_id)
        if self.job.get('conversation_id'):
            ids.append(self.job['conversation_id'])
        ids.extend(self.job.get('conversation_ids') or [])
        self.guard(transaction, ids)
        durable = self.ledger.get('batch_pipeline') or {}
        if (
            self.ledger.get('dispatch_protocol') != 'batch_v1'
            or durable
            != {
                'protocol_version': 1,
                'namespace': self.store.store.namespace,
                'segment_ids': list(self.binding.segment_ids),
            }
            or self.ledger.get('job_id') != self.binding.job_id
        ):
            raise ProjectionBlocked('durable intake ledger binding required')
        receipt = self.receipt()
        if not (receipt and self.ledger.get('status') == 'completed') and not batch_projection_ledger_owner_matches(
            self.ledger,
            self.binding.job_id,
            self.binding.run_token,
            self.binding.run_epoch,
        ):
            raise ProjectionBlocked('content ledger owner lost')
        if receipt:
            if replay:
                raise ProjectionReplay(receipt)
            return
        if self.part_index is not None:
            if self.entry.get('projection_part_count', self.part_count) != self.part_count:
                raise ProjectionBlocked('immutable projection part count mismatch')
            if self.part_index and str(self.part_index - 1) not in (self.entry.get('projection_parts') or {}):
                raise ProjectionBlocked('earlier projection part must persist first')
        from database.batch_pipeline_privacy import erased_predecessors

        erased = erased_predecessors(
            self.client,
            transaction,
            self.store.store.namespace,
            owner_key(self.binding.owner_id),
            self.entry['previous_segment_id'],
            owner.get('projection_watermark'),
        )
        if erased is None:
            raise ProjectionPredecessorPending('earlier committed projection must persist first')
        self.erased_predecessors = erased

    def validate_plan(self, transaction, planned):
        # encode is still in assignment's read-only planning phase.
        self.guard(transaction, [planned['id'], *(planned.get('sync_merged_from') or [])])
        from utils.manual_speaker_assignments import apply_manual_assignments, manual_owner_reserved

        current = self.loaded_naming_snapshot()
        if current is not None and manual_owner_reserved(current.manual_receipt):
            # A previously unbound canonical candidate may first be known here.
            # Withdraw only this part's NEW automatic owner accepts, then honor
            # the assignment's canonical receipt; do not retry forever.
            for segment in planned.get('transcript_segments') or []:
                if (
                    segment.get('id') in self.incoming_segment_ids
                    and segment.get('is_user')
                    and segment.get('speaker_match_source') == 'final_centroid:batch-v1'
                    and segment.get('speaker_label_source') not in ('manual', 'carried')
                ):
                    segment.update(
                        is_user=False,
                        person_id=None,
                        speaker_label_source=None,
                        speaker_match_source='batch_owner_reserved',
                        speaker_identity_status='ambiguous',
                    )
            planned['transcript_segments'] = apply_manual_assignments(
                planned.get('transcript_segments') or [], planned.get('manual_speaker_assignments') or {}
            )

    def persist(self, transaction, planned=None, *, superseded=False):
        assigned, created, survivors = planned if planned is not None else ({}, False, [])
        repeat_only = assigned.get('_sync_lineage_repeat_only', False)
        silent = (self.job.get('speech_redrive') or {}).get('silent') is True
        if silent and assigned.get('id') and not superseded:
            # Same assignment transaction: even a previously queued enrichment
            # must observe the silent revision. A later normal append gets a new
            # revision and resumes its ordinary derived effects.
            revision = assigned.get('sync_content_revision')
            if type(revision) is not int or revision <= 0:
                raise ProjectionBlocked('silent redrive requires a content revision')
            conversation = self.client.collection('users').document(self.binding.owner_id).collection('conversations')
            transaction.update(conversation.document(assigned['id']), {'sync_silent_redrive_revision': revision})
        receipt: dict[str, Any] = {
            'state': 'ready' if superseded else 'persisted',
            'conversation_id': assigned.get('id'),
            'created': created,
            'language': assigned.get('language') or self.binding.language or 'en',
            'persisted_at': self.now,
            **({'silent_redrive': True} if silent else {}),
            'audio_required': bool(survivors and self.binding.private_cloud_sync_enabled),
            'incoming_segment_count': self.incoming_segment_count,
            'speech_seconds': 0.0 if superseded else self.speech_seconds,
            'enrichment_required': bool(
                assigned.get('id') and (not repeat_only or assigned.get('_sync_lineage_completion_pending'))
            ),
        }
        if superseded:
            receipt.update(disposition='superseded', superseded_speech_seconds=self.speech_seconds)
        if self.part_index is not None:
            receipt.update(
                part_index=self.part_index,
                capture_at=self.capture_at,
                audio_end=self.audio_end,
                speaker_scope=self.speaker_scope,
            )
            parts = {**(self.entry.get('projection_parts') or {}), str(self.part_index): receipt}
            changes: dict[str, Any] = {'projection_parts': parts, 'projection_part_count': self.part_count}
            if assigned.get('id'):
                changes['conversation_ids'] = firestore.ArrayUnion([assigned['id']])
                transaction.update(
                    self.store.ref('jobs', self.segment_id),
                    {'conversation_ids': firestore.ArrayUnion([assigned['id']])},
                )
            if self.part_index != self.part_count - 1:
                transaction.update(self.result_ref, changes)
                return receipt
            summary = {
                **receipt,
                'state': 'ready' if all(part['state'] == 'ready' for part in parts.values()) else 'persisted',
                'speech_seconds': max(
                    0.0,
                    self.total_speech_seconds
                    - sum(part.get('superseded_speech_seconds', 0.0) for part in parts.values()),
                ),
                'part_count': self.part_count,
            }
            # The summary describes the whole result, not merely its last part.
            summary.pop('disposition', None)
            summary.pop('superseded_speech_seconds', None)
            if all(part.get('disposition') == 'superseded' for part in parts.values()):
                summary.update(disposition='superseded', speech_seconds=0.0)
            changes.update(projection=summary, projection_state=summary['state'])
            transaction.update(self.result_ref, changes)
        else:
            transaction.update(self.result_ref, {'projection': receipt, 'projection_state': receipt['state']})
        transaction.update(self.owner_ref, {'projection_watermark': self.segment_id})
        for reference in self.erased_predecessors:
            transaction.update(
                reference,
                {
                    'expires_at': datetime.fromtimestamp(self.now, timezone.utc)
                    + timedelta(days=LEDGER_RETENTION_DAYS),
                },
            )
        # A read-before-write ledger checkpoint shares the assignment commit.
        transaction.update(
            self.ledger_ref,
            {
                'processed_segment_ids': firestore.ArrayUnion([self.segment_id]),
                'updated_at': datetime.fromtimestamp(self.now, timezone.utc),
            },
        )
        return receipt

    def persist_empty(self, *, superseded=False):
        @firestore.transactional
        def commit(transaction):
            self.prepare(transaction)
            return self.persist(transaction, superseded=superseded)

        try:
            return self.store.run(commit, policy=self.policy)
        finally:
            # A2 shadow: persist() wrote the owner watermark and erased predecessors outside Store.run.
            # A strict no-op unless shadow mode; re-copies current state; never raises.
            mirror = getattr(self.store, 'mirror_assignment', None)
            if mirror is not None:
                mirror(self)
