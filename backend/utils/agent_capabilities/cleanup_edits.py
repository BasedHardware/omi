"""Validated reversible people/task/conversation cleanup through the Review journal."""

from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Literal, cast

from database import conversations, review_changes, review_store
from database.action_item_refresh_policy import protected_donor
from database.task_intelligence_control import get_task_workflow_control
from models.agent_refs import base_ref, has_ref
from models.review import ChangeRef
from utils.conversations.fragment_visibility import is_user_curated
from utils.agent_capabilities.guards import timestamp
from utils.agent_capabilities.errors import ToolError

from utils.agent_capabilities.registry import KINDS as REGISTRY

KINDS = frozenset(name for name, spec in REGISTRY.items() if spec.validation == 'validate_cleanup')


def require_unprotected_person(row):
    if any(
        row.get(field)
        for field in (
            'speech_samples',
            'speaker_embedding',
            'user_confirmed',
            'is_user_created',
            'pinned',
            'label_evidence',
        )
    ):
        raise ValueError('agent_person_user_protected')


def require_generated_task(row):
    # Unknown provenance is insufficient permission, even when timestamps happen
    # to match. Existing refresh protection also keeps every edited/linked task.
    if row.get('source') != 'conversation' or protected_donor(row, []):
        raise ValueError('agent_task_user_protected')
    if row.get('status', 'active') != 'active' or row.get('completed') or row.get('deleted'):
        raise ValueError('agent_invalid_task')


def speech(row):
    return ' '.join(' '.join(str(s.get('text') or '').split()) for s in row.get('transcript_segments') or [])


def require_duplicate_capture(left, right, *, authority='dream'):
    for row in (left, right):
        if authority == 'dream' and (
            row.get('status') != 'completed'
            or is_user_curated(row)
            or row.get('manual_speaker_assignments')
            or any(
                segment.get('speaker_label_source') in {'manual', 'carried'}
                for segment in row.get('transcript_segments') or []
            )
        ):
            raise ValueError('agent_conversation_user_protected')
        if not conversations.is_visible_conversation(row) or row.get('is_locked'):
            raise ValueError('agent_invalid_conversation_merge')
    spans = [(timestamp(row.get('started_at')), timestamp(row.get('finished_at'))) for row in (left, right)]
    (a, b), (c, d) = spans
    if a is None or b is None or c is None or d is None or b <= a or d <= c:
        raise ValueError('agent_capture_time_unavailable')
    overlap = (min(b, d) - max(a, c)).total_seconds()
    if overlap <= 0 or overlap / min((b - a).total_seconds(), (d - c).total_seconds()) < 0.5:
        raise ValueError('agent_captures_do_not_overlap')
    left_speech, right_speech = speech(left).casefold(), speech(right).casefold()
    if min(len(left_speech.split()), len(right_speech.split())) < 12:
        raise ValueError('agent_capture_speech_insufficient')
    if max(len(left_speech), len(right_speech)) > 12000 and left_speech != right_speech:
        raise ValueError('agent_capture_similarity_budget')
    if SequenceMatcher(None, left_speech[:12000], right_speech[:12000], autojunk=True).ratio() < 0.92:
        raise ValueError('agent_capture_speech_mismatch')


def validate_cleanup(edit, records, *, authority='dream'):
    ref = base_ref(edit.target)
    if '#' in edit.target:
        raise ToolError(
            'agent_fragment_not_supported', field='target', ref=edit.target, expected='A whole-record ref for cleanup'
        )
    if not has_ref(ref, records):
        raise ToolError(
            'agent_unread_ref', field='target', ref=edit.target, expected='Read this owner record before editing'
        )
    row = records[ref]
    if any(row.get(field) for field in ('deleted', 'is_locked', 'is_dismissed', 'discarded')):
        raise ValueError('agent_target_unavailable')
    collection = ref.partition('/')[0]
    if edit.kind == 'dismiss_person':
        if collection != 'people':
            raise ValueError('agent_invalid_person')
        if authority == 'dream':
            require_unprotected_person(row)
        if edit.before and edit.before != row.get('name'):
            raise ValueError('agent_person_changed')
    elif edit.kind in {'retire_task', 'merge_tasks'}:
        if collection != 'action_items':
            raise ValueError('agent_invalid_task')
        if authority == 'dream':
            require_generated_task(row)
        if edit.before and edit.before != row.get('description'):
            raise ValueError('agent_task_changed')
        if edit.kind == 'merge_tasks':
            other = records.get(base_ref(edit.other))
            if not other or not edit.other.startswith('action_items/') or '#' in edit.other:
                raise ValueError('agent_missing_duplicate')
            if authority == 'dream':
                require_generated_task(other)
            if any(row.get(key) != other.get(key) for key in ('due_at', 'owner', 'account_generation')):
                raise ValueError('agent_task_merge_metadata_mismatch')
    elif edit.kind == 'merge_conversations':
        other = records.get(base_ref(edit.other))
        if (
            collection != 'conversations'
            or not other
            or not edit.other.startswith('conversations/')
            or '#' in edit.other
        ):
            raise ValueError('agent_missing_duplicate')
        require_duplicate_capture(row, other, authority=authority)
    elif edit.kind == 'set_language':
        if (
            collection != 'conversations'
            or row.get('status') != 'completed'
            or (authority == 'dream' and row.get('language_user_set'))
        ):
            raise ValueError('agent_invalid_language_target')
        parts = edit.after.split('-')
        if (
            not 2 <= len(parts[0]) <= 3
            or not parts[0].isalpha()
            or any(not part.isascii() or not 2 <= len(part) <= 8 or not part.isalnum() for part in parts)
        ):
            raise ValueError('agent_invalid_language_tag')
        if edit.before != (row.get('language') or '') or edit.before == edit.after:
            raise ValueError('agent_language_changed')
        if len(speech(row).split()) < 20:
            raise ValueError('agent_language_speech_insufficient')


def apply_cleanup(uid, edit, records, change, key, *, expected_records=None, authority='dream'):
    validate_cleanup(edit, records, authority=authority)
    ref = base_ref(edit.target)
    collection, document_id = ref.split('/', 1)
    raw = review_store.user(uid).collection(collection).document(document_id).get().to_dict()
    current = conversations.prepare_conversation_for_read(raw, uid) if collection == 'conversations' and raw else raw
    if current is None:
        raise review_store.ReviewConflict('Cleanup target unavailable')
    # The verified snapshot and every cited record are fenced by the caller.
    # Re-run structural guards on the current target before the transaction.
    live = dict(records, **{ref: current})
    validate_cleanup(edit, live, authority=authority)
    fences = dict(expected_records or {})
    fences.setdefault(ref, raw)
    control_ref = review_store.user(uid).collection('task_intelligence_control').document('state')
    control = control_ref.get().to_dict()
    fences.setdefault('task_intelligence_control/state', control)
    if (
        collection == 'action_items'
        and int(raw.get('account_generation', 0)) != get_task_workflow_control(uid).account_generation
    ):
        raise review_store.ReviewConflict('Cleanup task generation changed')
    witnesses = {}
    if edit.kind in {'merge_tasks', 'merge_conversations'} and edit.other:
        other_ref = base_ref(edit.other)
        other_collection, other_id = other_ref.split('/', 1)
        # Use the staged witness, never replace it with an unverified reread.
        if other_ref not in fences:
            fences[other_ref] = review_store.user(uid).collection(other_collection).document(other_id).get().to_dict()
        witnesses[other_ref] = fences[other_ref]
    now = datetime.now(timezone.utc)
    if edit.kind == 'dismiss_person':
        patch = {'is_dismissed': True, 'dismissed_at': now}
    elif edit.kind in {'retire_task', 'merge_tasks'}:
        patch = {
            'status': 'superseded' if edit.other else 'cancelled',
            'completed': False,
            'completed_at': None,
            'deleted': True,
            'superseded_by': edit.other.split('/', 1)[1] if edit.other else None,
        }
    elif edit.kind == 'merge_conversations':
        patch = {'dream_duplicate_of': edit.other.split('/', 1)[1], 'dream_duplicate': True}
    else:
        patch = {'language': edit.after}
    ref_types: dict[str, Literal['person', 'task', 'conversation']] = {
        'people': 'person',
        'action_items': 'task',
        'conversations': 'conversation',
    }
    ref_type = ref_types[collection]
    label = row_label(records[ref])
    change.refs = [ChangeRef(type=ref_type, id=document_id, label=label)]
    if edit.other:
        change.refs.append(
            ChangeRef(type=ref_type, id=edit.other.split('/', 1)[1], label=row_label(records[base_ref(edit.other)]))
        )
    review_changes.record_agent_change(
        uid,
        change,
        [
            review_changes.AgentEdit(
                collection=cast(Literal['people', 'action_items', 'conversations'], collection),
                document_id=document_id,
                patch=patch,
            )
        ],
        edit_key=key,
        expected_documents={document_id: raw},
        expected_records=fences,
        exact_undo=True,
        witness_records=witnesses,
    )
    return 'applied'


def row_label(row):
    return ' '.join(
        str(
            row.get('description')
            or row.get('name')
            or row.get('content')
            or (row.get('structured') or {}).get('title')
            or 'Item'
        ).split()
    )[:180]
