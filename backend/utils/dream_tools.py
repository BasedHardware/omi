"""Typed writes through Review seams. No hard deletes or unjournaled user edits."""

import copy
import hashlib
import json
import re
from datetime import datetime, timezone
from uuid import uuid5, NAMESPACE_URL
from typing import Any

from database import candidates, conversations, frame_requests, review_changes, review_store
from database.review_changes import AgentEdit
from database.review_memory_changes import MemoryEdit
from database.task_intelligence_control import get_task_workflow_control
from models.action_item import EvidenceRef, EvidenceKind, EvidenceScope, TaskCreatePayload
from models.candidate import CandidateCreate, TaskCreateCandidate
from models.review import AgentProposalItem, ChangeRef, ReviewChange, ReviewItemV2
from utils.entity_pages import resolve_entity
from utils.dream_guards import spelling_rejection, summary_rejection, task_rejection, vocabulary_rejection
from utils.dream_grounding import spelling_grounding_rejection, spelling_question


def edit_key(edit, records=None):
    # Semantic key excludes run id and prose. Undo cannot be bypassed next pass.
    kind = edit.kind
    value = [edit.target, edit.other, edit.before.casefold(), edit.after.casefold()]
    if (
        records
        and edit.target in records
        and edit.target.split('/')[0] in {'memories', 'memory_items'}
        and edit.kind in {'memory', 'spelling'}
    ):
        row = records[edit.target]
        after = replace_term(row['content'], edit.before, edit.after) if edit.kind == 'spelling' else edit.after
        # Undo appends a tail with another id. Suppress the same semantic edit
        # even if a later plan chooses the other memory-correction tool kind.
        kind = 'memory'
        value = [
            row['content'],
            after,
            row.get('subject_scope'),
            row.get('subject_entity_id'),
            row.get('slot'),
            row.get('visibility'),
        ]

    if edit.kind == 'merge_memories' and records and edit.target in records and edit.other in records:
        rows = [records[edit.target], records[edit.other]]
        value = sorted(
            [
                json.dumps([row.get('content'), row.get('subject_entity_id'), row.get('slot')], sort_keys=True)
                for row in rows
            ]
        )
    elif edit.kind == 'merge_people' or edit.kind == 'merge_memories':
        value = sorted([edit.target, edit.other])
    return 'dream:' + kind + ':' + hashlib.sha256(json.dumps(value).encode()).hexdigest()


def replace_term(text, before, after):
    return re.sub(r'(?<!\w)' + re.escape(before) + r'(?!\w)', lambda _: after, text)


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
                }
                else v
            )
            for k, v in value.items()
        }
    return value


def validate_summary_edit(edit, row):
    if edit.kind not in {'title', 'overview'}:
        return
    if row.get('is_locked') or not conversations.is_visible_conversation(row):
        raise review_store.ReviewConflict('Dream conversation unavailable')
    if edit.kind == 'title' and row.get('user_title'):
        raise review_store.ReviewConflict('Dream title was set by the user')
    if edit.before != ((row.get('structured') or {}).get(edit.kind) or ''):
        raise review_store.ReviewConflict('Dream summary changed')
    reason = summary_rejection(edit, row)
    if reason:
        raise ValueError('dream_summary_' + reason)


def validate_edit(edit, records):
    reason = spelling_rejection(edit)
    if reason:
        raise ValueError('dream_' + reason)
    if edit.target not in records or any(ref not in records for ref in edit.evidence):
        raise ValueError('dream_unknown_evidence')
    reason = task_rejection(edit, records[edit.target], records)
    if reason:
        raise ValueError('dream_' + reason)
    row = records[edit.target]
    validate_summary_edit(edit, row)
    if edit.kind == 'spelling' and (not edit.before or not edit.after or len(edit.before) > 50 or len(edit.after) > 50):
        raise ValueError('dream_invalid_spelling')
    collection, separator, key_id = edit.target.partition('/')
    if not separator or not key_id or '/' in key_id:
        raise ValueError('dream_invalid_target')
    if row.get('is_locked') or row.get('deleted') or row.get('discarded') or row.get('is_dismissed'):
        raise review_store.ReviewConflict('Dream target unavailable')
    if edit.kind in {'close_task', 'retire_task'}:
        if collection != 'action_items' or row.get('status', 'active') != 'active':
            raise ValueError('dream_invalid_task')
    elif edit.kind in {'memory', 'merge_memories'}:
        if collection not in {'memories', 'memory_items'}:
            raise ValueError('dream_invalid_memory')
        MemoryEdit(memory_id=key_id, content=edit.after)
        if edit.kind == 'memory' and edit.before and edit.before != row.get('content'):
            raise review_store.ReviewConflict('Dream memory changed')
        if edit.kind == 'merge_memories':
            other = records.get(edit.other)
            if (
                not other
                or edit.other == edit.target
                or edit.other.partition('/')[0] not in {'memories', 'memory_items'}
            ):
                raise ValueError('dream_missing_duplicate')
            if any(
                row.get(field) != other.get(field)
                for field in ('visibility', 'subject_scope', 'subject_entity_id', 'slot')
            ):
                raise review_store.ReviewConflict('Duplicate facts must share visibility and subject')
    elif edit.kind in {'merge_people', 'entity_summary'}:
        if collection not in {'entity', 'knowledge_nodes', 'people', 'workstreams'} or not row.get('entity_id'):
            raise ValueError('dream_invalid_entity')
        if edit.kind == 'entity_summary' and (not edit.after.strip() or len(edit.after) > 16000):
            raise ValueError('dream_invalid_entity_summary')
        if edit.kind == 'merge_people':
            other = records.get(edit.other)
            if (
                not other
                or row.get('type') != 'person'
                or other.get('type') != 'person'
                or row['entity_id'] == other.get('entity_id')
            ):
                raise ValueError('dream_invalid_person_merge')


def apply_edit(uid, edit, records, *, expected_records=None):
    validate_edit(edit, records)
    key = edit_key(edit, records)
    if not review_changes.agent_change_allowed(uid, key):
        return 'suppressed'
    row = records[edit.target]
    change = ReviewChange(
        change_id=str(uuid5(NAMESPACE_URL, uid + ":" + key)),
        kind='other',
        title=edit.reason,
        reason=edit.reason,
        created_at=datetime.now(timezone.utc),
    )
    if edit.kind == 'entity_summary':
        entity_id = row.get('entity_id')
        if not entity_id:
            raise ValueError('dream_invalid_entity')
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
    if edit.kind == 'merge_people':
        other = records.get(edit.other)
        if not other or row.get('type') != 'person' or other.get('type') != 'person':
            raise ValueError('dream_invalid_person_merge')
        review_changes.merge_review_entities(
            uid, change, row['entity_id'], other['entity_id'], edit_key=key, expected_records=expected_records
        )
        return 'applied'
    if edit.kind in {'memory', 'merge_memories'} or (
        edit.kind == 'spelling' and edit.target.split('/')[0] in {'memories', 'memory_items'}
    ):
        content = edit.after if edit.kind != 'spelling' else replace_term(row['content'], edit.before, edit.after)
        duplicate = edit.other.split('/')[-1] if edit.kind == 'merge_memories' and edit.other in records else None
        if edit.kind == 'merge_memories' and not duplicate:
            raise ValueError('dream_missing_duplicate')
        review_changes.record_agent_change(
            uid,
            change,
            [],
            edit_key=key,
            expected_records=expected_records,
            memory_edit=MemoryEdit(
                memory_id=edit.target.split('/')[-1], content=content, duplicate_memory_id=duplicate
            ),
        )
        return 'applied'
    collection, key_id = edit.target.split('/', 1)
    raw = review_store.user(uid).collection(collection).document(key_id).get().to_dict()
    if not raw or raw.get('is_locked'):
        raise review_store.ReviewConflict('Dream target unavailable')
    if edit.kind in {'close_task', 'retire_task'}:
        if collection != 'action_items' or raw.get('status', 'active') != 'active':
            raise ValueError('dream_invalid_task')
        if raw.get('account_generation', 0) != get_task_workflow_control(uid).account_generation:
            raise review_store.ReviewConflict('Dream task generation changed')
        if raw.get('updated_at') != row.get('updated_at') or raw.get('status', 'active') != row.get('status', 'active'):
            raise review_store.ReviewConflict('Dream task changed')
        reason = task_rejection(edit, raw, records)
        if reason:
            raise ValueError('dream_' + reason)
        patch = {
            'status': 'completed' if edit.kind == 'close_task' else 'cancelled',
            'completed': edit.kind == 'close_task',
            'completed_at': datetime.now(timezone.utc) if edit.kind == 'close_task' else None,
        }
    elif edit.kind in {'title', 'overview'}:
        current = conversations.prepare_conversation_for_read(copy.deepcopy(raw), uid)
        if current is None:
            raise review_store.ReviewConflict('Dream conversation unavailable')
        fields = [edit.kind, 'sections', 'note_claims'] if edit.kind == 'overview' else [edit.kind]
        if (
            current.get('transcript_segments') != row.get('transcript_segments')
            or any((current.get('structured') or {}).get(k) != (row.get('structured') or {}).get(k) for k in fields)
            or current.get('user_title') != row.get('user_title')
        ):
            raise review_store.ReviewConflict('Dream conversation changed')
        validate_summary_edit(edit, current)
        patch = {'structured.' + edit.kind: edit.after}
        if edit.kind == 'overview':
            # Clients compose notes from sections when present. Clear stale projections
            # in the same journal entry so undo restores them with the previous overview.
            patch.update({'structured.sections': [], 'structured.note_claims': []})
        change.kind = 'title_conversation' if edit.kind == 'title' else 'other'
        change.snippet = edit.after
        change.refs = [
            ChangeRef(type='conversation', id=key_id, label=edit.after if edit.kind == 'title' else 'Conversation')
        ]
    elif edit.kind == 'spelling':
        if collection == 'people':
            if raw.get('name') != row.get('name'):
                raise review_store.ReviewConflict('Dream person changed')
            patch = {'name': replace_term(row['name'], edit.before, edit.after)}
        elif collection == 'conversations':
            # Fence the snapshot used for reasoning against concurrent user corrections.
            current = conversations.prepare_conversation_for_read(copy.deepcopy(raw), uid)
            if current is None:
                raise review_store.ReviewConflict('Dream conversation unavailable')
            if current.get('transcript_segments') != row.get('transcript_segments') or current.get(
                'structured'
            ) != row.get('structured'):
                raise review_store.ReviewConflict('Dream conversation changed')
            structured = _replace_tree(current.get('structured') or {}, edit.before, edit.after)
            patch = {}
            if structured.get('title') != (current.get('structured') or {}).get('title'):
                patch['structured.title'] = structured['title']
            if current.get('user_title'):
                patch['user_title'] = replace_term(current['user_title'], edit.before, edit.after)
            segments = copy.deepcopy(current.get('transcript_segments') or [])
            changed_ids = []
            for segment in segments:
                text = replace_term(segment.get('text', ''), edit.before, edit.after)
                if text != segment.get('text'):
                    segment['text'] = text
                    changed_ids.append(segment.get('id'))
            if changed_ids:
                encoded = conversations.encode_conversation_for_write(
                    uid, {'transcript_segments': segments}, current.get('data_protection_level', 'standard')
                )
                patch['transcript_segments'] = encoded['transcript_segments']
        else:
            raise ValueError('dream_unsupported_spelling_target')
    else:
        raise ValueError('dream_unsupported_edit')
    review_changes.record_agent_change(
        uid,
        change,
        [AgentEdit(collection=collection, document_id=key_id, patch=patch)],
        edit_key=key,
        expected_documents={key_id: raw},
        expected_records=expected_records,
    )
    return 'applied'


def apply_grounded_edit(uid, edit, records):
    """Automatic spelling alone requires current independent support and fences.

    Explicit user acceptance keeps using apply_edit through the Review path.
    """
    validate_edit(edit, records)
    sources = {ref: records[ref] for ref in {edit.target, *edit.evidence}}
    fences = proposal_fences(uid, {'records': sources})
    raw_vocabulary = review_store.user(uid).collection('dream_vocabulary').document('current').get().to_dict()
    revalidate_proposal(uid, {'records': sources})
    vocabulary = (review_store.decode_doc(uid, raw_vocabulary) or {}).get('source', [])
    reason = spelling_grounding_rejection(edit, sources, vocabulary)
    if reason:
        raise ValueError('dream_' + reason)
    # Fence the current vocabulary snapshot too; a concurrent removal must win.
    fences['dream_vocabulary/current'] = raw_vocabulary
    return apply_edit(uid, edit, sources, expected_records=fences)


def suggest_spelling(uid, edit, records):
    validate_edit(edit, records)
    review_store.enqueue_review_proposal(
        uid,
        spelling_question(edit),
        edit_key=edit_key(edit, records),
        evidence_version=review_store.fingerprint({ref: records[ref] for ref in {edit.target, *edit.evidence}}),
    )
    return 'suggested'


def proposal_record(uid, ref, snapshot):
    from utils import dream_reads

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
    return dream_reads.read_record(uid, ref)


def revalidate_proposal(uid, source):
    from fastapi import HTTPException

    records = source['records']
    for ref, snapshot in records.items():
        try:
            current = proposal_record(uid, ref, snapshot)
        except (review_store.ReviewNotFound, LookupError, ValueError) as exc:
            raise review_store.ReviewConflict('Dream proposal evidence unavailable') from exc
        except HTTPException as exc:
            if exc.status_code not in {402, 404}:
                raise
            raise review_store.ReviewConflict('Dream proposal evidence unavailable') from exc
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
        if collection in {'entity', 'knowledge_nodes', 'workstreams'}:
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
    return {
        path: review_store.user(uid).collection(path.split('/', 1)[0]).document(path.split('/', 1)[1]).get().to_dict()
        for path in sorted(paths)
    }


def validate_canonical_proposal(uid, edit):
    if edit.kind not in {'memory', 'merge_memories'} and not (
        edit.kind == 'spelling' and edit.target.partition('/')[0] in {'memories', 'memory_items'}
    ):
        return
    from utils.memory.canonical_memory_adapter import read_canonical_memory_item

    refs = [edit.target, *([edit.other] if edit.kind == 'merge_memories' else [])]
    sources = [read_canonical_memory_item(uid, ref.split('/', 1)[1], db_client=review_store.client()) for ref in refs]
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
        for field in ('visibility', 'subject_scope', 'subject_entity_id', 'slot')
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


def suggest_edit(uid, edit, records):
    validate_edit(edit, records)
    key = edit_key(edit, records)
    if not review_changes.agent_change_allowed(uid, key):
        return 'suppressed'
    refs = set([edit.target, *edit.evidence, *([edit.other] if edit.other else [])])
    source: dict[str, Any] = {'records': {ref: records[ref] for ref in refs}, 'edit_key': key, 'auxiliary': {}}
    if edit.kind == 'entity_summary':
        entity_id = records[edit.target]['entity_id']
        raw = review_store.user(uid).collection('entity_pages').document(entity_id).get().to_dict()
        if edit.before != (review_store.decode_doc(uid, raw) or {}).get('summary', ''):
            raise review_store.ReviewConflict('Dream entity summary changed')
        source['auxiliary']['entity_pages/' + entity_id] = raw
    source['fences'] = proposal_fences(uid, source)
    revalidate_proposal(uid, source)
    validate_canonical_proposal(uid, edit)
    if (
        edit.kind in {'close_task', 'retire_task'}
        and records[edit.target].get('account_generation', 0) != get_task_workflow_control(uid).account_generation
    ):
        raise review_store.ReviewConflict('Dream task generation changed')
    item = ReviewItemV2(
        item_id='agent_proposal:' + review_store.safe_id(key),
        kind='agent_proposal',
        title=edit.reason,
        created_at=datetime.now(timezone.utc),
        agent_proposal=AgentProposalItem(
            edit=edit,
            target_label=proposal_label(records[edit.target]),
            other_label=proposal_label(records[edit.other]) if edit.other else None,
        ),
    )
    return review_store.enqueue_review_proposal(
        uid, item, source=source, edit_key=key, evidence_version=review_store.fingerprint(source)
    )


def vocabulary_key(term):
    return 'dream:vocabulary:' + review_store.fingerprint(
        [term.kind, term.spelling.casefold(), sorted(a.casefold() for a in term.aliases)]
    )


def apply_vocabulary(uid, terms, *, expected_records=None):
    status = 'unchanged'
    for term in terms:
        if vocabulary_rejection(term):
            raise ValueError('dream_common_word')
        key = vocabulary_key(term)
        if not review_changes.agent_change_allowed(uid, key):
            status = 'suppressed'
            continue
        ref = review_store.user(uid).collection('dream_vocabulary').document('current')
        raw = ref.get().to_dict()
        existing = (review_store.decode_doc(uid, raw) or {}).get('source', [])
        merged = {row['spelling'].casefold(): row for row in existing}
        # This policy owns additions; never overwrite an existing user term.
        if term.spelling.casefold() in merged:
            continue
        merged[term.spelling.casefold()] = term.model_dump()
        change = ReviewChange(
            change_id=str(uuid5(NAMESPACE_URL, uid + ':' + key)),
            kind='other',
            title='Add vocabulary: ' + term.spelling,
            created_at=datetime.now(timezone.utc),
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


def suggest_vocabulary(uid, term, records):
    if vocabulary_rejection(term) or any(ref not in records for ref in term.evidence):
        raise ValueError('dream_invalid_vocabulary')
    key = vocabulary_key(term)
    if not review_changes.agent_change_allowed(uid, key):
        return 'suppressed'
    source: dict[str, Any] = {
        'records': {ref: records[ref] for ref in term.evidence},
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


def answer_proposal(uid, proposal, source, decision):
    if decision == 'dismiss':
        review_changes.suppress_agent_change(uid, source['edit_key'])
        return False
    records = revalidate_proposal(uid, source)
    try:
        status = (
            apply_edit(uid, proposal.edit, records, expected_records=source.get('fences'))
            if proposal.edit
            else apply_vocabulary(uid, [proposal.vocabulary], expected_records=source.get('fences'))
        )
    except ValueError as exc:
        raise review_store.ReviewConflict('Dream proposal no longer valid') from exc
    if status == 'suppressed':
        raise review_store.ReviewConflict('Dream proposal was suppressed')
    return status == 'applied'


def ask(uid, item, records):
    if item.kind not in {'same_person', 'spelling'}:
        raise ValueError('dream_question_kind')
    review_store.enqueue_review_proposal(uid, item, evidence_version=review_store.fingerprint(records))


def request_frame(uid, question, records):
    screen = records.get(question.screen_ref)
    if not screen or not question.screen_ref.startswith('screen/') or not screen.get('captureEligible'):
        raise ValueError('dream_frame_evidence')
    frame_requests.enqueue_frame_request(
        uid,
        device_id=screen['clientDeviceId'],
        screenshot_id=screen.get('localScreenshotId') or screen['id'],
        dedupe_key=review_store.fingerprint([question.screen_ref, question.question]),
        account_generation=screen.get('accountGeneration', 0),
        requested_ttl_seconds=300,
        device_retention_seconds=screen.get('deviceRetentionSeconds'),
    )


def propose_task(uid, task, records):
    evidence = []
    for ref in task.evidence:
        if ref not in records:
            raise ValueError('dream_task_evidence')
        collection, key = ref.split('/', 1)
        kind = {'conversations': 'conversation', 'memory_items': 'memory_item', 'memories': 'memory_item'}.get(
            collection
        )
        if kind:
            evidence.append(EvidenceRef(kind=EvidenceKind(kind), id=key, scope=EvidenceScope.canonical))
    if not evidence:
        raise ValueError('dream_task_evidence')
    proposal = CandidateCreate(
        TaskCreateCandidate(
            capture_confidence=0.8,
            ownership_confidence=0.8,
            source_surface='dream_agent',
            evidence_refs=evidence,
            task_change=TaskCreatePayload(description=task.description),
        )
    )
    generation = get_task_workflow_control(uid).account_generation
    candidates.create_candidate(
        uid, proposal, idempotency_key=review_store.fingerprint(task.model_dump()), account_generation=generation
    )
