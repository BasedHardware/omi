"""Two-stage background shaped mount with a single guarded effect boundary."""

import asyncio
from functools import partial
from dataclasses import replace
from typing import Any
from collections import Counter

from pydantic import ValidationError

from config.dream_agent import (
    Caps,
    mode,
    concurrency,
    auto_apply_kinds,
    apply_policy,
    context_mode,
    full_context_enabled,
    FULL_PASS_SECONDS,
    FULL_DRAIN_SECONDS,
    FULL_MODEL_SECONDS,
    PASS_TIMEOUT_SECONDS,
    FINISH_MARGIN_SECONDS,
    DRAIN_TIMEOUT_SECONDS,
)
from database import dream_scheduler, dream_store, dream_feedback, review_changes, review_store
from database.dream_dirty import dream_writing
from models.dream_agent import Triage, Plan, FullPlan, DreamReviewItem
from models.dream_refs import base_ref, has_ref, cited_value
from utils import dream_capacity, dream_reads, dream_tools, dream_transport, dream_guards
from utils.dream_consensus import majority, unanimous_spelling, plan_dump, item_dump
from utils.dream_context import EvidenceRecords, target_refs, cluster_hints, REASONING_TARGET_LIMIT
from utils.dream_grounding import spelling_grounding_rejection, spelling_question, rank_questions
from utils.dream_decisions import edit_decisions, offer_questions
from utils.executors import db_executor, postprocess_executor, run_blocking
from utils.llm.shaped_agent import run_loop
from utils.dream_metrics import record_pass, error_code, record_reclaimed
from utils.dream_diagnostics import initialize, counts_only

from utils.dream_prompt import mount, evidence_message, evidence_chars, person_names, TRIAGE_INSTRUCTIONS, triage_budget
from utils.dream_prompt import full_mount, full_evidence_message, select_full_records


async def plan_pass(uid, records, caps, *, turn=None, usage_sink=None, vocabulary=None, deadline=None, clock=None):
    caps = caps.for_uid(uid)
    clock = asyncio.get_running_loop().time if clock is None else clock
    deadline = deadline if deadline is not None else clock() + FULL_PASS_SECONDS

    async def invoke(uid, lane, mount, messages):
        if usage_sink is not None:
            key = 'triage_evidence_chars' if lane == dream_transport.TRIAGE_LANE else 'reasoning_evidence_chars'
            usage_sink[key] = evidence_chars(messages)
            if caps.context_mode != 'full':
                usage_sink['context_mode'] = 'bounded'
                usage_sink['input_tokens_estimate'] = usage_sink.get(
                    'input_tokens_estimate', 0
                ) + dream_transport.input_estimate(messages, mount.schema.model_json_schema())
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

    if caps.context_mode == 'full':
        selected = EvidenceRecords(select_full_records(records, caps, vocabulary), targets=target_refs(records))
        selected.targets &= set(selected)
        selected.context_mode = 'full'
        active_mount = full_mount(caps)
        messages = full_evidence_message(selected, caps, vocabulary)
        if usage_sink is not None:
            usage_sink.update(
                context_mode='full',
                samples_requested=caps.samples,
                targets=len(selected.targets),
                records=len(selected),
                input_tokens_estimate=dream_transport.input_estimate(
                    active_mount.messages(messages), active_mount.schema.model_json_schema()
                ),
            )
            usage_sink['admitted_records'] = selected
        sample_usage: list[dict[str, Any]] = [
            {'tokens': 0, 'usage_unknown': False, 'returned': False} for _ in range(caps.samples)
        ]

        async def sample(sink):
            async def sample_turn(active, framed):
                sink['reasoning_attempted'] = True
                previous_unknown = sink['usage_unknown']
                sink['usage_unknown'] = True
                try:
                    if turn is not None:
                        result = await turn(uid, dream_transport.MAIN_LANE, active, framed)
                        sink['tokens'] += result.tokens
                        sink['usage_unknown'] = previous_unknown
                        return result
                    return await dream_transport.model_turn(
                        uid,
                        dream_transport.MAIN_LANE,
                        active,
                        framed,
                        usage_sink=sink,
                        completion_limit=caps.completion_tokens,
                    )
                except (dream_transport.PreTokenFailure, dream_transport.httpx.HTTPStatusError):
                    sink['usage_unknown'] = previous_unknown
                    raise

            # A capacity retry can follow a billed malformed response. Carry its
            # usage into the retry's remaining token budget; do not purchase a third
            # full sample budget under the same worst-case reservation.
            remaining_mount = replace(
                active_mount, budget=replace(active_mount.budget, tokens=active_mount.budget.tokens - sink['tokens'])
            )
            result = await run_loop(remaining_mount, messages, sample_turn)
            if result.reason != 'stopped':
                raise ValueError('dream_reasoning_budget')
            if not isinstance(result.value, (Plan, FullPlan)):
                raise ValueError('dream_sample_plan')
            sink['returned'] = True
            return result.value

        results = []
        try:
            for sink in sample_usage:
                if deadline - clock() < FULL_MODEL_SECONDS:
                    break
                sink['attempted'] = True
                for attempt in range(2):
                    try:
                        results.append(await sample(sink))
                        break
                    except dream_transport.CapacityWait as exc:
                        sink['capacity_wait'] = True
                        if attempt == 0 and await dream_capacity.wait_for_capacity(
                            deadline, FULL_MODEL_SECONDS, clock=clock
                        ):
                            sink['capacity_retries'] = 1
                            continue
                        results.append(exc)
                        break
                    except Exception as exc:
                        results.append(exc)
                        break
        finally:
            if usage_sink is not None:
                usage_sink['samples_requested'] = caps.samples
                usage_sink['samples_returned'] = sum(sink['returned'] for sink in sample_usage)
                usage_sink['samples_failed'] = caps.samples - usage_sink['samples_returned']
                usage_sink['samples_attempted'] = sum(bool(sink.get('attempted')) for sink in sample_usage)
                usage_sink['samples_capacity_wait'] = sum(bool(sink.get('capacity_wait')) for sink in sample_usage)
                usage_sink['capacity_retries'] = sum(sink.get('capacity_retries', 0) for sink in sample_usage)
                usage_sink['reasoning_attempted'] = any(sink.get('reasoning_attempted') for sink in sample_usage)
                usage_sink['reasoning_evidence_chars'] = sum(
                    bool(sink.get('reasoning_attempted')) for sink in sample_usage
                ) * evidence_chars(messages)
                usage_sink['tokens'] += sum(sink['tokens'] for sink in sample_usage)
                usage_sink['usage_unknown'] = any(sink['usage_unknown'] for sink in sample_usage)
                usage_sink['response_retries'] = sum(sink.get('response_retries', 0) for sink in sample_usage)
                usage_sink['model_lanes'] = [lane for sink in sample_usage for lane in sink.get('model_lanes', [])]
                for field in ('rejected', 'validation_errors', 'dropped_invalid'):
                    counts = Counter(usage_sink.get(field, {}))
                    for sink in sample_usage:
                        counts.update(sink.get(field, {}))
                    usage_sink[field] = dict(counts)
        plans = [result for result in results if isinstance(result, (Plan, FullPlan))]
        if usage_sink is not None:
            usage_sink['samples_returned'] = len(plans)
            usage_sink['samples_failed'] = caps.samples - len(plans)
        if not plans:
            if any(isinstance(result, dream_transport.CapacityWait) for result in results) or not results:
                raise dream_transport.CapacityWait('dream_capacity_wait')
            raise next(result for result in results if isinstance(result, Exception))
        plan = majority(plans, usage_sink=usage_sink)
        if usage_sink is not None:
            usage_sink['raw_plan'] = plan_dump(plan, full=True)
        return dream_guards.filter_plan(plan, selected, usage_sink=usage_sink), sum(
            sink['tokens'] for sink in sample_usage
        )

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
    refs = list(dict.fromkeys(base_ref(ref) for c in triage.value.clusters for ref in c.refs))
    if any(ref not in records for ref in refs):
        raise ValueError('dream_unknown_cluster')
    if not refs:
        return Plan(), triage.tokens
    targets = [ref for ref in refs if ref in target_refs(records)][:REASONING_TARGET_LIMIT]
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
            clusters=cluster_hints(triage.value, selected),
            vocabulary=vocabulary,
        ),
        partial(invoke, uid, dream_transport.MAIN_LANE),
    )
    if main.reason != 'stopped':
        raise ValueError('dream_reasoning_budget')
    if usage_sink is not None:
        usage_sink['raw_plan'] = main.value.model_dump(mode='python')
    return (
        dream_guards.filter_plan(main.value, selected, targets=targets, usage_sink=usage_sink),
        triage.tokens + main.tokens,
    )


class IdlePass(Exception):
    """No visible evidence was selected; release the provisional admission."""


async def dry_run_retrieval(uid, records, *, targets=None, caps=None, vocabulary=None):
    """Retrieve authorized caller-supplied targets; return counts without planning/effects.

    Calls the same visibility-aware links/search/temporal readers as a pass.
    No lease, admission, inference, acknowledgement, product writes or report writes.
    Embedding search may call the existing provider. The caller owns authorization.
    """
    caps = (caps or Caps.from_env()).for_uid(uid)
    evidence = EvidenceRecords(records, targets=target_refs(records) if targets is None else targets)
    if not evidence.targets <= set(evidence):
        raise ValueError('dream_unknown_target')
    diagnostics = initialize({})
    if vocabulary is None:
        vocabulary = await run_blocking(db_executor, dream_store.vocabulary, uid)
    evidence = await run_blocking(
        postprocess_executor,
        dream_reads.retrieve_context,
        uid,
        evidence,
        caps,
        vocabulary,
        diagnostics=diagnostics,
    )
    return {
        **counts_only(diagnostics),
        'role_counts': {'target': len(evidence.targets), 'context': len(evidence) - len(evidence.targets)},
        'triage_fits': dream_reads.fits_triage(evidence, caps, vocabulary),
    }


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
    caps = (caps or Caps.from_env()).for_uid(uid)
    plan, tokens = await plan_pass(uid, evidence, caps, turn=turn, vocabulary=vocabulary, usage_sink=sink)
    evidence = sink.pop('admitted_records', evidence)
    plan = dream_guards.filter_plan(plan, evidence, targets=evidence.targets, usage_sink=sink)
    if caps.context_mode == 'full':
        accepted = []
        for feedback in plan.feedback:
            try:
                await run_blocking(
                    postprocess_executor, dream_feedback.validate, feedback, evidence, vocabulary or [], uid=uid
                )
                accepted.append(feedback)
            except ValueError:
                counts = Counter(sink.get('rejected', {}))
                counts['privacy_rejected'] += 1
                sink['rejected'] = dict(counts)
        plan = plan.model_copy(update={'feedback': dream_guards.cap_feedback(accepted, usage_sink=sink)})
    full = caps.context_mode == 'full'
    proposed = plan_dump(plan, full=full)
    questions: list[DreamReviewItem] = list(plan.questions)
    for edit, row in zip(plan.edits, proposed['edits']):
        reason = spelling_grounding_rejection(edit, evidence, vocabulary or [])
        if full and unanimous_spelling(edit) and reason == 'ungrounded_spelling':
            reason = None
        row['policy'] = 'suggest' if reason else apply_policy(edit.kind, auto_apply_kinds(uid))
        if reason == 'ungrounded_spelling':
            sink.setdefault('rejected', {}).setdefault(reason, 0)
            sink['rejected'][reason] += 1
            if not dream_guards.verbatim_quote(edit.before, cited_value(edit.target, evidence)):
                sink['rejected']['invalid_question_evidence'] = sink['rejected'].get('invalid_question_evidence', 0) + 1
            elif full:
                questions.append(spelling_question(edit, full=True))
            elif len(proposed['questions']) < 3:
                proposed['questions'].append(spelling_question(edit).model_dump(mode='python'))
    if full:
        proposed['questions'] = [item_dump(item) for item in rank_questions(questions, usage_sink=sink)[:3]]
    result = {
        'plan': proposed,
        'guard_decisions': sink.get('rejected', {}),
        'role_counts': {'target': len(evidence.targets), 'context': len(evidence) - len(evidence.targets)},
        'tokens': tokens,
    }
    result['raw_plan'] = sink.get('raw_plan', Plan().model_dump(mode='python'))
    if caps.context_mode == 'full':
        result.update(
            context_mode='full',
            input_tokens_estimate=sink.get('input_tokens_estimate', 0),
            response_retries=sink.get('response_retries', 0),
            samples_requested=sink.get('samples_requested', 0),
            samples_returned=sink.get('samples_returned', 0),
            samples_failed=sink.get('samples_failed', 0),
            consensus_threshold=sink.get('consensus_threshold', 0),
        )
    return result


async def run_pass(
    uid, *, caps=None, turn=None, trigger='schedule', canary=False, timeout_seconds=None, progress=None
) -> dict[str, Any]:
    caps = (caps or Caps.from_env()).for_uid(uid)
    maximum = FULL_PASS_SECONDS if caps.context_mode == 'full' else 180
    timeout_seconds = maximum if timeout_seconds is None else min(timeout_seconds, maximum)
    # Injected synthetic turns need no provider admission. Real/manual/canary calls do.
    slot = (
        await dream_capacity.claim(concurrency(), slot_seconds=FULL_DRAIN_SECONDS)
        if turn is None and caps.context_mode == 'full'
        else await dream_capacity.claim(concurrency()) if turn is None else None
    )
    if turn is None and slot is None:
        report = {
            'status': 'waiting',
            'reason': 'reserved_capacity',
            'context_mode': caps.context_mode,
            'samples_requested': caps.samples if caps.context_mode == 'full' else 0,
        }
        if caps.context_mode == 'bounded':
            report.pop('context_mode')
            report.pop('samples_requested')
        record_pass(report)
        return report
    progress = {} if progress is None else progress
    try:
        report = await _run_admitted_pass(
            uid,
            caps=caps,
            turn=turn,
            trigger=trigger,
            canary=canary,
            timeout_seconds=timeout_seconds,
            progress=progress,
        )
    except dream_store.AdmissionDenied:
        # The transaction deterministically declined without creating an owner lease.
        if slot is not None:
            await dream_capacity.release(slot)
        raise
    except Exception as exc:
        if slot is not None:
            await dream_capacity.release(slot)
        # A completed model pass must keep its counts if settlement fails.
        if 'report' not in progress:
            raise
        report = progress['report']
        report.pop('admitted_records', None)
        report.pop('raw_plan', None)
        report.update(status='failed', error_type=type(exc).__name__, error_code=error_code(exc))
        record_pass(report)
        return report
    except BaseException:
        # Cancellation may leave synchronous IO running; retain the TTL fence.
        raise
    if slot is not None and report.get('error_type') != 'TimeoutError':
        await dream_capacity.release(slot)
    return report


async def _run_admitted_pass(
    uid, *, caps=None, turn=None, trigger='schedule', canary=False, timeout_seconds=180, progress=None
):
    caps = caps or Caps.from_env()
    reclaimed: dict[str, Any] = {}
    try:
        lease = await run_blocking(
            db_executor, dream_store.acquire, uid, caps, trigger=trigger, canary=canary, reclaim_sink=reclaimed
        )
    finally:
        # Admission can be denied after a reclamation commits. Count that outcome too.
        if reclaimed:
            record_reclaimed(**reclaimed)
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
        'context_mode': caps.context_mode,
        'samples_requested': caps.samples if caps.context_mode == 'full' else 0,
        'input_tokens_estimate': 0,
        'targets': 0,
        'records': 0,
    }
    initialize(report)
    if progress is not None:
        progress['report'] = report
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    consumed = []
    reviewed = set()
    seeded = set()
    cleanup_cursor = None
    deferred = set()
    unavailable = []
    refund = False
    success = False
    release = True
    try:
        async with asyncio.timeout(timeout_seconds):
            vocabulary = await run_blocking(db_executor, dream_store.vocabulary, uid)
            # Retrieval coordinates storage and embedding providers; leave CRUD workers free.
            records, consumed = await run_blocking(
                postprocess_executor,
                dream_reads.read_changes,
                uid,
                lease,
                caps,
                vocabulary,
                diagnostics=report,
                unavailable=unavailable,
            )
            reviewed = target_refs(records)
            sources = getattr(records, 'target_sources', {ref: 'dirty' for ref in reviewed})
            seeded = {ref for ref in reviewed if sources.get(ref) in {'seeded', 'random'}}
            cleanup_cursor = getattr(records, 'cleanup_cursor', None)
            report['target_source_counts'] = dict(Counter(sources.values()))
            report['seed_errors'] = getattr(records, 'seed_errors', 0)
            report['dirty_read'] = len(consumed)
            report['records_read'] = len(records)
            report.update(targets=len(target_refs(records)), records=len(records))
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
            plan, tokens = await plan_pass(
                uid, records, caps, turn=turn, usage_sink=report, vocabulary=vocabulary, deadline=deadline
            )
            records = report.pop('admitted_records', records)
            inspected = {item['collection'] + '/' + item['id'] for item in [*consumed, *unavailable]}
            seeded.update(set(records) - inspected)  # Retrieval-only refs have no inspected dirty version.
            report.pop('raw_plan', None)  # Raw private feedback is only returned to the dry-run caller.
            plan = dream_guards.filter_plan(plan, records, targets=target_refs(records), usage_sink=report)
            full = caps.context_mode == 'full'
            if full:
                report.update(
                    auto_applied_unanimous=0,
                    suggested_majority=0,
                    questions_offered=0,
                    questions_dropped_low_value=report.get('questions_dropped_low_value', 0),
                )
            report.update(
                status='planned',
                tokens=tokens,
                cost_usd_upper_bound=tokens * caps.max_usd_per_token,
                # A privacy timeout/fault must not leave unchecked feedback in the failed report.
                proposed={**plan_dump(plan, full=full), 'feedback': []},
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
            automatic = auto_apply_kinds(uid) - demoted
            grounding, edit_policies = edit_decisions(plan, records, vocabulary, automatic, demoted, full, report)
            for edit, proposed_edit in zip(plan.edits, report['proposed']['edits']):
                proposed_edit['policy'] = edit_policies[dream_tools.edit_key(edit, records)]
            for term in report['proposed']['vocabulary']:
                term['policy'] = apply_policy('vocabulary', automatic)
            outcomes: list[dict[str, Any]] = report['outcomes']
            queued_questions = list(plan.questions)
            question_edits = {}
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
                    if grounding[key] == 'ungrounded_spelling' and not dream_guards.verbatim_quote(
                        edit.before, cited_value(edit.target, records)
                    ):
                        report.setdefault('rejected', {}).setdefault('invalid_question_evidence', 0)
                        report['rejected']['invalid_question_evidence'] += 1
                        outcomes.append({'key': key, 'status': 'invalid_question_evidence'})
                        continue
                    if not has_ref(edit.target, records) or any(not has_ref(ref, records) for ref in edit.evidence):
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
                        if full and grounding[key] == 'ungrounded_spelling':
                            item = spelling_question(edit, full=True)
                            queued_questions.append(item)
                            question_edits[item.item_id] = edit
                            outcomes.append({'key': key, 'status': 'suggest_only', 'policy': 'suggest'})
                            continue
                        remaining -= 1
                        is_question = grounding[key] == 'ungrounded_spelling'
                        tool = (
                            (dream_tools.apply_grounded_edit if edit.kind == 'spelling' else dream_tools.apply_edit)
                            if edit_policies[key] == 'auto'
                            else dream_tools.suggest_spelling if is_question else dream_tools.suggest_edit
                        )
                        if full and edit_policies[key] == 'auto' and unanimous_spelling(edit):
                            tool = dream_tools.apply_unanimous_edit
                        try:
                            if is_question:
                                report['proposed']['questions'].append(
                                    spelling_question(edit).model_dump(mode='python')
                                )
                            status = (
                                await effect(tool, edit, records, lease['run_id'])
                                if is_question
                                else await effect(tool, edit, records)
                            )
                            if is_question and status in {'suggestion_cap', 'already_suggested', 'suppressed'}:
                                remaining += 1
                            if is_question and status == 'suggestion_cap':
                                deferred.add(base_ref(edit.target))
                            if full and status == 'applied' and unanimous_spelling(edit):
                                report['auto_applied_unanimous'] += 1
                        except (ValueError, review_store.ReviewConflict, review_store.ReviewNotFound):
                            status = 'invalid_evidence'
                    outcomes.append({'key': key, 'status': status, 'policy': edit_policies[key]})
                if full:
                    remaining = await offer_questions(
                        uid,
                        lease['run_id'],
                        records,
                        queued_questions,
                        question_edits,
                        remaining,
                        deferred,
                        report,
                        effect,
                    )
                else:
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
                terms = [t for t in plan.vocabulary if all(has_ref(ref, records) for ref in t.evidence)]
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
            report['usage_complete'] = not report['usage_unknown']
            report['status'] = 'complete'
            success = True
    except IdlePass:
        report.update(status='not_admitted', reason='idle', usage_complete=True, cost_usd_reserved=0)
        success = True
        refund = True
    except Exception as exc:
        report.pop('admitted_records', None)
        report.pop('raw_plan', None)
        report.update(status='failed', error_type=type(exc).__name__, error_code=error_code(exc))
        if isinstance(exc, dream_transport.CapacityWait):
            report.update(status='waiting', reason='reserved_capacity')
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
        consumed=[item for item in consumed if item['collection'] + '/' + item['id'] not in deferred],
        deferred=deferred,
        unavailable=unavailable,
        reviewed=reviewed - deferred,
        seeded=seeded,
        cleanup_cursor=cleanup_cursor,
        release=release,
        refund=refund,
        count_failure=report['status'] != 'waiting'
        and not success
        and release
        and report['tokens'] > 0
        and report.get('reasoning_attempted', False),
    )
    if report.get('reason') == 'idle':
        report.pop('run_id', None)
    record_pass(report)
    return report


async def drain(*, limit=100):
    if mode() == 'off' or limit <= 0:
        return []
    results = []
    page = None
    tried = set()
    stop = asyncio.Event()
    drain_seconds = FULL_DRAIN_SECONDS if full_context_enabled() else DRAIN_TIMEOUT_SECONDS
    deadline = asyncio.get_running_loop().time() + drain_seconds
    try:
        async with asyncio.timeout(drain_seconds):
            if await dream_capacity.available_model() is None:
                report = {'status': 'waiting', 'reason': 'reserved_capacity'}
                record_pass(report)
                return [report]
            page = await run_blocking(db_executor, dream_scheduler.candidates, limit=min(limit, 100))
            owners = iter(page)

            async def worker():
                for uid in owners:
                    if mode() == 'off' or stop.is_set():
                        return
                    pass_seconds = FULL_PASS_SECONDS if context_mode(uid) == 'full' else PASS_TIMEOUT_SECONDS
                    if deadline - asyncio.get_running_loop().time() < pass_seconds + FINISH_MARGIN_SECONDS:
                        stop.set()
                        results.append({'status': 'deadline'})
                        return
                    try:
                        report = await run_pass(uid)
                    except Exception as exc:
                        # Owner-local acquire/finish faults must not cancel siblings.
                        report = {
                            'status': 'failed',
                            'error_type': type(exc).__name__,
                            'error_code': error_code(exc),
                            'context_mode': context_mode(uid),
                        }
                        record_pass(report)
                    results.append(report)
                    if report.get('status') == 'waiting':
                        stop.set()
                        return
                    tried.add(uid)

            async with asyncio.TaskGroup() as group:
                for _ in range(concurrency()):
                    group.create_task(worker())
    except TimeoutError:
        results.append({'status': 'deadline'})
    if isinstance(page, dream_scheduler.CandidatePage):
        try:
            await run_blocking(db_executor, dream_scheduler.advance, page, tried)
        except Exception:
            # Failed cursor persistence retries the same page, never skips owners.
            results.append({'status': 'failed', 'error_type': 'CursorWriteError'})
    return results
