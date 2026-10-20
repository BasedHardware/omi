"""Conservative offline fallback until the production pluggable checks exist.

Passing structural guards is NOT semantic agreement. Only byte-identical,
fully overlapping uncurated captures can agree locally; other survivors Review.
"""

from __future__ import annotations

from datetime import datetime
from importlib.util import find_spec
from typing import Any

from evals.dream_verifier.contracts import Snapshot
from evals.dream_verifier.metrics import Outcome
from models.agent_refs import base_ref, cited_value
from utils.agent_capabilities.guards import (
    spelling_rejection,
    summary_rejection,
    task_rejection,
    vocabulary_rejection,
    verbatim_quote,
)
from utils.conversations.fragment_visibility import is_user_curated
from database.action_item_refresh_policy import protected_donor

PRODUCTION_MODULE = 'utils.agent_capabilities.verifiers'


def local_check(snapshot: Snapshot) -> str:
    operation, records = snapshot.operation_data, snapshot.records
    rows = [records.get(base_ref(ref)) for ref in snapshot.refs]
    if not rows or any(row is None for row in rows):
        return 'disagree'
    target = records.get(base_ref(operation.get('target', '')), {})
    if snapshot.kind == 'spelling':
        if spelling_rejection(snapshot.operation) or not verbatim_quote(
            operation['before'], cited_value(operation['target'], records)
        ):
            return 'disagree'
    if snapshot.kind in {'title', 'overview'} and summary_rejection(snapshot.operation, target, full=True):
        return 'disagree'
    if snapshot.kind in {'close_task', 'retire_task'} and task_rejection(snapshot.operation, target, records):
        return 'disagree'
    if snapshot.kind == 'vocabulary' and vocabulary_rejection(snapshot.operation):
        return 'disagree'
    if snapshot.kind in {'close_task', 'retire_task', 'merge_tasks'}:
        tasks = [target]
        if operation.get('other'):
            tasks.append(records.get(base_ref(operation['other']), {}))
        if any(
            row.get('source') != 'conversation'
            or row.get('user_edited')
            or row.get('is_user_created')
            or row.get('completed')
            or protected_donor(row, [])
            for row in tasks
        ):
            return 'disagree'
    if snapshot.kind in {'title', 'overview'}:
        if (target.get('structured') or {}).get(snapshot.kind) or (
            snapshot.kind == 'title' and target.get('user_title')
        ):
            return 'disagree'
        if snapshot.kind == 'overview' and (target.get('structured') or {}).get('sections'):
            return 'disagree'
    if snapshot.kind == 'supersede_memory':
        newer = records.get(base_ref(operation.get('other', '')), {})
        if newer:
            if any(
                target.get(field) != newer.get(field)
                for field in ('slot', 'visibility', 'subject_scope', 'subject_entity_id')
            ):
                return 'disagree'
            if newer.get('content') == target.get('content'):
                return 'disagree'
            try:
                if datetime.fromisoformat(newer['created_at'].replace('Z', '+00:00')) <= datetime.fromisoformat(
                    target['created_at'].replace('Z', '+00:00')
                ):
                    return 'disagree'
            except (KeyError, ValueError, TypeError):
                return 'review'
    if snapshot.kind == 'vocabulary':
        text = ' '.join(str(records[base_ref(ref)]) for ref in snapshot.refs)
        if operation['spelling'] not in text:
            return 'disagree'
        if operation['kind'] == 'jargon' and operation['spelling'].casefold() in {'the', 'a', 'and'}:
            return 'disagree'
    if snapshot.kind == 'merge_conversations':
        other = records.get(base_ref(operation.get('other', '')), {})
        pair = (target, other)
        if any(
            row.get('status') != 'completed'
            or is_user_curated(row)
            or row.get('manual_speaker_assignments')
            or row.get('is_locked')
            or row.get('deleted')
            for row in pair
        ):
            return 'disagree'
        if any(
            segment.get('speaker_label_source') in {'manual', 'carried'}
            for row in pair
            for segment in row.get('transcript_segments', [])
        ):
            return 'disagree'
        try:
            spans = [
                (
                    datetime.fromisoformat(row['started_at'].replace('Z', '+00:00')),
                    datetime.fromisoformat(row['finished_at'].replace('Z', '+00:00')),
                )
                for row in pair
            ]
            (a, b), (c, d) = spans
            if min((b - a).total_seconds(), (d - c).total_seconds()) <= 0:
                return 'disagree'
            if (min(b, d) - max(a, c)).total_seconds() / min((b - a).total_seconds(), (d - c).total_seconds()) < 0.5:
                return 'disagree'
            left = ' '.join(segment['text'] for segment in target['transcript_segments'])
            right = ' '.join(segment['text'] for segment in other['transcript_segments'])
            if left == right and len(left.split()) >= 12 and spans[0] == spans[1]:
                return 'agree'
        except (KeyError, ValueError, TypeError):
            return 'review'
    return 'review'


def check(item: dict[str, Any]) -> Outcome:
    snapshot = Snapshot.from_item(item)
    if find_spec(PRODUCTION_MODULE) is not None:
        from evals.dream_verifier.production_checks import production_namespace
        from utils.agent_capabilities.registry import KINDS

        namespace = production_namespace()
        verdict = namespace['run_deterministic'](snapshot, namespace['VerifierStep']('deterministic'))
        if verdict.status not in {'agree', 'disagree', 'uncertain', 'unverified', 'split'}:
            raise ValueError('production_verifier_verdict_contract')
        spec = KINDS.get(snapshot.kind)
        sufficient = spec is not None and getattr(spec, 'deterministic_sufficient', False) is True
        decision = verdict.status if verdict.status in {'agree', 'disagree'} else 'review'
        if decision == 'agree' and not sufficient:
            decision = 'review'
        return Outcome(decision, source='production_pure_checks_current_authority')
    return Outcome(local_check(snapshot), source='local_conservative_fallback')
