"""Project encrypted owner reports onto the mobile contract using owner-visible labels."""

from datetime import datetime, timezone

from fastapi import HTTPException

from config.dream_agent import Caps, eligible, mode, self_report_enabled
from database import dream_store, review_store
from database._client import get_firestore_client
from models.dream_report import DreamRun, DreamRunsResponse
from utils import dream_reads


def require_owner(uid):
    if not self_report_enabled() or mode() == 'off':
        raise HTTPException(404, detail='dream_report_disabled')
    user = get_firestore_client().collection('users').document(uid).get().to_dict() or {}
    if not eligible(uid, user):
        raise HTTPException(404, detail='dream_report_disabled')


def target_label(ref, row):
    if not row:
        return 'Deleted item'
    collection = ref.partition('/')[0]
    structured = row.get('structured') or {}
    if collection == 'conversations':
        label, kind = row.get('user_title') or structured.get('title'), 'Conversation'
        if not isinstance(label, str) or not label.strip():
            return 'Untitled conversation'
    elif collection in {'memories', 'memory_items'}:
        label, kind = row.get('content'), 'Memory'
    elif collection == 'people':
        label, kind = row.get('name'), 'Person'
    elif collection in {'action_items', 'candidates'}:
        label, kind = row.get('description'), 'Task'
    else:
        label, kind = row.get('name') or row.get('label'), 'Entity'
    if not isinstance(label, str) or not label.strip():
        return 'Deleted item'
    return f'{kind} · {" ".join(label.split())[:80]}'


def project_run(uid, run_id, doc):
    source = (review_store.decode_doc(uid, doc) or {}).get('source', {})
    proposed = source.get('proposed') or {}
    outcomes = source.get('outcomes') or []
    records = {}
    for edit in proposed.get('edits', []):
        ref = edit['target']
        if ref in records:
            continue
        try:
            # Identity enrichment uses entity/<typed-id>, rather than dirty collection refs.
            records[ref] = (
                dream_reads.resolve_entity(uid, ref.removeprefix('entity/'))
                if ref.startswith('entity/')
                else dream_reads.read_record(uid, ref)
            )
        except (review_store.ReviewNotFound, ValueError):
            records[ref] = None
        except HTTPException as exc:
            if exc.status_code not in {402, 404}:
                raise
            records[ref] = None
    edit_outcomes = [row for row in outcomes if 'key' in row]
    edits = []
    for index, edit in enumerate(proposed.get('edits', [])):
        outcome = edit_outcomes[index]['status'] if index < len(edit_outcomes) else 'invalid_evidence'
        if outcome not in {'shadow', 'applied', 'suppressed', 'suggest_only', 'edit_cap', 'invalid_evidence'}:
            outcome = 'invalid_evidence'
        edits.append(
            {
                'kind': edit['kind'],
                'target_label': target_label(edit['target'], records.get(edit['target'])),
                'before': edit.get('before', ''),
                'after': edit.get('after', ''),
                'reason': edit.get('reason', ''),
                'evidence_count': len(edit.get('evidence', [])),
                'outcome': outcome,
            }
        )
    status = source.get('status', 'failed')
    if status == 'not_admitted' and source.get('reason') == 'idle':
        status = 'idle'
    elif source.get('error_type') == 'TimeoutError':
        status = 'deadline'
    elif status not in {'complete', 'failed', 'deadline'}:
        status = 'failed'
    return DreamRun.model_validate(
        dict(
            run_id=run_id,
            created_at=doc['created_at'],
            trigger=doc.get('trigger', 'schedule'),
            status=status,
            error_type=source.get('error_type'),
            records_read=doc.get('records_read', source.get('records_read', source.get('dirty_read', 0))),
            records_queued_after=doc.get('records_queued_after', source.get('records_queued_after', 0)),
            dirty_dropped=source.get('dirty_dropped', 0),
            tokens=source.get('tokens', 0),
            cost_usd=doc.get('cost_usd', source.get('cost_usd_upper_bound', 0)),
            edits=edits,
            questions=[{'kind': row['kind'], 'text': row['title']} for row in proposed.get('questions', [])],
            slow_tasks=[{'description': row['description']} for row in proposed.get('slow_tasks', [])],
            vocabulary=[
                {key: row.get(key, []) for key in ('kind', 'spelling', 'aliases')}
                for row in proposed.get('vocabulary', [])
            ],
            feedback=[
                {key: row[key] for key in ('component', 'failure_class', 'severity', 'count')}
                for row in proposed.get('feedback', [])
            ],
            privacy_rejected=sum(row.get('status') == 'privacy_rejected' for row in outcomes),
        )
    )


def list_runs(uid, limit):
    caps = Caps.from_env()
    state = dream_store.own_state(uid)
    today = state.get('day') == datetime.now(timezone.utc).date().isoformat()
    runs = [project_run(uid, run_id, doc) for run_id, doc in dream_store.own_runs(uid, limit=limit)]
    return DreamRunsResponse.model_validate(
        dict(
            mode=mode(),
            passes_today=int(state.get('passes', 0)) if today else 0,
            passes_limit=caps.passes,
            manual_runs_today=int(state.get('manual_runs', 0)) if today else 0,
            manual_runs_limit=caps.manual_runs,
            queued_changes=dream_store.dirty_count(uid),
            runs=[run for run in runs if run.status != 'idle'],
        )
    )


def finished_run(uid, run_id):
    doc = dream_store.own_run(uid, run_id)
    if not doc:
        raise RuntimeError('dream_report_missing')
    return project_run(uid, run_id, doc)
