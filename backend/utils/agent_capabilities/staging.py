"""The harness's immediate schema/grounding/authority boundary. Staging never writes."""

from dataclasses import dataclass
from copy import deepcopy
import json
from typing import Any

from database import review_changes, review_store
from models.agent_tools import HarnessQuestion
from models.agent_edit import HarnessEdit
from models.dream_edit import Term
from models.agent_refs import base_ref, has_ref, cited_value
from utils.agent_capabilities import tools as dream_tools
from utils.agent_capabilities.guards import verbatim_quote
from utils.executors import db_executor, run_blocking
from utils.agent_capabilities.errors import ToolError


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
    return 'agent:question:' + review_store.fingerprint([question.kind, question.source_ref, question.quote])


async def stage(
    uid, operation: HarnessEdit | Term | HarnessQuestion, records, *, authority, value=3, why_it_matters=''
):
    if authority not in {'user', 'dream'}:
        raise ValueError('agent_invalid_authority')
    refs = references(operation)
    if isinstance(operation, HarnessQuestion) and operation.same_person:
        people = {operation.same_person.left.entity_id, operation.same_person.right.entity_id}
        refs = (*refs, *(ref for ref, row in records.items() if row.get('entity_id') in people))
    for ref in refs:
        if not has_ref(ref, records) or ('#' in ref and cited_value(ref, records) is None):
            raise ToolError(
                'agent_unknown_evidence',
                field='evidence',
                ref=ref,
                expected='Read this owner ref and cite its current segment id',
            )
    if not refs:
        raise ToolError('agent_unknown_evidence', field='evidence', expected='At least one fully read owner ref')
    if isinstance(operation, HarnessEdit):
        dream_tools.validate_edit(operation, records, authority=authority)
        if operation.kind == 'spelling' and not verbatim_quote(
            operation.before, cited_value(operation.target, records)
        ):
            raise ToolError(
                'agent_target_quote_mismatch',
                field='before',
                ref=operation.target,
                expected='Exact text in this cited segment',
            )
        key = dream_tools.edit_key(operation, records)
        value, why_it_matters = operation.value, operation.why_it_matters
    elif isinstance(operation, HarnessQuestion):
        if not verbatim_quote(operation.quote, cited_value(operation.source_ref, records)):
            raise ValueError('agent_invalid_question_evidence')
        if operation.same_person:
            entities = {row.get('entity_id') for row in records.values()}
            if any(
                person.entity_id not in entities for person in (operation.same_person.left, operation.same_person.right)
            ):
                raise ValueError('agent_unknown_person')
        key = await run_blocking(db_executor, question_key, operation)
        value, why_it_matters = operation.value, operation.why_it_matters
    else:
        from utils.agent_capabilities.registry import get_kind

        get_kind('vocabulary').validate(operation, records, authority=authority)
        key = dream_tools.vocabulary_key(operation)
    if authority == 'dream' and not await run_blocking(db_executor, review_changes.agent_change_allowed, uid, key):
        raise ValueError('agent_suppressed')
    scoped = {base_ref(ref): records[base_ref(ref)] for ref in refs}
    source = {'records': scoped}
    # Current snapshots are checked at proposal time and fenced again at commit.
    fences = await run_blocking(db_executor, dream_tools.proposal_fences, uid, source)
    if isinstance(operation, HarnessEdit) and operation.kind == 'merge_people':
        for ref in (operation.target, operation.other):
            node = fences.get('knowledge_nodes/' + records[base_ref(ref)]['entity_id'])
            if node and node.get('redirect_entity_id'):
                raise ValueError('agent_person_already_merged')
    if len(json.dumps({'source': source, 'fences': fences}, default=str, ensure_ascii=False).encode()) > 256000:
        raise ValueError('agent_proposal_byte_budget')
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
        decoded = await run_blocking(db_executor, review_store.decode_doc, uid, raw)
        existing = (decoded or {}).get('source', [])
        if len(existing) >= 500:
            raise ValueError('agent_vocabulary_cap')
    return Staged(
        id=await run_blocking(db_executor, review_store.safe_id, key),
        key=key,
        operation=operation,
        kind=operation.kind if not isinstance(operation, Term) else 'vocabulary',
        refs=refs,
        fences=fences,
        records=deepcopy(scoped),
        value=value,
        why_it_matters=why_it_matters,
    )
