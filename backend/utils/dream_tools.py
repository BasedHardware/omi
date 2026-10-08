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
from models.review import ReviewChange
from utils.entity_pages import write_entity_summary


def edit_key(edit, records=None):
    # Semantic key excludes run id and prose. Undo cannot be bypassed next pass.
    value = [edit.target, edit.other, edit.before.casefold(), edit.after.casefold()]
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
    return 'dream:' + edit.kind + ':' + hashlib.sha256(json.dumps(value).encode()).hexdigest()


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
                if k in {'text', 'title', 'description', 'content', 'overview', 'sections', 'items'}
                else v
            )
            for k, v in value.items()
        }
    return value


def apply_edit(uid, edit, records):
    if edit.target not in records or any(ref not in records for ref in edit.evidence):
        raise ValueError('dream_unknown_evidence')
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
        write_entity_summary(uid, entity_id, edit.after, change=change, edit_key=key)
        return 'applied'
    if edit.kind == 'merge_people':
        other = records.get(edit.other)
        if not other or row.get('type') != 'person' or other.get('type') != 'person':
            raise ValueError('dream_invalid_person_merge')
        review_changes.merge_review_entities(uid, change, row['entity_id'], other['entity_id'], edit_key=key)
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
        patch = {
            'status': 'completed' if edit.kind == 'close_task' else 'cancelled',
            'completed': edit.kind == 'close_task',
            'completed_at': datetime.now(timezone.utc) if edit.kind == 'close_task' else None,
        }
    elif edit.kind == 'spelling':
        if not edit.before or not edit.after or len(edit.before) > 50 or len(edit.after) > 50:
            raise ValueError('dream_invalid_spelling')
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
            patch = {'structured': structured}
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
                patch.update(encoded)
                # Clear stale references with nulls (reversible journal snapshots);
                # DELETE_FIELD sentinels are not serializable journal payloads.
                for segment_id in changed_ids:
                    for path in conversations.summary_source_reference_invalidations(structured, segment_id):
                        parts = path.split('.')[1:]
                        branch = structured
                        for part in parts[:-1]:
                            branch = branch.setdefault(part, {})
                        branch[parts[-1]] = conversations.summary_source_reference_invalidations(
                            structured, segment_id
                        )[path]
                invalidated = {}
                conversations.invalidate_client_processing(invalidated)
                patch.update({name: None for name in invalidated})
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
    )
    return 'applied'


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
