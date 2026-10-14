"""The harness's immediate schema/grounding/authority boundary. Staging never writes."""

from dataclasses import dataclass
from copy import deepcopy
from typing import Any

from database import review_changes, review_store
from models.dream_harness import HarnessQuestion
from models.dream_harness_edit import HarnessEdit
from models.dream_edit import Term
from models.dream_refs import base_ref, has_ref, cited_value
from utils import dream_tools
from utils.dream_guards import verbatim_quote, vocabulary_rejection
from utils.executors import db_executor, run_blocking


@dataclass
class Staged:
    id: str
    key: str
    operation: HarnessEdit | Term | HarnessQuestion
    kind: str
    refs: tuple[str, ...]
    fences: dict[str, Any]
    records: dict[str, Any]
    value: int
    why_it_matters: str

    def payload(self):
        return {'id': self.id, 'kind': self.kind, 'operation': self.operation.model_dump(mode='json')}


def references(operation: HarnessEdit | Term | HarnessQuestion) -> tuple[str, ...]:
    if isinstance(operation, HarnessEdit):
        return tuple(
            dict.fromkeys([operation.target, *operation.evidence, *([operation.other] if operation.other else [])])
        )
    if isinstance(operation, HarnessQuestion):
        return (operation.source_ref,)
    return tuple(operation.evidence)


def question_key(question):
    return 'dream:question:' + review_store.fingerprint([question.kind, question.source_ref, question.quote])


async def stage(uid, operation: HarnessEdit | Term | HarnessQuestion, records, *, value=3, why_it_matters=''):
    refs = references(operation)
    if isinstance(operation, HarnessQuestion) and operation.same_person:
        people = {operation.same_person.left.entity_id, operation.same_person.right.entity_id}
        refs = (*refs, *(ref for ref, row in records.items() if row.get('entity_id') in people))
    if not refs or any(not has_ref(ref, records) or ('#' in ref and cited_value(ref, records) is None) for ref in refs):
        raise ValueError('dream_unknown_evidence')
    if isinstance(operation, HarnessEdit):
        dream_tools.validate_edit(operation, records)
        if operation.kind == 'spelling' and not verbatim_quote(
            operation.before, cited_value(operation.target, records)
        ):
            raise ValueError('dream_invalid_target')
        key = dream_tools.edit_key(operation, records)
        value, why_it_matters = operation.value, operation.why_it_matters
    elif isinstance(operation, HarnessQuestion):
        if not verbatim_quote(operation.quote, cited_value(operation.source_ref, records)):
            raise ValueError('dream_invalid_question_evidence')
        if operation.same_person:
            entities = {row.get('entity_id') for row in records.values()}
            if any(
                person.entity_id not in entities for person in (operation.same_person.left, operation.same_person.right)
            ):
                raise ValueError('dream_unknown_person')
        key = question_key(operation)
        value, why_it_matters = operation.value, operation.why_it_matters
    else:
        rejection = vocabulary_rejection(operation)
        if rejection:
            raise ValueError('dream_' + rejection)
        key = dream_tools.vocabulary_key(operation)
    if not await run_blocking(db_executor, review_changes.agent_change_allowed, uid, key):
        raise ValueError('dream_suppressed')
    scoped = {base_ref(ref): records[base_ref(ref)] for ref in refs}
    source = {'records': scoped}
    # Current snapshots are checked at proposal time and fenced again at commit.
    fences = await run_blocking(db_executor, dream_tools.proposal_fences, uid, source)
    await run_blocking(db_executor, dream_tools.revalidate_proposal, uid, source)
    if isinstance(operation, HarnessEdit):
        await run_blocking(db_executor, dream_tools.validate_canonical_proposal, uid, operation)
    if isinstance(operation, Term):
        path = 'dream_vocabulary/current'
        raw = await run_blocking(
            db_executor,
            lambda: review_store.user(uid).collection('dream_vocabulary').document('current').get().to_dict(),
        )
        fences[path] = raw
        existing = (review_store.decode_doc(uid, raw) or {}).get('source', [])
        if len(existing) >= 500:
            raise ValueError('dream_vocabulary_cap')
    return Staged(
        id=review_store.safe_id(key),
        key=key,
        operation=operation,
        kind=operation.kind if not isinstance(operation, Term) else 'vocabulary',
        refs=refs,
        fences=fences,
        records=deepcopy(scoped),
        value=value,
        why_it_matters=why_it_matters,
    )
