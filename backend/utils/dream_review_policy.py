"""Typed writes through Review seams. No hard deletes or unjournaled user edits."""

from datetime import datetime, timezone
from typing import Any

from database import review_changes, review_store
from database.task_intelligence_control import get_task_workflow_control
from models.review import AgentProposalItem, ReviewItem, ReviewItemV2
from models.agent_refs import base_ref, has_ref, cited_value
from models.dream_edit import Edit, MemoryHygieneEdit
from models.agent_edit import HarnessEdit
from models.review_context import question_source
from utils.agent_capabilities.guards import vocabulary_rejection, verbatim_quote
from utils.agent_capabilities.registry import get_kind


from utils.agent_capabilities.tools import (
    validate_edit,
    edit_key,
    proposal_fences,
    revalidate_proposal,
    validate_canonical_proposal,
    proposal_label,
    vocabulary_key,
)


def suggest_edit(uid, edit, records, *, run_id=None):
    if get_kind(edit.kind).dream_only:
        raise ValueError('Dream-private capability cannot be offered in Review')
    validate_edit(edit, records)
    key = edit_key(edit, records)
    if not review_changes.agent_change_allowed(uid, key):
        return 'suppressed'
    refs = {base_ref(ref) for ref in [edit.target, *edit.evidence, *([edit.other] if edit.other else [])]}
    source: dict[str, Any] = {'records': {ref: records[ref] for ref in refs}, 'edit_key': key, 'auxiliary': {}}
    if edit.kind == 'entity_summary':
        entity_id = records[base_ref(edit.target)]['entity_id']
        raw = review_store.user(uid).collection('entity_pages').document(entity_id).get().to_dict()
        if edit.before != (review_store.decode_doc(uid, raw) or {}).get('summary', ''):
            raise review_store.ReviewConflict('Dream entity summary changed')
        source['auxiliary']['entity_pages/' + entity_id] = raw
    source['fences'] = proposal_fences(uid, source)
    revalidate_proposal(uid, source)
    validate_canonical_proposal(uid, edit)
    if (
        edit.kind in {'close_task', 'retire_task'}
        and records[base_ref(edit.target)].get('account_generation', 0)
        != get_task_workflow_control(uid).account_generation
    ):
        raise review_store.ReviewConflict('Dream task generation changed')
    target_label = proposal_label(records[base_ref(edit.target)])
    other_label = proposal_label(records[base_ref(edit.other)]) if edit.other else None
    target_content, other_content = (None, None)
    if edit.kind in {'retire_memory', 'supersede_memory'}:
        target_content = str(records[base_ref(edit.target)].get('content') or '')
        other_content = str(records[base_ref(edit.other)].get('content') or '') if edit.other else None
    if isinstance(edit, HarnessEdit):
        proposal = AgentProposalItem.model_validate(
            dict(
                edit=edit,
                target_label=target_label,
                other_label=other_label,
                target_content=target_content,
                other_content=other_content,
            )
        )
    elif edit.kind in {'retire_memory', 'supersede_memory'}:
        proposal = AgentProposalItem.model_validate(
            dict(
                edit=MemoryHygieneEdit.model_validate(edit.model_dump(exclude={'value'})),
                target_label=target_label,
                other_label=other_label,
                target_content=target_content,
                other_content=other_content,
            )
        )
    else:
        proposal = AgentProposalItem(
            edit=Edit.model_validate(edit.model_dump(exclude={'value', 'effective_from'})),
            target_label=target_label,
            other_label=other_label,
        )
    item = ReviewItemV2(
        item_id='agent_proposal:' + review_store.safe_id(key),
        kind='agent_proposal',
        title=edit.kind.replace('_', ' ').capitalize(),
        created_at=datetime.now(timezone.utc),
        agent_proposal=proposal,
    )
    return review_store.enqueue_review_proposal(
        uid,
        item,
        source=source,
        edit_key=key,
        evidence_version=review_store.fingerprint(source),
        **{'dream_run_id': run_id} if run_id is not None else {}
    )


def suggest_hygiene(uid, edit, records, run_id):
    return suggest_edit(uid, edit, records, run_id=run_id)


def suggest_vocabulary(uid, term, records):
    if vocabulary_rejection(term) or any((not has_ref(ref, records) for ref in term.evidence)):
        raise ValueError('dream_invalid_vocabulary')
    key = vocabulary_key(term)
    if not review_changes.agent_change_allowed(uid, key):
        return 'suppressed'
    source: dict[str, Any] = {
        'records': {base_ref(ref): records[base_ref(ref)] for ref in term.evidence},
        'edit_key': key,
        'auxiliary': {
            'dream_vocabulary/current': review_store.user(uid)
            .collection('dream_vocabulary')
            .document('current')
            .get()
            .to_dict()
        },
    }
    source['fences'] = proposal_fences(uid, source)
    revalidate_proposal(uid, source)
    item = ReviewItemV2(
        item_id='agent_proposal:' + review_store.safe_id(key),
        kind='agent_proposal',
        title='Add vocabulary: ' + term.spelling,
        created_at=datetime.now(timezone.utc),
        agent_proposal=AgentProposalItem(vocabulary=term, target_label=term.spelling),
    )
    return review_store.enqueue_review_proposal(
        uid, item, source=source, edit_key=key, evidence_version=review_store.fingerprint(source)
    )


def ask(uid, item, records, *, run_id=None):
    if item.kind not in {'same_person', 'spelling'}:
        raise ValueError('dream_question_kind')
    if not has_ref(item.source_ref, records) or not verbatim_quote(item.quote, cited_value(item.source_ref, records)):
        raise ValueError('dream_invalid_question_evidence')
    result = review_store.enqueue_review_proposal(
        uid,
        ReviewItem.model_validate(
            {
                **item.model_dump(exclude={'value', 'why_it_matters'}),
                'item_id': review_store.dream_question_item_id(uid, item.kind, item.source_ref, item.quote),
                'created_at': datetime.now(timezone.utc),
            }
        ),
        evidence_version=review_store.fingerprint(records),
        source=question_source(item, records),
        **{'dream_run_id': run_id} if run_id is not None else {}
    )
    if run_id is not None:
        return result


def ask_ranked(uid, item, records, run_id):
    return ask(uid, item, records, run_id=run_id)
