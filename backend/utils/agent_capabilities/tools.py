"""Typed writes through Review seams. No hard deletes or unjournaled user edits."""

import copy
import hashlib
import json
import logging
from types import SimpleNamespace
from datetime import datetime, timezone
from uuid import uuid5, NAMESPACE_URL
from typing import Any, Literal, cast

from database import conversations, review_changes, review_store
from database.review_changes import AgentEdit
from database.review_memory_changes import MemoryEdit
from database.task_intelligence_control import get_task_workflow_control
from models.review import ChangeRef, ReviewChange
from utils.agent_capabilities.text_edits import replace_term
from models.agent_refs import base_ref, has_ref, cited_value
from models.dream_edit import MemoryHygieneEdit
from models.agent_edit import HarnessEdit
from models.agent_tools import tool_model
from database import review_memory_hygiene
from utils.entity_pages import resolve_entity
from utils.agent_capabilities.guards import (
    spelling_rejection,
    summary_rejection,
    task_rejection,
    vocabulary_rejection,
    verbatim_quote,
)
from utils.agent_capabilities.evidence import EvidenceRecords
from utils.agent_capabilities.errors import ToolError
from utils.agent_capabilities import change_view as dream_change_view
from utils.agent_capabilities import cleanup_edits as dream_cleanup_edits
from utils.review_projection import sync_transcript_chunks
from database.legal_holds import DestructiveOperationInProgress
from utils import dream_required_intake

logger = logging.getLogger(__name__)


def edit_key(edit, records=None):
    from utils.agent_capabilities.registry import get_kind

    kind, value = get_kind(edit.kind).key(edit, records)
    return 'agent:' + kind + ':' + hashlib.sha256(json.dumps(value).encode()).hexdigest()


def _replace_tree(value: Any, before: str, after: str) -> Any:
    if isinstance(value, str):
        return replace_term(value, before, after)
    if isinstance(value, list):
        return [_replace_tree(item, before, after) for item in value]
    if isinstance(value, dict):
        # Citations, IDs and timestamps must never be rewritten as names.
        return {
            k: (
                _replace_tree(v, before, after)
                if k
                in {
                    'text',
                    'title',
                    'description',
                    'content',
                    'overview',
                    'sections',
                    'items',
                    'heading',
                    'body_markdown',
                    'note_claims',
                }
                else v
            )
            for k, v in value.items()
        }
    return value


def validate_summary_edit(edit, row, *, full=False, authority='dream'):
    if edit.kind not in {'title', 'overview'}:
        return
    if not conversations.is_visible_conversation(row, include_discarded=True):
        raise review_store.ReviewStale('Dream conversation unavailable')
    if row.get('is_locked') or not conversations.is_visible_conversation(row):
        raise review_store.ReviewConflict('Dream conversation unavailable')
    if authority == 'user' and isinstance(edit, HarnessEdit):
        current = (
            row.get('user_title')
            if edit.kind == 'title' and row.get('user_title')
            else (row.get('structured') or {}).get(edit.kind, '')
        )
        if edit.before != current:
            raise review_store.ReviewConflict('Agent summary changed')
        if not edit.after.strip():
            raise ValueError('agent_empty_summary')
        return
    if edit.kind == 'title' and row.get('user_title'):
        raise review_store.ReviewConflict('Dream title was set by the user')
    if edit.before != ((row.get('structured') or {}).get(edit.kind) or ''):
        raise review_store.ReviewConflict('Dream summary changed')
    reason = summary_rejection(edit, row, full=full)
    if reason:
        raise ValueError('agent_summary_' + reason)


def validate_memory_hygiene(edit, records):
    MemoryHygieneEdit.model_validate(edit.model_dump(exclude={'value', 'why_it_matters'}))
    ref = base_ref(edit.target)
    if ref.partition('/')[0] not in {'memories', 'memory_items'} or '#' in edit.target:
        raise ValueError('agent_invalid_memory')
    row = records[ref]
    if edit.before and edit.before != row.get('content'):
        raise review_store.ReviewConflict('Dream memory changed')
    if not any(
        base_ref(ev) != ref and base_ref(ev).partition('/')[0] in {'conversations', 'memories', 'memory_items'}
        for ev in edit.evidence
    ):
        raise ValueError('agent_unknown_evidence')
    if any(base_ref(ev).partition('/')[0] not in {'conversations', 'memories', 'memory_items'} for ev in edit.evidence):
        raise ValueError('agent_unknown_evidence')
    if edit.other:
        other = records.get(base_ref(edit.other))
        if (
            not other
            or base_ref(edit.other) == ref
            or '#' in edit.other
            or edit.other.partition('/')[0] not in {'memories', 'memory_items'}
        ):
            raise ValueError('agent_invalid_memory')
        if any(
            row.get(field) != other.get(field) for field in ('visibility', 'subject_scope', 'subject_entity_id', 'slot')
        ):
            raise review_store.ReviewConflict('Replacement must share privacy, subject and attribute')
    elif edit.kind == 'supersede_memory' and not any(base_ref(ev).startswith('conversations/') for ev in edit.evidence):
        raise ValueError('agent_unknown_evidence')


def target_authority_protected(edit, records):
    """Autonomous cleanup cannot silently close owner-authored facts."""
    if edit.kind not in {'merge_memories', 'retire_memory', 'supersede_memory'}:
        return False
    return any(
        str((records.get(base_ref(ref)) or {}).get('write_reason') or '')
        in {'direct_user_statement', 'explicit_remember', 'onboarding'}
        for ref in (edit.target, edit.other)
        if ref
    )


def apply_verified_edit(
    uid,
    edit,
    records,
    *,
    expected_records,
    authority,
    gate_retry=False,
    run_started_at=None,
    run_id=None,
):
    """The harness alone selects this boundary after independent verification.

    User acceptance retains apply_edit. Verification never relaxes schema,
    current evidence, source/account fences, or durable Undo suppression.
    """
    if authority == 'dream' and target_authority_protected(edit, records):
        raise ValueError('agent_user_memory_requires_review')
    validate_edit(edit, records, authority=authority)
    if authority == 'dream' and gate_retry:
        key = edit_key(edit, records)
        change_id = dream_change_view.change_id_for_key(uid, key)
        prior = review_store.decode_doc(
            uid,
            review_store.user(uid)
            .collection('review_changes')
            .document(review_store.safe_id(change_id))
            .get()
            .to_dict(),
        )
        created_at = prior.get('created_at') if prior else None
        same_run = (
            bool(run_id)
            and prior is not None
            and run_id
            in {
                prior.get('run_id'),
                prior.get('dream_run_id'),
            }
        )
        same_pass = (
            isinstance(run_started_at, datetime)
            and isinstance(created_at, datetime)
            and created_at.tzinfo is not None
            and run_started_at.tzinfo is not None
            and created_at >= run_started_at
        )
        change = prior.get('change') if prior else None
        if (
            prior
            and prior.get('edit_key') == key
            and prior.get('phase') in {None, 'applied'}
            and (same_pass or same_run)
            and isinstance(change, dict)
            and change.get('undone', False) is False
        ):
            if prior.get('transcript_overlay'):
                try:
                    sync_transcript_chunks(
                        uid, prior['transcript_overlay']['conversation_id'], firestore_client=review_store.client()
                    )
                except DestructiveOperationInProgress:
                    raise
                except Exception:
                    # The change is committed; a provider failure in the repair must not fail the pass.
                    logger.warning('dream transcript chunk repair failed after committed change', exc_info=True)
            return 'applied'
    refs = {base_ref(ref) for ref in [edit.target, *edit.evidence, *([edit.other] if edit.other else [])]}
    sources = EvidenceRecords({ref: records[ref] for ref in refs})
    revalidate_proposal(uid, {'records': sources})
    validate_canonical_proposal(uid, edit)
    return apply_edit(uid, edit, sources, expected_records=expected_records, authority=authority)


def answer_spelling(uid, source, value):
    """Apply the user's chosen spelling through the existing fenced Review seam."""
    from models.dream_edit import Edit

    edit = Edit.model_validate(source['spelling_edit'])
    if not value.strip() or len(value) > 50:
        raise review_store.ReviewConflict('Dream spelling answer is invalid')
    if value == edit.before:
        return False
    records = revalidate_proposal(uid, source)
    selected = edit.model_copy(update={'after': value})
    try:
        status = apply_edit(uid, selected, records, expected_records=source.get('fences'), authority='user')
    except (review_store.ReviewConflict, review_store.ReviewNotFound):
        raise
    except ValueError as exc:
        raise review_store.ReviewConflict('Dream spelling proposal no longer valid') from exc
    if status == 'suppressed':
        raise review_store.ReviewConflict('Dream spelling proposal was suppressed')
    return status == 'applied'


def proposal_record(uid, ref, snapshot):
    from utils.agent_capabilities import reads as dream_reads

    if ref.startswith('memory_items/') and dream_required_intake.MARKER in snapshot:
        return dream_required_intake.read_candidate(uid, ref.split('/', 1)[1], snapshot[dream_required_intake.MARKER])
    if ref.startswith('entity/'):
        entity_id = ref.removeprefix('entity/')
        return (
            dream_reads.read_entity_record(uid, entity_id)
            if 'facts' in snapshot or 'decisions' in snapshot
            else resolve_entity(uid, entity_id)
        )
    if ref.startswith('screen/'):
        # Screen evidence is local-retention scoped; missing/revoked evidence conflicts.
        from database import screen_activity

        return next(
            (
                r
                for r in screen_activity.get_screen_activity(
                    uid, start_date=snapshot.get('timestamp'), end_date=snapshot.get('timestamp'), limit=100
                )
                if r['id'] == ref.split('/', 1)[1]
            ),
            None,
        )
    return dream_reads.read_record(uid, ref, require_available=True)


def revalidate_proposal(uid, source):
    from fastapi import HTTPException

    records = source['records']
    for ref, snapshot in records.items():
        try:
            current = proposal_record(uid, ref, snapshot)
        except review_store.ReviewConflict:
            raise
        except HTTPException as exc:
            if exc.status_code == 404 and ref.partition('/')[0] in {'memories', 'memory_items', 'conversations'}:
                raise review_store.ReviewStale('Dream proposal evidence unavailable') from exc
            raise review_store.ReviewConflict('Dream proposal evidence unavailable') from exc
        except Exception as exc:
            # A failed read cannot establish an allowlisted terminal condition.
            raise review_store.ReviewConflict('Dream proposal evidence unavailable') from exc
        if current is None and ref.partition('/')[0] in {'memories', 'memory_items', 'conversations'}:
            # These readers return None only for their explicit terminal exclusions.
            raise review_store.ReviewStale('Dream proposal evidence unavailable')
        if review_store.fingerprint(current) != review_store.fingerprint(snapshot):
            raise review_store.ReviewConflict('Dream proposal evidence changed')
    for path, snapshot in source.get('auxiliary', {}).items():
        collection, key = path.split('/', 1)
        if review_store.user(uid).collection(collection).document(key).get().to_dict() != snapshot:
            raise review_store.ReviewConflict('Dream proposal target changed')
    return records


def proposal_fences(uid, source):
    paths = set(source.get('auxiliary', {}))
    for ref, row in source['records'].items():
        collection, key = ref.split('/', 1)
        if collection in {'action_items', 'candidates', 'workstreams'} or row.get('type') == 'project':
            paths.add('task_intelligence_control/state')
        if collection == 'people':
            paths.update({ref, 'knowledge_nodes/person:' + key})
        elif collection in {'entity', 'knowledge_nodes', 'workstreams'}:
            entity_id = row['entity_id']
            paths.add('knowledge_nodes/' + entity_id)
            if row['type'] == 'person':
                paths.add('people/' + entity_id.removeprefix('person:'))
            elif row['type'] == 'project':
                paths.add('workstreams/' + entity_id)
        elif collection in {'memories', 'memory_items'}:
            paths.add('memory_items/' + key)
        elif collection == 'screen':
            paths.add('screen_activity/' + key)
        else:
            paths.add(ref)
            if collection == 'conversations' and row.get('has_transcript_corrections'):
                paths.add('transcript_corrections/' + key)
    return {
        path: review_store.user(uid).collection(path.split('/', 1)[0]).document(path.split('/', 1)[1]).get().to_dict()
        for path in sorted(paths)
    }


def validate_canonical_proposal(uid, edit):
    if edit.kind not in {'memory', 'merge_memories', 'retire_memory', 'supersede_memory'} and not (
        edit.kind == 'spelling' and base_ref(edit.target).partition('/')[0] in {'memories', 'memory_items'}
    ):
        return
    from utils.memory.canonical_memory_adapter import read_canonical_memory_item

    refs = [edit.target, *([edit.other] if edit.other else [])]
    sources = [
        read_canonical_memory_item(uid, base_ref(ref).split('/', 1)[1], db_client=review_store.client()) for ref in refs
    ]
    if any(
        row is None
        or row.status.value != 'active'
        or row.kind.value != 'fact'
        or row.ledger_schema_version != 'knowledge_ledger.v1'
        for row in sources
    ):
        raise review_store.ReviewConflict('Only active canonical facts may be proposed')
    if len(sources) == 2 and any(
        getattr(sources[0], field) != getattr(sources[1], field)
        for field in ('visibility', 'subject_scope', 'subject_entity_id', 'slot', 'tier')
    ):
        raise review_store.ReviewConflict('Duplicate facts must share visibility and subject')


def proposal_label(row):
    label = (
        row.get('description')
        or row.get('content')
        or row.get('name')
        or row.get('label')
        or (row.get('structured') or {}).get('title')
    )
    return ' '.join(str(label or 'Item').split())[:180]


def vocabulary_key(term):
    from utils.agent_capabilities.registry import get_kind

    kind, value = get_kind('vocabulary').key(term, None)
    return 'agent:' + kind + ':' + review_store.fingerprint(value)


def apply_vocabulary(uid, terms, *, expected_records=None, user_accepted=False, verified=False, records=None):
    if not user_accepted and not verified:
        raise ValueError('agent_vocabulary_requires_acceptance')
    status = 'unchanged'
    for term in terms:
        if vocabulary_rejection(term):
            raise ValueError('agent_common_word')
        key = vocabulary_key(term)
        if user_accepted and review_store.is_user_request(uid):
            from uuid import uuid4

            key = 'agent:user:vocabulary:' + str(uuid4())
        if not user_accepted and not review_changes.agent_change_allowed(uid, key):
            status = 'suppressed'
            continue
        ref = review_store.user(uid).collection('dream_vocabulary').document('current')
        raw = ref.get().to_dict()
        existing = (review_store.decode_doc(uid, raw) or {}).get('source', [])
        merged = {row['spelling'].casefold(): row for row in existing}
        # This policy owns additions; never overwrite an existing user term.
        if term.spelling.casefold() in merged:
            continue
        if len(merged) >= 500:
            raise ValueError('agent_vocabulary_cap')
        merged[term.spelling.casefold()] = {
            **term.model_dump(),
            'authorship': 'user_accepted' if user_accepted else 'dream_verified',
        }
        change = ReviewChange(
            change_id=str(uuid5(NAMESPACE_URL, uid + ':' + key)),
            kind='other',
            title='Add vocabulary: ' + term.spelling,
            edit_kind='vocabulary',
            before='',
            after=term.spelling,
            created_at=datetime.now(timezone.utc),
        )
        if records:
            ref = next((ref for ref in term.evidence if base_ref(ref) in records), '')
            if ref:
                evidence_edit = SimpleNamespace(
                    kind='vocabulary',
                    target=ref,
                    other='',
                    before='',
                    after=term.spelling,
                    reason=change.title,
                    evidence=term.evidence,
                )
                viewed = dream_change_view.edit_change(uid, evidence_edit, records, key)
                change.context = viewed.context
                change.refs = (
                    [
                        ChangeRef(
                            type='conversation',
                            id=base_ref(ref).partition('/')[2],
                            label=proposal_label(records[base_ref(ref)]),
                        )
                    ]
                    if ref.startswith('conversations/')
                    else []
                )
        review_changes.record_agent_change(
            uid,
            change,
            [
                AgentEdit(
                    collection='dream_vocabulary',
                    document_id='current',
                    patch=review_store.encode_doc(uid, {'source': list(merged.values())[-500:]}),
                )
            ],
            edit_key=key,
            expected_documents={'current': raw},
            expected_records=expected_records,
        )
        status = 'applied'
    return status


def answer_proposal(uid, proposal, source, decision):
    if decision == 'dismiss':
        review_changes.suppress_agent_change(uid, source['edit_key'])
        return False
    records = revalidate_proposal(uid, source)
    selected = proposal.operation or proposal.edit
    try:
        status = (
            apply_edit(uid, selected, records, expected_records=source.get('fences'), authority='user')
            if selected
            else apply_vocabulary(uid, [proposal.vocabulary], expected_records=source.get('fences'), user_accepted=True)
        )
    except (review_store.ReviewConflict, review_store.ReviewNotFound):
        raise
    except ValueError as exc:
        if str(exc) == 'agent_vocabulary_cap':
            raise review_store.ReviewConflict('agent_vocabulary_cap') from exc
        raise review_store.ReviewConflict('Dream proposal no longer valid') from exc
    if status == 'suppressed':
        raise review_store.ReviewConflict('Dream proposal was suppressed')
    return status == 'applied'


def validate_spelling(edit, records, *, authority='dream'):
    reason = spelling_rejection(edit)
    if reason:
        raise ValueError('agent_' + reason)
    if isinstance(edit, HarnessEdit) and edit.kind == 'spelling':
        row = records[base_ref(edit.target)]
        collection = base_ref(edit.target).partition('/')[0]
        if '#' in edit.target:
            values = [(cited_value(edit.target, records) or {}).get('text', '')]
        elif collection == 'people':
            values = [row.get('name', '')]
        elif collection in {'memory_items', 'memories'}:
            values = [row.get('content', '')]
        else:
            generated = {
                key: value
                for key, value in (row.get('structured') or {}).items()
                if key in {'title', 'overview', 'sections', 'note_claims'}
            }
            changed = _replace_tree(generated, edit.before, edit.after)
            values = [segment.get('text', '') for segment in row.get('transcript_segments') or []]
            if generated != changed:
                values.append(edit.before)
        if not any(
            (isinstance(value, str) and replace_term(value, edit.before, edit.after) != value for value in values)
        ):
            raise ToolError(
                'agent_target_term_missing',
                field='before',
                ref=edit.target,
                expected='An exact whole term present in this record',
            )
    if (
        edit.kind == 'spelling'
        and '#' in edit.target
        and (not verbatim_quote(edit.before, cited_value(edit.target, records)))
    ):
        raise ToolError(
            'agent_target_quote_mismatch', field='before', ref=edit.target, expected='Exact text in this cited segment'
        )
    if edit.kind == 'spelling' and (
        not edit.before or not edit.after or len(edit.before) > 50 or (len(edit.after) > 50)
    ):
        raise ValueError('agent_invalid_spelling')


def validate_summary(edit, records, *, authority='dream'):
    row = records[base_ref(edit.target)]
    validate_summary_edit(edit, row, full=isinstance(edit, HarnessEdit), authority=authority)


def validate_task(edit, records, *, authority='dream'):
    row = records[base_ref(edit.target)]
    collection, _separator, _key_id = base_ref(edit.target).partition('/')
    if authority == 'dream':
        reason = task_rejection(edit, row, records)
        if reason:
            raise ValueError('agent_' + reason)
    if collection != 'action_items' or row.get('status', 'active') != 'active':
        raise ValueError('agent_invalid_task')


def validate_hygiene(edit, records, *, authority='dream'):
    validate_memory_hygiene(edit, records)


def validate_required_intake(edit, records, *, authority='dream'):
    dream_required_intake.validate(edit, records, authority=authority)


def apply_required_intake(uid, edit, records, change, key, row, *, expected_records=None, authority='dream'):
    return dream_required_intake.apply(
        uid, edit, records, change, key, row, expected_records=expected_records, authority=authority
    )


def validate_memory(edit, records, *, authority='dream'):
    row = records[base_ref(edit.target)]
    collection, _separator, key_id = base_ref(edit.target).partition('/')
    if collection not in {'memories', 'memory_items'}:
        raise ValueError('agent_invalid_memory')
    MemoryEdit(memory_id=key_id, content=edit.after)
    if edit.kind == 'memory' and edit.before and (edit.before != row.get('content')):
        raise review_store.ReviewConflict('Dream memory changed')
    if edit.kind == 'merge_memories':
        other = records.get(base_ref(edit.other))
        if (
            not other
            or base_ref(edit.other) == base_ref(edit.target)
            or edit.other.partition('/')[0] not in {'memories', 'memory_items'}
        ):
            raise ValueError('agent_missing_duplicate')
        if any(
            (
                row.get(field) != other.get(field)
                for field in ('visibility', 'subject_scope', 'subject_entity_id', 'slot', 'memory_tier')
            )
        ):
            raise review_store.ReviewConflict('Duplicate facts must share visibility and subject')


def validate_entity(edit, records, *, authority='dream'):
    row = records[base_ref(edit.target)]
    collection, _separator, _key_id = base_ref(edit.target).partition('/')
    if collection not in {'entity', 'knowledge_nodes', 'people', 'workstreams'} or not row.get('entity_id'):
        raise ValueError('agent_invalid_entity')
    if edit.kind == 'entity_summary' and (not edit.after.strip() or len(edit.after) > 16000):
        raise ValueError('agent_invalid_entity_summary')
    if edit.kind == 'merge_people':
        other = records.get(base_ref(edit.other))
        if (
            not other
            or row.get('type') != 'person'
            or other.get('type') != 'person'
            or (row['entity_id'] == other.get('entity_id'))
        ):
            raise ValueError('agent_invalid_person_merge')
        if authority == 'dream':
            from utils.agent_capabilities.cleanup_edits import require_unprotected_person

            require_unprotected_person(row)
            require_unprotected_person(other)


def validate_cleanup(edit, records, *, authority='dream'):
    dream_cleanup_edits.validate_cleanup(edit, records, authority=authority)


def validate_edit(edit, records, *, authority='dream'):
    if isinstance(edit, HarnessEdit):
        tool_model('propose_edit', authority).model_validate({'edit': edit.model_dump()})
    if not has_ref(edit.target, records) or any((not has_ref(ref, records) for ref in edit.evidence)):
        raise ValueError('agent_unknown_evidence')
    row = records[base_ref(edit.target)]
    _collection, _separator, key_id = base_ref(edit.target).partition('/')
    if not _separator or not key_id or '/' in key_id:
        raise ValueError('agent_invalid_target')
    if row.get('deleted') and _collection in {'memories', 'memory_items', 'conversations'}:
        raise review_store.ReviewStale('Dream target deleted')
    if row.get('is_locked') or row.get('deleted') or row.get('discarded') or row.get('is_dismissed'):
        raise review_store.ReviewConflict('Dream target unavailable')
    from utils.agent_capabilities.registry import get_kind

    get_kind(edit.kind).validate(edit, records, authority=authority)


def apply_cleanup(uid, edit, records, change, key, row, *, expected_records=None, authority='dream'):
    return dream_cleanup_edits.apply_cleanup(
        uid, edit, records, change, key, expected_records=expected_records, authority=authority
    )


def apply_hygiene(uid, edit, records, change, key, row, *, expected_records=None, authority='dream'):
    change.refs = [
        ChangeRef(type='memory', id=base_ref(ref).split('/', 1)[1], label=proposal_label(records[base_ref(ref)]))
        for ref in (edit.target, *([edit.other] if edit.kind == 'merge_memories' else []))
    ]
    review_memory_hygiene.record_change(uid, change, edit, key, expected_records=expected_records)
    return 'applied'


def apply_entity(uid, edit, records, change, key, row, *, expected_records=None, authority='dream'):
    entity_id = row.get('entity_id')
    if not entity_id:
        raise ValueError('agent_invalid_entity')
    cache_ref = review_store.user(uid).collection('entity_pages').document(entity_id)
    raw = cache_ref.get().to_dict()
    current = review_store.decode_doc(uid, raw) or {}
    if edit.before != current.get('summary', ''):
        raise review_store.ReviewConflict('Dream entity summary changed')
    patch = review_store.encode_doc(uid, {'summary': edit.after, 'updated_at': change.created_at})
    review_changes.record_agent_change(
        uid,
        change,
        [AgentEdit(collection='entity_pages', document_id=entity_id, patch=patch)],
        edit_key=key,
        expected_documents={entity_id: raw},
        expected_records=expected_records,
    )
    return 'applied'


def apply_people(uid, edit, records, change, key, row, *, expected_records=None, authority='dream'):
    other = records.get(base_ref(edit.other))
    if not other or row.get('type') != 'person' or other.get('type') != 'person':
        raise ValueError('agent_invalid_person_merge')
    review_changes.merge_review_entities(
        uid, change, row['entity_id'], other['entity_id'], edit_key=key, expected_records=expected_records
    )
    return 'applied'


def apply_memory(uid, edit, records, change, key, row, *, expected_records=None, authority='dream'):
    content = edit.after if edit.kind != 'spelling' else replace_term(row['content'], edit.before, edit.after)
    duplicate = (
        base_ref(edit.other).split('/')[-1] if edit.kind == 'merge_memories' and has_ref(edit.other, records) else None
    )
    if edit.kind == 'merge_memories' and (not duplicate):
        raise ValueError('agent_missing_duplicate')
    review_changes.record_agent_change(
        uid,
        change,
        [],
        edit_key=key,
        expected_records=expected_records,
        memory_edit=MemoryEdit(
            memory_id=base_ref(edit.target).split('/')[-1], content=content, duplicate_memory_id=duplicate
        ),
    )
    return 'applied'


def patch_task(
    uid, edit, records, change, key, row, raw, collection, key_id, *, expected_records=None, authority='dream'
):
    if collection != 'action_items' or raw.get('status', 'active') != 'active':
        raise ValueError('agent_invalid_task')
    if raw.get('account_generation', 0) != get_task_workflow_control(uid).account_generation:
        raise review_store.ReviewConflict('Dream task generation changed')
    if raw.get('updated_at') != row.get('updated_at') or raw.get('status', 'active') != row.get('status', 'active'):
        raise review_store.ReviewConflict('Dream task changed')
    if authority == 'dream':
        reason = task_rejection(edit, raw, records)
        if reason:
            raise ValueError('agent_' + reason)
    patch = {
        'status': 'completed' if edit.kind == 'close_task' else 'cancelled',
        'completed': edit.kind == 'close_task',
        'completed_at': datetime.now(timezone.utc) if edit.kind == 'close_task' else None,
    }
    return patch


def patch_summary(
    uid, edit, records, change, key, row, raw, collection, key_id, *, expected_records=None, authority='dream'
):
    current = conversations.prepare_conversation_for_read(copy.deepcopy(raw), uid)
    if current is None:
        if conversations.is_soft_deleted(raw):
            raise review_store.ReviewStale('Dream conversation unavailable')
        raise review_store.ReviewConflict('Dream conversation unavailable')
    fields = [edit.kind, 'sections', 'note_claims'] if edit.kind == 'overview' else [edit.kind]
    if (
        current.get('transcript_segments') != row.get('transcript_segments')
        or any(((current.get('structured') or {}).get(k) != (row.get('structured') or {}).get(k) for k in fields))
        or current.get('user_title') != row.get('user_title')
    ):
        raise review_store.ReviewConflict('Dream conversation changed')
    validate_summary_edit(edit, current, full=isinstance(edit, HarnessEdit), authority=authority)
    patch: dict[str, Any] = {'structured.' + edit.kind: edit.after}
    if authority == 'user' and isinstance(edit, HarnessEdit) and (edit.kind == 'title') and current.get('user_title'):
        patch = {'user_title': edit.after}
    if edit.kind == 'overview':
        patch.update({'structured.sections': [], 'structured.note_claims': []})
    change.kind = 'title_conversation' if edit.kind == 'title' else 'other'
    change.snippet = edit.after
    change.refs = [
        ChangeRef(type='conversation', id=key_id, label=edit.after if edit.kind == 'title' else 'Conversation')
    ]
    return patch


def patch_spelling(
    uid, edit, records, change, key, row, raw, collection, key_id, *, expected_records=None, authority='dream'
):
    if collection == 'people':
        if raw.get('name') != row.get('name'):
            raise review_store.ReviewConflict('Dream person changed')
        patch = {'name': replace_term(row['name'], edit.before, edit.after)}
    elif collection == 'conversations':
        current = conversations.prepare_conversation_for_read(copy.deepcopy(raw), uid)
        if current is None:
            if conversations.is_soft_deleted(raw):
                raise review_store.ReviewStale('Dream conversation unavailable')
            raise review_store.ReviewConflict('Dream conversation unavailable')
        if current.get('transcript_segments') != row.get('transcript_segments') or current.get('structured') != row.get(
            'structured'
        ):
            raise review_store.ReviewConflict('Dream conversation changed')
        structured = current.get('structured') or {}
        if '#' not in edit.target:
            structured = _replace_tree(structured, edit.before, edit.after)
        patch = {}
        if structured.get('title') != (current.get('structured') or {}).get('title'):
            patch['structured.title'] = structured['title']
        if isinstance(edit, HarnessEdit) and '#' not in edit.target:
            for field in ('overview', 'sections', 'note_claims'):
                if structured.get(field) != (current.get('structured') or {}).get(field):
                    patch['structured.' + field] = structured[field]
        if not isinstance(edit, HarnessEdit) and '#' not in edit.target and current.get('user_title'):
            patch['user_title'] = replace_term(current['user_title'], edit.before, edit.after)
        change.refs = [
            ChangeRef(
                type='conversation',
                id=key_id,
                label='Conversation' + (' #' + edit.target.partition('#')[2] if '#' in edit.target else ''),
            )
        ]
        from utils.agent_capabilities import transcripts

        corrections = transcripts.entries(edit, current, authority=authority, change_id=change.change_id)
        if corrections:
            from database.review_transcript_changes import record_change

            record_change(
                uid,
                change,
                patch,
                corrections,
                edit_key=key,
                expected_records=expected_records,
                expected_document=raw,
                authority=authority,
            )
            return 'applied'
    else:
        raise ValueError('agent_unsupported_spelling_target')
    return patch


def apply_edit(uid, edit, records, *, expected_records=None, authority='dream'):
    from utils.agent_capabilities.registry import get_kind

    if authority not in {'user', 'dream'}:
        raise ValueError('agent_invalid_authority')
    validate_edit(edit, records, authority=authority)
    key = edit_key(edit, records)
    if authority == 'user':
        from uuid import uuid4

        key = 'agent:user:' + str(uuid4())
    if authority == 'dream' and (not review_changes.agent_change_allowed(uid, key)):
        return 'suppressed'
    row = records[base_ref(edit.target)]
    change = dream_change_view.edit_change(uid, edit, records, key)
    return get_kind(edit.kind).apply(
        uid, edit, records, change, key, row, expected_records=expected_records, authority=authority
    )


def apply_fields(uid, edit, records, change, key, row, *, expected_records=None, authority='dream'):
    collection, key_id = base_ref(edit.target).split('/', 1)
    raw = review_store.user(uid).collection(collection).document(key_id).get().to_dict()
    if not raw and collection in {'memories', 'memory_items', 'conversations'}:
        raise review_store.ReviewStale('Dream target deleted')
    if not raw or raw.get('is_locked'):
        raise review_store.ReviewConflict('Dream target unavailable')
    from utils.agent_capabilities.registry import get_kind

    patch = get_kind(edit.kind).patch(
        uid,
        edit,
        records,
        change,
        key,
        row,
        raw,
        collection,
        key_id,
        expected_records=expected_records,
        authority=authority,
    )
    if isinstance(patch, str):
        return patch
    review_changes.record_agent_change(
        uid,
        change,
        [
            AgentEdit(
                collection=cast(
                    Literal[
                        'knowledge_nodes', 'people', 'conversations', 'action_items', 'entity_pages', 'dream_vocabulary'
                    ],
                    collection,
                ),
                document_id=key_id,
                patch=patch,
            )
        ],
        edit_key=key,
        expected_documents={key_id: raw},
        expected_records=expected_records,
    )
    return 'applied'


def apply_spelling(uid, edit, records, change, key, row, *, expected_records=None, authority='dream'):
    handler = apply_memory if base_ref(edit.target).split('/')[0] in {'memory_items', 'memories'} else apply_fields
    return handler(uid, edit, records, change, key, row, expected_records=expected_records, authority=authority)


def apply_memory_merge(uid, edit, records, change, key, row, *, expected_records=None, authority='dream'):
    handler = apply_hygiene if isinstance(edit, HarnessEdit) else apply_memory
    return handler(uid, edit, records, change, key, row, expected_records=expected_records, authority=authority)


def validate_vocabulary(term, records, *, authority='dream'):
    reason = vocabulary_rejection(term)
    if reason:
        raise ValueError('agent_' + reason)


def apply_vocabulary_entry(
    uid, term, records, change=None, key=None, row=None, *, expected_records=None, authority='dream'
):
    return apply_vocabulary(
        uid,
        [term],
        expected_records=expected_records,
        user_accepted=authority == 'user',
        verified=authority == 'dream',
        records=records,
    )
