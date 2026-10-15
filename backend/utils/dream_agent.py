"""One owner session, two independent verifiers, one reversible effect boundary."""

import asyncio
from collections import Counter
from dataclasses import replace
from functools import partial
from typing import Any

from config.dream_agent import Caps, auto_apply_kinds, enabled, concurrency, PASS_TIMEOUT_SECONDS, DRAIN_TIMEOUT_SECONDS
from database import dream_scheduler, dream_store, dream_turns, review_store
from database.dream_dirty import dream_writing
from models.agent_tools import HarnessQuestion
from models.agent_edit import HarnessEdit
from utils.agent_capabilities import tools as dream_tools
from utils import dream_review_policy, dream_capacity, dream_harness_transport, dream_seed, dream_verify
from utils.agent_capabilities.search import OwnerSearch
from utils.agent_capabilities.session import Session
from utils.dream_instructions import INSTRUCTIONS
from utils.dream_metrics import record_pass, error_code, record_reclaimed
from database.dream_effect_fence import ACTIVE_RUN
from utils.executors import db_executor, run_blocking


async def run_session(
    uid,
    seed,
    records,
    limits,
    *,
    turn=None,
    lease=None,
    caps=None,
    dry_run=False,
    timeout_seconds=PASS_TIMEOUT_SECONDS,
    bootstrap_tools=None,
):
    caps = caps or Caps.from_env()
    started = asyncio.get_running_loop().time()
    deadline = started + timeout_seconds
    report: dict[str, Any] = {
        'status': 'failed',
        'tokens': 0,
        'accounted_tokens': 0,
        'cached_tokens': 0,
        'cache_unreported_tokens': 0,
        'uncached_tokens': 0,
        'usage_unknown': False,
        'usage_complete': False,
        'size_bucket': limits.bucket,
        'mode': 'on',
        'proposed': {'edits': [], 'questions': [], 'vocabulary': []},
        'outcomes': [],
        'model_lanes': [],
        'dry_run': dry_run,
    }
    session = Session(
        uid,
        OwnerSearch(uid),
        limits,
        seed,
        authority='dream',
        records=records,
        instructions=INSTRUCTIONS,
        question_policy=lambda item: item.value > 2,
    )

    async def active():
        if not enabled():
            raise ValueError('dream_disabled')
        if lease is not None:
            await run_blocking(db_executor, dream_store.assert_lease, uid, lease['run_id'])

    session.check_active = active

    async def usage(result):
        report['tokens'] += result.tokens
        report['accounted_tokens'] += result.tokens if result.accounted_tokens is None else result.accounted_tokens
        session.accounted_model_tokens = report['accounted_tokens']
        if result.cached_tokens is None:
            report['cache_unreported_tokens'] += result.prompt_tokens
        else:
            report['cached_tokens'] += result.cached_tokens
            report['cache_unreported_tokens'] += result.cache_unreported_tokens
            report['uncached_tokens'] += max(
                0, result.prompt_tokens - result.cached_tokens - result.cache_unreported_tokens
            )
        if lease is not None:
            await run_blocking(db_executor, dream_turns.settle, uid, lease['run_id'], result)

    async def invoke(lane, mount, messages):
        await active()
        remaining = limits.tokens - report['accounted_tokens'] - session.counters['search_embedding_token_upper_bound']
        mount = replace(mount, budget=replace(mount.budget, tokens=min(mount.budget.tokens or 0, remaining)))
        if mount.budget.tokens is None or mount.budget.tokens < 1024:
            raise ValueError('dream_input_token_budget')
        ceiling = dream_harness_transport.input_bytes(messages, mount)
        completion = (
            limits.verifier_completion_tokens
            if lane == dream_harness_transport.VERIFY_LANE
            else limits.completion_tokens
        )
        reserve = min(mount.budget.tokens, 2 * (ceiling + completion))
        if lease is not None:
            await run_blocking(db_executor, dream_turns.reserve, uid, lease['run_id'], reserve, caps)
        report['model_lanes'].append(lane)
        sink = {}
        try:
            if turn is not None:
                result = await turn(uid, lane, mount, messages)
                await usage(result)
                return result
            return await dream_harness_transport.model_turn(
                uid,
                lane,
                mount,
                messages,
                completion_limit=completion,
                model_seconds=min(
                    limits.verifier_seconds if lane == dream_harness_transport.VERIFY_LANE else limits.model_seconds,
                    max(1, deadline - asyncio.get_running_loop().time()),
                ),
                on_usage=usage,
                usage_sink=sink,
            )
        finally:
            if lane == dream_harness_transport.VERIFY_LANE and sink.get('transport_complete'):
                report['verifier_transport_responses'] = report.get('verifier_transport_responses', 0) + 1
            report['usage_unknown'] |= sink.get('usage_unknown', False)

    async def effect(fn, *args, **kwargs):
        await active()
        if dry_run:
            return 'dry_run'
        return await run_blocking(db_executor, partial(fn, uid, *args, **kwargs))

    try:
        async with asyncio.timeout(timeout_seconds):
            await active()
            try:
                if bootstrap_tools is not None:
                    await session.execute(bootstrap_tools)
                    report['stop_reason'] = 'synthetic_tools'
                else:
                    result = await session.run(
                        partial(invoke, dream_harness_transport.MAIN_LANE),
                        deadline_seconds=max(1, timeout_seconds - 300),
                    )
                    report['stop_reason'] = result.reason
            except Exception as exc:
                # Already staged work survives model/budget exhaustion. The live
                # kill/lease boundary is rechecked before verification and effects.
                report['stop_reason'] = error_code(exc) or type(exc).__name__
                if not session.staged:
                    raise
            await active()
            staged = list(session.staged.values())
            verification_telemetry = {}
            support, calls = await dream_verify.verify(
                staged,
                partial(invoke, dream_harness_transport.VERIFY_LANE),
                tokens=min(limits.verification_tokens, max(0, limits.tokens - report['accounted_tokens'])),
                deadline_seconds=max(0, deadline - asyncio.get_running_loop().time() - min(60, timeout_seconds / 10)),
                verifier_seconds=limits.verifier_seconds,
                completion_tokens=limits.verifier_completion_tokens,
                telemetry=verification_telemetry,
            )
            report['verifier_calls'] = calls
            report['verifier_transport_responses'] = max(
                report.get('verifier_transport_responses', 0), verification_telemetry.get('transport_responses', 0)
            )
            report['verifier_valid_responses'] = sum(
                isinstance(vote, bool) for votes in support.values() for vote in votes
            )
            decisions = Counter()
            demoted = await run_blocking(db_executor, dream_store.demoted_types, uid, caps)
            automatic = auto_apply_kinds(uid) - demoted
            offered = []
            if not dry_run and lease is None:
                raise ValueError('dream_lease_required')
            effect_scope = ACTIVE_RUN.set((uid, lease['run_id']) if lease else None)
            token = dream_writing.set(True)
            try:
                for item in staged:
                    decision = dream_verify.disposition(support[item.id])
                    auto_allowed = item.kind in automatic and not (
                        isinstance(item.operation, HarnessEdit)
                        and dream_tools.target_authority_protected(item.operation, item.records)
                    )
                    decisions[decision] += 1
                    category = (
                        'questions'
                        if isinstance(item.operation, HarnessQuestion)
                        else 'edits' if isinstance(item.operation, HarnessEdit) else 'vocabulary'
                    )
                    report['proposed'][category].append(
                        {
                            **item.operation.model_dump(mode='python'),
                            'key': item.key,
                            'policy': 'auto' if decision == 'agree' and auto_allowed else 'suggest',
                        }
                    )
                    if decision in {'disagree', 'unverified'}:
                        report['outcomes'].append(
                            {'key': item.key, 'kind': item.kind, 'status': 'verifier_' + decision}
                        )
                    elif decision == 'agree' and auto_allowed and not isinstance(item.operation, HarnessQuestion):
                        try:
                            if isinstance(item.operation, HarnessEdit):
                                status = await effect(
                                    dream_tools.apply_verified_edit,
                                    item.operation,
                                    item.records,
                                    expected_records=item.fences,
                                    authority='dream',
                                )
                            else:
                                status = await effect(
                                    dream_tools.apply_vocabulary,
                                    [item.operation],
                                    expected_records=item.fences,
                                    verified=True,
                                    records=item.records,
                                )
                        except (ValueError, review_store.ReviewConflict, review_store.ReviewNotFound):
                            status = 'invalid_evidence'
                        report['outcomes'].append({'key': item.key, 'kind': item.kind, 'status': status})
                    elif item.value > 2:
                        offered.append((item, sum(vote is True for vote in support[item.id])))
                # Actual enqueue shares Review's daily proposal/answer attention
                # ledger. Failed/suppressed offers cannot consume an apply slot.
                offered.sort(key=lambda pair: (pair[0].value, pair[1]), reverse=True)
                for item, _ in offered[:3]:
                    try:
                        if isinstance(item.operation, HarnessQuestion):
                            status = await effect(
                                dream_review_policy.ask_ranked,
                                item.operation,
                                item.records,
                                lease['run_id'] if lease else 'dry-run',
                            )
                        elif isinstance(item.operation, HarnessEdit):
                            status = await effect(
                                dream_review_policy.suggest_edit,
                                item.operation,
                                item.records,
                                run_id=lease['run_id'] if lease else 'dry-run',
                            )
                        else:
                            status = await effect(dream_review_policy.suggest_vocabulary, item.operation, item.records)
                    except (ValueError, review_store.ReviewConflict, review_store.ReviewNotFound):
                        status = 'invalid_evidence'
                    report['outcomes'].append({'key': item.key, 'kind': item.kind, 'status': status})
            finally:
                dream_writing.reset(token)
                ACTIVE_RUN.reset(effect_scope)
            report['verifier_outcomes'] = dict(decisions)
            report.update(
                status='complete',
                notes=session.finish.notes if session.finish else '',
                summary=session.finish.summary if session.finish else '',
            )
    except Exception as exc:
        report.update(status='failed', error_type=type(exc).__name__, error_code=error_code(exc))
        if isinstance(exc, dream_harness_transport.CapacityWait) or str(exc) == 'dream_minute_headroom':
            report.update(status='waiting', reason='reserved_capacity')
    report['accounted_tokens'] += session.counters['search_embedding_token_upper_bound']
    report.update(
        tool_counts={key[5:]: count for key, count in session.counters.items() if key.startswith('tool:')},
        turns=len([lane for lane in report['model_lanes'] if lane == dream_harness_transport.MAIN_LANE]),
        rejected=dict(session.rejections),
        resubmits_succeeded=session.counters['resubmits_succeeded'],
        records_read=len(session.records),
        read_bytes=session.read_bytes,
        usage_complete=not report['usage_unknown'],
        cost_usd=report['tokens'] * caps.max_usd_per_token,
        cost_usd_upper_bound=report['accounted_tokens'] * caps.max_usd_per_token,
    )
    return report, session


async def run_pass(
    uid,
    *,
    caps=None,
    turn=None,
    trigger='schedule',
    canary=False,
    timeout_seconds=PASS_TIMEOUT_SECONDS,
    progress=None,
    dry_run=False,
    bootstrap_tools=None,
):
    if not enabled():
        report = {'status': 'not_admitted', 'reason': 'disabled'}
        if not dry_run:
            record_pass(report)
        return report
    caps = caps or Caps.from_env()
    if bootstrap_tools is not None and not canary:
        raise ValueError('dream_bootstrap_requires_synthetic_canary')
    slot = await dream_capacity.claim(concurrency(), slot_seconds=timeout_seconds + 120) if not dry_run else None
    if not dry_run and slot is None:
        report = {'status': 'waiting', 'reason': 'reserved_capacity'}
        record_pass(report)
        return report
    lease = None
    release_slot = False
    try:
        seed, records, dirty, limits = await run_blocking(db_executor, dream_seed.load, uid, caps)
        limits = replace(
            limits,
            completion_tokens=min(limits.completion_tokens, caps.completion_tokens),
            verifier_completion_tokens=min(limits.verifier_completion_tokens, caps.completion_tokens),
        )
        caps = replace(caps, tokens=limits.tokens)
        if not dry_run:
            reclaimed = {}
            try:
                lease = await run_blocking(
                    db_executor, dream_store.acquire, uid, caps, trigger=trigger, canary=canary, reclaim_sink=reclaimed
                )
            finally:
                if reclaimed:
                    record_reclaimed(**reclaimed)
            if lease is None:
                release_slot = True
                report = {'status': 'not_admitted'}
                record_pass(report)
                return report
        if limits.bucket == 'empty' and not seed.get('targets'):
            report: dict[str, Any] = {
                'status': 'not_admitted',
                'reason': 'idle',
                'tokens': 0,
                'accounted_tokens': 0,
                'usage_unknown': False,
                'usage_complete': True,
                'size_bucket': 'empty',
                'mode': 'on',
                'proposed': {'edits': [], 'questions': [], 'vocabulary': []},
                'outcomes': [],
            }
            session = Session(
                uid,
                OwnerSearch(uid),
                limits,
                seed,
                authority='dream',
                records=records,
                instructions=INSTRUCTIONS,
                question_policy=lambda item: item.value > 2,
            )
        else:
            report, session = await run_session(
                uid,
                seed,
                records,
                limits,
                turn=turn,
                lease=lease,
                caps=caps,
                dry_run=dry_run or canary,
                timeout_seconds=timeout_seconds,
                bootstrap_tools=bootstrap_tools,
            )
        if progress is not None:
            progress['report'] = report
        if lease is not None:
            report.update(
                run_id=lease['run_id'], trigger=trigger, mode=lease['mode'], cost_usd_reserved=caps.reservation_usd
            )
            consumed = [item for item in dirty if item['collection'] + '/' + item['id'] in session.records]
            unavailable = [
                {**item, 'transient': session.unavailable[item['collection'] + '/' + item['id']]}
                for item in dirty
                if item['collection'] + '/' + item['id'] in session.unavailable
            ]
            await run_blocking(
                db_executor,
                dream_store.finish,
                uid,
                lease,
                report,
                success=report['status'] == 'complete' or report.get('reason') == 'idle',
                consumed=consumed,
                unavailable=unavailable,
                reviewed=set(session.records),
                refund=report['tokens'] == 0 and not report['usage_unknown'],
                release=report.get('error_type') != 'TimeoutError',
            )
        if report.get('reason') == 'idle':
            report.pop('run_id', None)
        if not dry_run:
            record_pass(report)
        release_slot = report.get('error_type') != 'TimeoutError'
        return report
    except Exception as exc:
        release_slot = not isinstance(exc, TimeoutError)
        raise
    finally:
        # Canceled/timed-out IO may still hold a synchronous operation. Its
        # capacity and owner leases retain their TTL fences until reclaim.
        if slot is not None and release_slot:
            await dream_capacity.release(slot)


async def drain(*, limit=5000):
    if not enabled() or limit <= 0:
        return []
    results = []
    try:
        async with asyncio.timeout(DRAIN_TIMEOUT_SECONDS):
            if await dream_capacity.available_model() is None:
                report = {'status': 'waiting', 'reason': 'reserved_capacity'}
                record_pass(report)
                return [report]
            page = await run_blocking(db_executor, dream_scheduler.candidates, limit=min(limit, 5000))
            owners = iter(page)

            async def worker():
                for uid in owners:
                    if not enabled():
                        return
                    try:
                        report = await run_pass(uid)
                    except Exception as exc:
                        report = {'status': 'failed', 'error_type': type(exc).__name__, 'error_code': error_code(exc)}
                    results.append(report)
                    while report['status'] == 'waiting' and enabled():
                        await asyncio.sleep(60)
                        report = await run_pass(uid)
                        results.append(report)

            async with asyncio.TaskGroup() as group:
                for _ in range(concurrency()):
                    group.create_task(worker())
    except TimeoutError:
        results.append({'status': 'deadline'})
    return results
