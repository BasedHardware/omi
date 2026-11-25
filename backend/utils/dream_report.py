"""Project encrypted owner reports onto the mobile contract using owner-visible labels."""

from datetime import datetime, timezone

from fastapi import HTTPException

from config.dream_agent import Caps, eligible, mode, self_report_enabled
from database import dream_store, review_store
from database._client import get_firestore_client
from models.dream_report import DreamRun, DreamRunsResponse
from models.agent_refs import base_ref
from utils.agent_capabilities import reads as dream_reads
from utils.other.list_budget import ListReadBudgetExhausted, budgeted_document_get


def require_owner(uid, *, budget=None):
    if not self_report_enabled() or mode() == 'off':
        raise HTTPException(404, detail='dream_report_disabled')
    user_ref = get_firestore_client().collection('users').document(uid)
    user = budgeted_document_get(user_ref, budget).to_dict() or {}
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


def project_run(uid, run_id, doc, *, budget=None):
    source = (review_store.decode_doc(uid, doc) or {}).get('source', {})
    proposed = source.get('proposed') or {}
    outcomes = source.get('outcomes') or []
    records = {}
    budget_kwargs = {'budget': budget} if budget is not None else {}
    for edit in proposed.get('edits', []):
        ref = base_ref(edit['target'])
        if ref in records:
            continue
        try:
            # Identity enrichment uses entity/<typed-id>, rather than dirty collection refs.
            records[ref] = (
                dream_reads.resolve_entity(uid, ref.removeprefix('entity/'), **budget_kwargs)
                if ref.startswith('entity/')
                else dream_reads.read_record(uid, ref, **budget_kwargs)
            )
        except (review_store.ReviewNotFound, ValueError):
            records[ref] = None
        except HTTPException as exc:
            if exc.status_code not in {402, 404}:
                raise
            records[ref] = None
    edit_outcomes = [row for row in outcomes if 'key' in row]
    by_key = {row['key']: row['status'] for row in edit_outcomes}
    edits = []
    for index, edit in enumerate(proposed.get('edits', [])):
        outcome = (
            by_key.get(edit['key'], 'invalid_evidence')
            if 'key' in edit
            else edit_outcomes[index]['status'] if index < len(edit_outcomes) else 'invalid_evidence'
        )
        outcome = {'suggested': 'suggest_only', 'already_suggested': 'suggest_only', 'suggestion_cap': 'edit_cap'}.get(
            outcome, outcome
        )
        if outcome not in {
            'shadow',
            'applied',
            'suppressed',
            'suggest_only',
            'edit_cap',
            'invalid_evidence',
        }:
            outcome = 'invalid_evidence'
        edits.append(
            {
                'kind': edit['kind'],
                'policy': edit.get(
                    'policy', 'auto' if edit['kind'] in {'title', 'overview', 'spelling'} else 'suggest'
                ),
                'target_label': target_label(edit['target'], records.get(base_ref(edit['target']))),
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
                {
                    **{key: row.get(key, []) for key in ('kind', 'spelling', 'aliases')},
                    'policy': row.get('policy', 'auto'),
                }
                for row in proposed.get('vocabulary', [])
            ],
            feedback=[
                {key: row[key] for key in ('component', 'failure_class', 'severity', 'count')}
                for row in proposed.get('feedback', [])
            ],
            privacy_rejected=sum(row.get('status') == 'privacy_rejected' for row in outcomes),
        )
    )


def _bounded(budget, read, fallback, partial_attr='partial_snapshots'):
    """Run one report stage under the request's read budget.

    A spent budget is this route's explicit truncation, never an error: the
    caller keeps whatever the stage already produced, including the honest
    prefix a stream cut mid-page attaches to its exhaustion.
    """
    try:
        return read()
    except ListReadBudgetExhausted as exc:
        if budget is None:
            raise
        return getattr(exc, partial_attr, fallback)


def list_runs(uid, limit, *, budget=None):
    """The owner's run history inside one request-scoped read budget.

    Reads, at most, the owner state document, one ``limit``-row run stream, and
    one dirty-count aggregation, plus one deduped target read per edited record
    across those runs (the session's edit ceiling is 25 per run). Without
    ``budget`` every read is the released unbounded call. With one, each read
    carries the budget's per-RPC timeout and no retry; a spent budget returns
    the runs projected so far and flags the response through
    ``X-Omi-List-Truncated`` instead of holding the request to the middleware
    cutoff.
    """
    caps = Caps.from_env()
    state = _bounded(budget, lambda: dream_store.own_state(uid, budget=budget), {}) or {}
    today = state.get('day') == datetime.now(timezone.utc).date().isoformat()
    rows = _bounded(
        budget, lambda: dream_store.own_runs(uid, limit=limit, budget=budget), [], partial_attr='partial_runs'
    )
    runs = []
    for run_id, doc in rows:
        try:
            runs.append(project_run(uid, run_id, doc, budget=budget))
        except ListReadBudgetExhausted:
            # Only fully projected runs ship: a target label left unresolved
            # mid-run would read as a deleted record. The response header marks
            # the list incomplete.
            break
    queued_changes = _bounded(budget, lambda: dream_store.dirty_count(uid, budget=budget), 0)
    return DreamRunsResponse.model_validate(
        dict(
            mode=mode(),
            passes_today=int(state.get('passes', 0)) if today else 0,
            passes_limit=caps.passes,
            manual_runs_today=int(state.get('manual_runs', 0)) if today else 0,
            manual_runs_limit=caps.manual_runs,
            queued_changes=queued_changes,
            runs=[run for run in runs if run.status != 'idle'],
        )
    )


def finished_run(uid, run_id):
    doc = dream_store.own_run(uid, run_id)
    if not doc:
        raise RuntimeError('dream_report_missing')
    return project_run(uid, run_id, doc)
