"""Cell-backed people domain operations; writes use the shared cell flush."""

from __future__ import annotations

from typing import Any

from copy import deepcopy
from datetime import datetime, timezone

from database.ports.people import GenerationFence, PersonDraft, PersonEntity
from models.other import VoiceReadiness, voice_readiness

from ._base import Repo, atomic


class CellPeople(Repo):
    domain = 'people'

    @atomic
    def set_pinned(
        self,
        person_id: str,
        pinned: bool,
        *,
        now: datetime | None = None,
        expected_revision: int | None = None,
        mutation_id: str | None = None,
    ) -> PersonEntity | None:
        digest, prior = self.receipt(mutation_id, 'people.pin', [person_id, pinned])
        row = self.store.state['people'].get(person_id)
        if row is None:
            return None
        if prior is None:
            revision = self.check('people', person_id, row, expected_revision)
            if bool(row.get('pinned')) != pinned:
                now = now or datetime.now(timezone.utc)
                row.update(pinned=pinned, pinned_at=now if pinned else None, updated_at=now, revision=revision + 1)
                self.store.state['generation'] += 1
            self.save(mutation_id, digest, person_id)
        data: dict[str, Any] = {**deepcopy(row), 'id': person_id}
        return PersonEntity.model_construct(**data)

    @atomic
    def get_or_create_by_name(self, draft: PersonDraft, *, mutation_id: str | None = None) -> PersonEntity:
        digest, prior = self.receipt(mutation_id, 'people.create', draft.model_dump())
        if prior is not None:
            return PersonEntity.model_construct(
                **self._project({**(self.store.state['people'].get(prior) or {}), 'id': prior})
            )
        matches = self.store.query(
            'people',
            "jsonb_typeof(doc->'name')='string' AND doc->>'name'=%s "
            "AND doc->'is_dismissed' IS DISTINCT FROM 'true'::jsonb",
            [draft.name],
            limit=1,
        )
        existing_id = matches[0][0] if matches else None
        existing = self.store.state['people'].get(existing_id) if matches else None
        if existing is None:
            data: dict[str, Any] = {**draft.model_dump(), 'revision': 1}
            self.store.state['people'][draft.id] = {**data, 'is_user_created': True}
            self.store.state['generation'] += 1
        else:
            data = self._project({**existing, 'id': existing_id})
        self.save(mutation_id, digest, data['id'])
        return PersonEntity.model_construct(**data)

    @staticmethod
    def _project(person: dict) -> dict:
        # The reference has no learning-job ledger; model the settled, no-job
        # projection and preserve all unrelated heterogeneous fields.
        data = deepcopy(person)
        if data.get('voice_learning_state') != 'disabled' and voice_readiness(data) == VoiceReadiness.ready:
            data['voice_learning_state'] = 'learned'
        elif data.get('voice_learning_state') in (None, 'pending', 'learned'):
            data['voice_learning_state'] = 'unknown'
        if data.get('voice_learning_state') != 'needs_more_speech':
            data['voice_needed_seconds'] = None
        return data

    @atomic
    def read_generation(self) -> GenerationFence | None:
        generation = self.store.state['generation']
        return GenerationFence(value=generation, token=str(generation)) if generation else None
