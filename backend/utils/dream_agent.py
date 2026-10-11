"""Two-stage background shaped mount with a single guarded effect boundary."""

import asyncio
from functools import partial
from typing import Any
from collections import Counter

from pydantic import ValidationError

from config.dream_agent import Caps, mode, auto_apply_kinds, apply_policy
from database import dream_store, dream_feedback, review_changes, review_store
from database.dream_dirty import dream_writing
from models.dream_agent import Triage, Plan
from utils import dream_reads, dream_tools, dream_transport, dream_guards
from utils.dream_context import EvidenceRecords, target_refs
from utils.dream_grounding import spelling_grounding_rejection, spelling_question
from utils.executors import db_executor, postprocess_executor, run_blocking
from utils.llm.shaped_agent import run_loop
from utils.dream_metrics import record_pass

from utils.dream_prompt import mount, evidence_message, evidence_chars, person_names, TRIAGE_INSTRUCTIONS, triage_budget


async def plan_pass(uid, records, caps, *, turn=None, usage_sink=None, vocabulary=None):
    async def invoke(uid, lane, mount, messages):
        if usage_sink is not None:
            key = 'triage_evidence_chars' if lane == dream_transport.TRIAGE_LANE else 'reasoning_evidence_chars'
            usage_sink[key] = evidence_chars(messages)
            if lane == dream_transport.MAIN_LANE:
                usage_sink['reasoning_attempted'] = True
        previous_unknown = bool(usage_sink and usage_sink.get('usage_unknown'))
        if usage_sink is not None:
            usage_sink['usage_unknown'] = True
        try:
            result = (
                await turn(uid, lane, mount, messages)
                if turn is not None
                else await dream_transport.model_turn(
                    uid, lane, mount, messages, usage_sink=usage_sink, completion_limit=caps.completion_tokens
                )
            )
        except (dream_transport.PreTokenFailure, dream_transport.httpx.HTTPStatusError):
            if usage_sink is not None:
                usage_sink['usage_unknown'] = previous_unknown
            raise
        if usage_sink is not None and turn is not None:
            usage_sink['tokens'] += result.tokens
            usage_sink['usage_unknown'] = previous_unknown
        return result

    triage_tokens = triage_budget(caps)
    # The byte-based transport gate remains authoritative, including schema.
    triage = await run_loop(
        mount(
            Triage,
            triage_tokens,
            TRIAGE_INSTRUCTIONS,
        ),
        evidence_message(records, Triage, triage_tokens, vocabulary=vocabulary),
        partial(invoke, uid, dream_transport.TRIAGE_LANE),
    )
    if triage.reason != 'stopped':
        raise ValueError('dream_triage_budget')
    refs = list(dict.fromkeys(ref for c in triage.value.clusters for ref in c.refs))
    if any(ref not in records for ref in refs):
        raise ValueError('dream_unknown_cluster')
    if not refs:
        return Plan(), triage.tokens
    targets = [ref for ref in refs if ref in target_refs(records)][:8]
    if not targets:
        return Plan(), triage.tokens
    # Both stages see the same admitted context; triage-selected targets stay bounded.
    selected = EvidenceRecords(
        {ref: row for ref, row in records.items() if ref in targets or ref not in target_refs(records)}, targets=targets
    )
    main = await run_loop(
        mount(Plan, caps.tokens - triage.tokens),
        evidence_message(
            selected,
            Plan,
            caps.tokens - triage.tokens,
            names=person_names(records),
            clusters=triage.value.model_dump(),
            vocabulary=vocabulary,
        ),
        partial(invoke, uid, dream_transport.MAIN_LANE),
    )
    if main.reason != 'stopped':
        raise ValueError('dream_reasoning_budget')
    return (
        dream_guards.filter_plan(main.value, selected, targets=targets, usage_sink=usage_sink),
        triage.tokens + main.tokens,
    )


class IdlePass(Exception):
    """No visible evidence was selected; release the provisional admission."""


async def dry_run(uid, records, *, targets=None, caps=None, turn=None, vocabulary=None):
    """Plan caller-supplied decrypted evidence without reads, admission or effects.

    The owner supplies records obtained through authorized visibility-aware readers.
    Inference still uses the configured gateway; this function writes no product state.
    Supplying `turn` makes provider-free synthetic replays possible.
    """
    evidence = EvidenceRecords(records, targets=target_refs(records) if targets is None else targets)
    if not evidence.targets <= set(evidence):
        raise ValueError('dream_unknown_target')
    sink: dict[str, Any] = {'tokens': 0}
    plan, tokens = await plan_pass(
        uid, evidence, caps or Caps.from_env(), turn=turn, vocabulary=vocabulary, usage_sink=sink
    )
    plan = dream_guards.filter_plan(plan, evidence, targets=evidence.targets, usage_sink=sink)
    proposed = plan.model_dump(mode='python')
    for edit, row in zip(plan.edits, proposed['edits']):
        reason = spelling_grounding_rejection(edit, evidence, vocabulary or [])
        row['policy'] = 'suggest' if reason else apply_policy(edit.kind, auto_apply_kinds())
        if reason == 'ungrounded_spelling':
            sink.setdefault('rejected', {}).setdefault(reason, 0)
            sink['rejected'][reason] += 1
            if len(proposed['questions']) < 3:
                proposed['questions'].append(spelling_question(edit).model_dump(mode='python'))
    return {
        'plan': proposed,
        'guard_decisions': sink.get('rejected', {}),
        'role_counts': {'target': len(evidence.targets), 'context': len(evidence) - len(evidence.targets)},
        'tokens': tokens,
    }


async def run_pass(uid, *, caps=None, turn=None, trigger='schedule', canary=False, timeout_seconds=180, progress=None):
    caps = caps or Caps.from_env()
    lease = await run_blocking(db_executor, dream_store.acquire, uid, caps, trigger=trigger, canary=canary)
    if lease is None:
        report = {'status': 'not_admitted'}
        record_pass(report)
        return report
    report: dict[str, Any] = {
        'status': 'failed',
        'tokens': 0,
        'cost_usd_reserved': caps.reservation_usd,
        'mode': lease['mode'],
        'usage_complete': False,
        'usage_unknown': False,
        'run_id': lease['run_id'],
        'trigger': trigger,
        'records_read': 0,
        'triage_evidence_chars': 0,
        'reasoning_evidence_chars': 0,
        'cost_usd': 0.0,
    }
    consumed = []
    reviewed = set()
    cleanup_cursor = None
    refund = False
    success = False
    release = True
    try:
        async with asyncio.timeout(timeout_seconds):
            vocabulary = await run_blocking(db_executor, dream_store.vocabulary, uid)
            records, consumed = await run_blocking(db_executor, dream_reads.read_changes, uid, lease, caps, vocabulary)
            reviewed = target_refs(records)
            cleanup_cursor = getattr(records, 'cleanup_cursor', None)
            report['target_source_counts'] = dict(
                Counter(getattr(records, 'target_sources', {ref: 'dirty' for ref in reviewed}).values())
            )
            report['dirty_read'] = len(consumed)
            report['records_read'] = len(records)
            report['role_counts'] = {
                'target': len(target_refs(records)),
                'context': len(records) - len(target_refs(records)),
            }
            if not records:
                raise IdlePass()
            if progress is not None:
                progress['stage'] = 'model'
            # Gate against all private input, including names not yet in the vocabulary doc.
            names = list(vocabulary)
            for row in records.values():
                for key in ('name', 'label', 'organization', 'title'):
                    if isinstance(row.get(key), str):
                        names.append({'spelling': row[key]})
            plan, tokens = await plan_pass(uid, records, caps, turn=turn, usage_sink=report, vocabulary=vocabulary)
            plan = dream_guards.filter_plan(plan, records, targets=target_refs(records), usage_sink=report)
            report.update(
                status='planned',
                tokens=tokens,
                cost_usd_upper_bound=tokens * caps.max_usd_per_token,
                # A privacy timeout/fault must not leave unchecked feedback in the failed report.
                proposed={**plan.model_dump(mode='python'), 'feedback': []},
                outcomes=[],
            )
            # Reject feedback before even saving it in a per-user shadow report.
            accepted = []
            for feedback in plan.feedback:
                try:
                    await run_blocking(
                        postprocess_executor,
                        dream_feedback.validate,
                        feedback,
                        records,
                        [*names, *[t.model_dump() for t in plan.vocabulary]],
                        uid=uid,
                    )
                    accepted.append(feedback)
                except ValueError:
                    counts = Counter(report.get('rejected', {}))
                    counts['privacy_rejected'] += 1
                    report['rejected'] = dict(counts)
                    report['outcomes'].append({'tool': 'feedback', 'status': 'privacy_rejected'})
            accepted = dream_guards.cap_feedback(accepted, usage_sink=report)
            report['proposed']['feedback'] = [f.model_dump() for f in accepted]
            demoted = await run_blocking(db_executor, dream_store.demoted_types, uid, caps)
            automatic = auto_apply_kinds() - demoted
            grounding = {
                dream_tools.edit_key(edit, records): spelling_grounding_rejection(edit, records, vocabulary)
                for edit in plan.edits
            }
            ungrounded = sum(reason == 'ungrounded_spelling' for reason in grounding.values())
            if ungrounded:
                counts = Counter(report.get('rejected', {}))
                counts['ungrounded_spelling'] += ungrounded
                report['rejected'] = dict(counts)
            edit_policies = {
                dream_tools.edit_key(edit, records): (
                    'suggest'
                    if dream_tools.edit_key(edit, records).split(':')[1] in demoted
                    or grounding[dream_tools.edit_key(edit, records)]
                    else apply_policy(edit.kind, automatic)
                )
                for edit in plan.edits
            }
            for edit, proposed_edit in zip(plan.edits, report['proposed']['edits']):
                proposed_edit['policy'] = edit_policies[dream_tools.edit_key(edit, records)]
            for term in report['proposed']['vocabulary']:
                term['policy'] = apply_policy('vocabulary', automatic)
            outcomes: list[dict[str, Any]] = report['outcomes']
            token = dream_writing.set(True)
            try:

                async def effect(fn, *args):
                    await run_blocking(db_executor, dream_store.assert_lease, uid, lease['run_id'])
                    # Recheck kill switch before every effect. A shadow lease cannot upgrade.
                    if lease['mode'] != 'on' or mode() != 'on':
                        return 'shadow'
                    return await run_blocking(db_executor, fn, uid, *args)

                remaining = caps.edits
                for edit in plan.edits:
                    key = dream_tools.edit_key(edit, records)
                    if edit.target not in records or any(ref not in records for ref in edit.evidence):
                        outcomes.append({'key': key, 'status': 'invalid_evidence'})
                        continue
                    try:
                        dream_tools.validate_edit(edit, records)
                    except (ValueError, review_store.ReviewConflict):
                        outcomes.append({'key': key, 'status': 'invalid_evidence'})
                        continue
                    allowed = await run_blocking(db_executor, review_changes.agent_change_allowed, uid, key)
                    if not allowed:
                        status = 'suppressed'
                    elif remaining <= 0:
                        status = 'edit_cap'
                    else:
                        remaining -= 1
                        is_question = grounding[key] == 'ungrounded_spelling'
                        tool = (
                            (dream_tools.apply_grounded_edit if edit.kind == 'spelling' else dream_tools.apply_edit)
                            if edit_policies[key] == 'auto'
                            else dream_tools.suggest_spelling if is_question else dream_tools.suggest_edit
                        )
                        try:
                            if is_question:
                                report['proposed']['questions'].append(
                                    spelling_question(edit).model_dump(mode='python')
                                )
                            admitted = True
                            if is_question and lease['mode'] == 'on' and mode() == 'on':
                                admitted = bool(
                                    await run_blocking(
                                        db_executor, dream_store.reserve_questions, uid, lease['run_id'], 1
                                    )
                                )
                            status = await effect(tool, edit, records) if admitted else 'suggestion_cap'
                        except (ValueError, review_store.ReviewConflict, review_store.ReviewNotFound):
                            status = 'invalid_evidence'
                    outcomes.append({'key': key, 'status': status, 'policy': edit_policies[key]})
                attention = await run_blocking(db_executor, review_store.remaining_today, uid)
                if lease['mode'] == 'on' and mode() == 'on' and plan.questions:
                    attention = await run_blocking(
                        db_executor,
                        dream_store.reserve_questions,
                        uid,
                        lease['run_id'],
                        min(len(plan.questions), attention),
                    )
                for item in plan.questions[:attention]:
                    outcomes.append({'tool': 'ask', 'status': await effect(dream_tools.ask, item, records)})
                # Slow tasks share the per-pass write budget; cannot bypass edit caps.
                for task in plan.slow_tasks[:remaining]:
                    remaining -= 1
                    outcomes.append(
                        {'tool': 'slow_task', 'status': await effect(dream_tools.propose_task, task, records)}
                    )
                terms = [t for t in plan.vocabulary if all(ref in records for ref in t.evidence)]
                for term in terms[:remaining]:
                    remaining -= 1
                    policy = apply_policy('vocabulary', automatic)
                    tool = dream_tools.apply_vocabulary if policy == 'auto' else dream_tools.suggest_vocabulary
                    try:
                        status = await effect(tool, [term]) if policy == 'auto' else await effect(tool, term, records)
                    except (ValueError, review_store.ReviewConflict, review_store.ReviewNotFound):
                        status = 'invalid_evidence'
                    outcomes.append({'tool': 'vocabulary', 'policy': policy, 'status': status})
                for frame in plan.frames:
                    outcomes.append(
                        {'tool': 'frame', 'status': await effect(dream_tools.request_frame, frame, records)}
                    )
                for feedback in accepted:
                    outcomes.append(
                        {'tool': 'feedback', 'status': await effect(dream_feedback.store, feedback, records, names)}
                    )
            finally:
                dream_writing.reset(token)
            report['usage_complete'] = True
            report['status'] = 'complete'
            success = True
    except IdlePass:
        report.update(status='not_admitted', reason='idle', usage_complete=True, cost_usd_reserved=0)
        success = True
        refund = True
    except Exception as exc:
        report.update(status='failed', error_type=type(exc).__name__)
        if isinstance(exc, ValidationError):
            counts = Counter(report.get('validation_errors', {}))
            counts.update(dream_transport.validation_counts(exc))
            report['validation_errors'] = dict(counts)
        release = not isinstance(exc, TimeoutError)
        refund = report['tokens'] == 0 and not report['usage_unknown']
        if refund:
            report['cost_usd_reserved'] = 0
        # No raw exception strings: provider bodies or user text may be embedded.
    report['cost_usd'] = report['tokens'] * caps.max_usd_per_token
    if progress is not None:
        progress['stage'] = 'report'
    await run_blocking(
        db_executor,
        dream_store.finish,
        uid,
        lease,
        report,
        success=success,
        consumed=consumed,
        release=release,
        refund=refund,
        reviewed=reviewed,
        cleanup_cursor=cleanup_cursor,
        count_failure=not success and release and report['tokens'] > 0 and report.get('reasoning_attempted', False),
    )
    record_pass(report)
    return report


DRAIN_TIMEOUT_SECONDS = 120


async def drain(*, limit=100):
    if mode() == 'off':
        return []
    results = []
    try:
        async with asyncio.timeout(DRAIN_TIMEOUT_SECONDS):
            for uid in await run_blocking(db_executor, dream_store.candidates, limit=max(0, min(limit, 100))):
                if mode() == 'off':
                    break
                results.append(await run_pass(uid))
    except TimeoutError:
        # Cancellation leaves any in-flight lease/reservation intact. Offloaded
        # storage may still settle; never admit another pass for that user.
        results.append({'status': 'deadline'})
    return results
