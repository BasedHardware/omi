"""Firestore People preferences, with explicit atomic generation fences."""

from datetime import datetime, timezone
from typing import Any, cast

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from database._client import get_firestore_client, run_transactional
from database.firestore_transaction_retry import run_with_transaction_contention_retry
from database.folders import check_port_revision, port_mutation_digest, read_port_mutation, write_port_mutation
from database.people_generation import bump_people_generation, generation_ref
from database.speaker_learning_fields import project_person_learning
from database.ports.people import GenerationFence, PersonDraft, PersonEntity


class FirestorePeople:
    def __init__(self, space_id: str, *, firestore_client: Any = None, transaction: Any = None):
        self.space_id = space_id
        self.client = firestore_client if firestore_client is not None else get_firestore_client()
        self.transaction = transaction
        self.owner = self.client.collection('users').document(space_id)
        self.ref = self.owner.collection('people')

    def _run(self, method: str, *args: Any, contention: bool = False, **kwargs: Any) -> Any:
        @firestore.transactional
        def apply(transaction):
            return getattr(
                FirestorePeople(self.space_id, firestore_client=self.client, transaction=transaction), method
            )(*args, **kwargs)

        if contention:
            return run_with_transaction_contention_retry(
                self.client.transaction, apply, operation_name='person_get_or_create'
            )
        return run_transactional(self.client, apply)

    def set_pinned(
        self,
        person_id: str,
        pinned: bool,
        *,
        now: datetime | None = None,
        expected_revision: int | None = None,
        mutation_id: str | None = None
    ) -> PersonEntity | None:
        now = now or datetime.now(timezone.utc)
        if self.transaction is None:
            return self._run(
                'set_pinned', person_id, pinned, now=now, expected_revision=expected_revision, mutation_id=mutation_id
            )
        digest = port_mutation_digest('people', 'pin', [person_id, pinned])
        receipt = read_port_mutation(self.owner, self.transaction, mutation_id, digest)
        ref = self.ref.document(person_id)
        snapshot = ref.get(transaction=self.transaction)
        if not snapshot.exists:
            return None
        person = snapshot.to_dict() or {}
        if receipt is not None:
            return PersonEntity.model_construct(**cast(dict[str, Any], {**person, 'id': person.get('id') or person_id}))
        revision = check_port_revision(self.space_id, 'people', person_id, person, expected_revision)
        if bool(person.get('pinned')) == pinned:
            write_port_mutation(self.owner, self.transaction, mutation_id, digest, 'people', person_id)
            return PersonEntity.model_construct(**cast(dict[str, Any], {**person, 'id': person.get('id') or person_id}))
        update = {'pinned': pinned, 'pinned_at': now if pinned else None, 'updated_at': now}
        self.transaction.update(ref, {**update, 'revision': firestore.Increment(1 if 'revision' in person else 2)})
        bump_people_generation(self.transaction, ref)
        write_port_mutation(self.owner, self.transaction, mutation_id, digest, 'people', person_id)
        return PersonEntity.model_construct(
            **cast(dict[str, Any], {**person, **update, 'id': person.get('id') or person_id, 'revision': revision + 1})
        )

    def get_or_create_by_name(self, draft: PersonDraft, *, mutation_id: str | None = None) -> PersonEntity:
        if self.transaction is None:
            data, existing = self._run('_get_or_create_raw', draft, mutation_id=mutation_id, contention=True)
            # Preserve the original retry boundary: ledger projection is AFTER the
            # name-check transaction, never replayed by its contention retry loop.
            if existing:
                data = project_person_learning(self.space_id, data, firestore_client=self.client)
        else:
            data, existing = self._get_or_create_raw(draft, mutation_id=mutation_id, project=True)
        return PersonEntity.model_construct(**data)

    def _get_or_create_raw(
        self, draft: PersonDraft, *, mutation_id: str | None = None, project: bool = False
    ) -> tuple[dict[str, Any], bool]:
        data = draft.model_dump()
        digest = port_mutation_digest('people', 'get_or_create', data)
        receipt = read_port_mutation(self.owner, self.transaction, mutation_id, digest)
        if receipt is not None:
            snapshot = self.ref.document(receipt['entity_id']).get(transaction=self.transaction)
            person = snapshot.to_dict() or {}
            data = {**person, 'id': person.get('id') or receipt['entity_id']}
            if project:
                data = project_person_learning(self.space_id, data, firestore_client=self.client)
            return data, True
        query = self.ref.where(filter=FieldFilter('name', '==', draft.name))
        existing = None
        for snapshot in list(query.stream(transaction=self.transaction)):
            person = snapshot.to_dict() or {}
            if person.get('is_dismissed') is not True:
                existing = {**person, 'id': person.get('id') or snapshot.id}
                break
        if existing is not None:
            # Projection reads happen before any receipt write. Preserve the existing
            # lookup projection; newly created drafts remain unprojected.
            result = (
                project_person_learning(self.space_id, existing, firestore_client=self.client) if project else existing
            )
            write_port_mutation(self.owner, self.transaction, mutation_id, digest, 'people', existing['id'])
            return result, True
        ref = self.ref.document(draft.id)
        self.transaction.set(ref, {**data, 'is_user_created': True, 'revision': 1})
        bump_people_generation(self.transaction, ref)
        write_port_mutation(self.owner, self.transaction, mutation_id, digest, 'people', draft.id)
        return {**data, 'revision': 1}, False

    def read_generation(self) -> GenerationFence | None:
        ref = generation_ref(self.owner)
        snapshot = ref.get(transaction=self.transaction) if self.transaction is not None else ref.get()
        if not snapshot.exists:
            return None
        value = (snapshot.to_dict() or {}).get('generation')
        if type(value) is not int or value < 0:
            return None
        return GenerationFence(value=value, token=snapshot.update_time.rfc3339())


def set_person_pinned(
    uid: str, person_id: str, pinned: bool, *, now: datetime | None = None, firestore_client: Any = None
) -> PersonEntity | None:
    return FirestorePeople(uid, firestore_client=firestore_client).set_pinned(person_id, pinned, now=now)


def get_or_create_person_by_name(uid: str, data: dict[str, Any], *, firestore_client: Any = None) -> PersonEntity:
    return FirestorePeople(uid, firestore_client=firestore_client).get_or_create_by_name(
        PersonDraft.model_validate(data)
    )
