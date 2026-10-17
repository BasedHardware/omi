"""One owner session, two independent verifiers, one reversible effect boundary."""

import asyncio
from datetime import datetime, timezone
from collections import Counter
from dataclasses import replace
from functools import partial
from typing import Any

from config.dream_agent import (
    Caps,
    admission_for,
    auto_apply_kinds,
    concurrency,
    enabled,
    may_be_eligible,
    on_demand_enabled,
    PASS_TIMEOUT_SECONDS,
    DRAIN_TIMEOUT_SECONDS,
)
from database import dream_scheduler, dream_store, dream_turns, legal_holds, review_store
from database.dream_dirty import dream_writing
from database.legal_holds import DestructiveOperationInProgress, LegalHoldActive
from models.agent_tools import HarnessQuestion
from models.agent_edit import HarnessEdit
from utils.agent_capabilities import tools as dream_tools
from utils.agent_capabilities import verifiers
from utils import dream_review_policy, dream_capacity, dream_harness_transport, dream_seed, dream_verify
from utils.dream_cost import (
    conservative_attempt_micro,
    minute_burndown_tokens,
    price_weighted_tokens,
    verification_reserve_tokens,
)
from utils.agent_capabilities.search import OwnerSearch
from utils.agent_capabilities.session import Session
from utils.dream_instructions import INSTRUCTIONS
from utils.dream_metrics import record_pass, error_code, record_reclaimed
from database.dream_effect_fence import ACTIVE_RUN
from utils.executors import db_executor, run_blocking

TAIL_BUDGET_NOTICE_THRESHOLD = 0.20
MINUTE_HEADROOM_RETRIES = 3
PROVIDER_STOP_CODES = frozenset({'dream_gateway_rejected', 'dream_gateway_failure'})
# A billed but unusable model reply late in a pass; staged work is still verified.
MODEL_OUTPUT_STOP_CODES = frozenset({'dream_response_truncated', 'dream_invalid_tool_calls'})
BUDGET_STOP_CODES = frozenset(
    {
        'dream_input_token_budget',
        'dream_daily_budget',
    }
)
GATE_CONTENTION_BACKOFF_SECONDS = (5, 15, 30, 60)
GATE_CONTENTION_APPLY_HEADROOM_SECONDS = 20
GATE_CONTENTION_RETRY_BUDGET_SECONDS = sum(GATE_CONTENTION_BACKOFF_SECONDS) + GATE_CONTENTION_APPLY_HEADROOM_SECONDS + 1
RETRYABLE_GATE_CONTENTION_MESSAGES = frozenset(
    {
        'another destructive operation owns the account gate',
        'canonical mutation blocked by destructive operation',
        'external data write blocked by destructive operation',
    }
)


def _exception_chain(error):
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        yield error
        error = error.__cause__ or error.__context__


def _retryable_gate_contention(error):
    chain = tuple(_exception_chain(error))
    if any(type(item) is LegalHoldActive for item in chain):
        return False
    if any('account deletion' in str(item).lower() for item in chain):
        return False
    return any(
        type(item) is DestructiveOperationInProgress and str(item) in RETRYABLE_GATE_CONTENTION_MESSAGES
        for item in chain
    )


async def _sleep_gate_retry(seconds):
    await asyncio.sleep(seconds)


def _cheap_turn(staged, invoke):
    """Bind one named cheap lane. Unset, VERIFY_LANE, or disagreeing lanes stay a no-op."""
    lanes = []
    for item in staged:
        policy = verifiers.policy_for(verifiers.item_kind(item))
        for step in policy.steps:
            if step.strategy != 'cheap_model':
                continue
            lane = step.lane
            if not lane or lane == dream_harness_transport.VERIFY_LANE or lane in lanes:
                continue
            lanes.append(lane)
    if len(lanes) != 1:
        return None
    return partial(invoke, lanes[0])


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
        'price_weighted_tokens': 0,
        'cached_tokens': 0,
        'cache_unreported_tokens': 0,
        'uncached_tokens': 0,
        'usage_unknown': False,
        'usage_complete': False,
        'cost_status': 'priced',
        'cost_micro_usd': 0,
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
        weighted = getattr(result, 'price_weighted_tokens', None)
        if weighted is None:
            if result.prompt_tokens + result.completion_tokens == result.tokens:
                weighted = price_weighted_tokens(
                    dream_harness_transport.DREAM_PROVIDER,
                    dream_harness_transport.DREAM_MODEL,
                    prompt_tokens=result.prompt_tokens,
                    cached_tokens=result.cached_tokens,
                    completion_tokens=result.completion_tokens,
                    cache_reported=(
                        result.cached_tokens is not None and getattr(result, 'cache_unreported_tokens', 0) == 0
                    ),
                )
            else:
                weighted = result.tokens
            weighted += max(
                0,
                (result.tokens if result.accounted_tokens is None else result.accounted_tokens) - result.tokens,
            )
        if type(weighted) is not int or weighted < 0:
            raise ValueError('dream_invalid_usage')
        result.price_weighted_tokens = weighted
        report['price_weighted_tokens'] += weighted
        session.accounted_model_tokens = report['price_weighted_tokens']
        if result.cached_tokens is None:
            report['cache_unreported_tokens'] += result.prompt_tokens
        else:
            report['cached_tokens'] += result.cached_tokens
            report['cache_unreported_tokens'] += result.cache_unreported_tokens
            report['uncached_tokens'] += max(
                0, result.prompt_tokens - result.cached_tokens - result.cache_unreported_tokens
            )
        status = getattr(result, 'cost_status', None)
        micro = getattr(result, 'cost_micro_usd', None)
        if status == 'priced' and type(micro) is int and report.get('cost_status') != 'unpriced':
            report['cost_micro_usd'] = report.get('cost_micro_usd', 0) + micro
            report['cost_status'] = 'priced'
        else:
            report['cost_status'] = 'unpriced'
            report.pop('cost_micro_usd', None)
        if lease is not None:
            await run_blocking(db_executor, dream_turns.settle, uid, lease['run_id'], result)

    main_history = {'prompt_tokens': None, 'messages': 0, 'cached_tokens': None}
    budget_notice_sent = False

    async def invoke(lane, mount, messages):
        nonlocal budget_notice_sent
        await active()
        remaining = (
            limits.tokens - report['price_weighted_tokens'] - session.counters['search_embedding_token_upper_bound']
        )
        if (
            lane == dream_harness_transport.MAIN_LANE
            and not budget_notice_sent
            and limits.tokens > 0
            and remaining <= limits.tokens * TAIL_BUDGET_NOTICE_THRESHOLD
        ):
            remaining_percent = max(0, min(100, int(100 * remaining / limits.tokens)))
            notice = (
                f"BUDGET NOTICE: about {remaining_percent}% of this pass's budget remains. "
                'Stage your strongest findings now with propose_* (or finish if there is nothing worth '
                'proposing); avoid new broad searches.'
            )
            if messages and messages[-1].get('role') == 'tool' and isinstance(messages[-1].get('content'), str):
                # Gemini rejects free text beside functionResponse parts in one user turn, so the
                # notice rides inside the latest tool result instead of a separate message.
                messages[-1] = {**messages[-1], 'content': messages[-1]['content'] + '\n\n' + notice}
            else:
                messages.append({'role': 'user', 'content': notice})
            budget_notice_sent = True
        mount = replace(mount, budget=replace(mount.budget, tokens=min(mount.budget.tokens or 0, remaining)))
        if mount.budget.tokens is None or mount.budget.tokens < 1024:
            raise ValueError('dream_input_token_budget')
        completion = (
            limits.verifier_completion_tokens
            if lane == dream_harness_transport.VERIFY_LANE
            else limits.completion_tokens
        )
        prior = main_history['prompt_tokens'] if lane == dream_harness_transport.MAIN_LANE else None
        prior_count = main_history['messages'] if lane == dream_harness_transport.MAIN_LANE else 0
        cached_estimate = main_history['cached_tokens'] if lane == dream_harness_transport.MAIN_LANE else None
        if type(prior_count) is not int:
            prior_count = 0
        estimate, completion_room = dream_harness_transport.attempt_room(
            messages,
            mount,
            prior_prompt_tokens=prior,
            prior_message_count=prior_count,
            cached_tokens_estimate=cached_estimate,
            completion_limit=completion,
        )
        # The shared minute ceiling counts reserved-capacity burndown (cached input 0.1, output 5x), not raw
        # tokens: counting every resent cached prefix in full stopped fast passes after a few minutes.
        reserve = minute_burndown_tokens(
            'gemini',
            'gemini-3.8-flash',
            weighted_tokens=price_weighted_tokens(
                'gemini',
                'gemini-3.8-flash',
                prompt_tokens=estimate,
                cached_tokens=(
                    min(cached_estimate, estimate) if type(cached_estimate) is int and cached_estimate >= 0 else None
                ),
                completion_tokens=completion_room,
            ),
            completion_tokens=completion_room,
            prompt_tokens=estimate,
        )
        micro, price_status = conservative_attempt_micro('gemini', 'gemini-3.8-flash', estimate, completion_room)
        if lease is not None:
            for attempt in range(MINUTE_HEADROOM_RETRIES + 1):
                try:
                    await run_blocking(
                        db_executor,
                        dream_turns.reserve,
                        uid,
                        lease['run_id'],
                        reserve,
                        caps,
                        cost_micro_usd=micro if price_status == 'priced' else None,
                    )
                    break
                except ValueError as exc:
                    # A full minute pauses the pass until the next minute instead of discarding it.
                    pause = 61 - datetime.now(timezone.utc).second
                    if (
                        str(exc) != 'dream_minute_headroom'
                        or attempt == MINUTE_HEADROOM_RETRIES
                        or asyncio.get_running_loop().time() + pause + 60 > deadline
                    ):
                        raise
                    await asyncio.sleep(pause)
                    await active()
        report['model_lanes'].append(lane)
        sink = {}
        try:
            if turn is not None:
                result = await turn(uid, lane, mount, messages)
                await usage(result)
                if lane == dream_harness_transport.MAIN_LANE and result.prompt_tokens:
                    main_history['prompt_tokens'] = result.prompt_tokens
                    main_history['messages'] = len(messages)
                    main_history['cached_tokens'] = (
                        result.cached_tokens
                        if result.cached_tokens is not None and getattr(result, 'cache_unreported_tokens', 0) == 0
                        else None
                    )
                return result
            result = await dream_harness_transport.model_turn(
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
                prior_prompt_tokens=prior,
                prior_message_count=prior_count,
                cached_tokens_estimate=cached_estimate,
            )
            if lane == dream_harness_transport.MAIN_LANE and result.prompt_tokens:
                main_history['prompt_tokens'] = result.prompt_tokens
                main_history['messages'] = len(messages)
                main_history['cached_tokens'] = (
                    result.cached_tokens
                    if result.cached_tokens is not None and result.cache_unreported_tokens == 0
                    else None
                )
            return result
        finally:
            if lane == dream_harness_transport.VERIFY_LANE and sink.get('transport_complete'):
                report['verifier_transport_responses'] = report.get('verifier_transport_responses', 0) + 1
            report['usage_unknown'] |= sink.get('usage_unknown', False)

    async def effect(fn, *args, **kwargs):
        await active()
        if dry_run:
            return 'dry_run'
        return await run_blocking(db_executor, partial(fn, uid, *args, **kwargs))

    gate_retry_deadline = None
    gate_retry_in_progress = False

    async def effect_with_gate_retry(fn, *args, **kwargs):
        nonlocal gate_retry_deadline, gate_retry_in_progress
        loop = asyncio.get_running_loop()
        delay_index = 0
        attempt = 0
        while True:
            attempt += 1
            effect_kwargs = kwargs
            if attempt > 1 and fn is dream_tools.apply_verified_edit:
                effect_kwargs = {
                    **kwargs,
                    'gate_retry': True,
                    'run_started_at': (lease or {}).get('started_at'),
                    'run_id': (lease or {}).get('run_id'),
                }
            try:
                result = await effect(fn, *args, **effect_kwargs)
                gate_retry_in_progress = False
                return result
            except Exception as exc:
                if not _retryable_gate_contention(exc):
                    raise
                gate_retry_in_progress = True
                now = loop.time()
                if gate_retry_deadline is None:
                    gate_retry_deadline = min(deadline, now + GATE_CONTENTION_RETRY_BUDGET_SECONDS)
                retry_allowed = await run_blocking(db_executor, legal_holds.dream_gate_contention_retry_allowed, uid)
                if not retry_allowed:
                    gate_retry_in_progress = False
                    raise
                now = loop.time()
                if delay_index >= len(GATE_CONTENTION_BACKOFF_SECONDS):
                    raise ValueError('dream_gate_contention') from exc
                delay = GATE_CONTENTION_BACKOFF_SECONDS[delay_index]
                delay_index += 1
                retry_deadline = min(deadline, gate_retry_deadline)
                if now + delay + GATE_CONTENTION_APPLY_HEADROOM_SECONDS >= retry_deadline:
                    raise ValueError('dream_gate_contention') from exc
                await _sleep_gate_retry(delay)
                if loop.time() + GATE_CONTENTION_APPLY_HEADROOM_SECONDS >= retry_deadline:
                    raise ValueError('dream_gate_contention') from exc
                await active()

    try:
        async with asyncio.timeout(timeout_seconds):
            await active()
            budget_stop_without_staged_work = False
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
                stop_code = error_code(exc)
                provider_stop = bool(session.staged) and (
                    (
                        type(exc) in (dream_harness_transport.PreTokenFailure, RuntimeError)
                        and str(exc) in PROVIDER_STOP_CODES
                    )
                    or stop_code in MODEL_OUTPUT_STOP_CODES
                )
                if provider_stop:
                    # A late provider failure must not discard work already staged this pass.
                    stop_code = stop_code or str(exc)
                elif stop_code not in BUDGET_STOP_CODES:
                    raise
                # Budget exhaustion is a normal terminal outcome even when it
                # leaves nothing to verify. Staged proposals still cross the
                # usual independent-verification boundary below.
                report['stop_reason'] = stop_code
                budget_stop_without_staged_work = not session.staged
                if budget_stop_without_staged_work:
                    report.update(status='complete', notes='', summary='')
            await active()
            staged = list(session.staged.values())
            verification_telemetry = {}
            # batches() sizes its evidence byte ceiling as tokens // 8, capped at
            # 24000. A reserve that only pays for the two model calls would shrink
            # that ceiling and drop evidence. Keep the ceiling open; the reserve
            # is still what the two calls need, and it is not held in the main loop.
            verify_need = max(
                verification_reserve_tokens(staged, completion_tokens=limits.verifier_completion_tokens),
                8 * 24000,
            )
            verify_budget = min(verify_need, max(0, limits.tokens - report['price_weighted_tokens']))
            if budget_stop_without_staged_work:
                support, calls = {}, 0
            else:
                support, calls = await dream_verify.verify(
                    staged,
                    partial(invoke, dream_harness_transport.VERIFY_LANE),
                    tokens=verify_budget,
                    deadline_seconds=max(
                        0, deadline - asyncio.get_running_loop().time() - min(60, timeout_seconds / 10)
                    ),
                    verifier_seconds=limits.verifier_seconds,
                    completion_tokens=limits.verifier_completion_tokens,
                    telemetry=verification_telemetry,
                    cheap_turn=_cheap_turn(staged, invoke),
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
                    default_policy = verifiers.is_default_policy(verifiers.policy_for(verifiers.item_kind(item)))
                    # The default two-verifier path records unverified and does not
                    # enqueue it. A non-default chain's unverified result uses the
                    # same offer path as a split. Disagreement is never offered.
                    if decision == 'disagree' or (decision == 'unverified' and default_policy):
                        report['outcomes'].append(
                            {'key': item.key, 'kind': item.kind, 'status': 'verifier_' + decision}
                        )
                    elif decision == 'agree' and auto_allowed and not isinstance(item.operation, HarnessQuestion):
                        try:
                            if isinstance(item.operation, HarnessEdit):
                                status = await effect_with_gate_retry(
                                    dream_tools.apply_verified_edit,
                                    item.operation,
                                    item.records,
                                    expected_records=item.fences,
                                    authority='dream',
                                )
                            else:
                                status = await effect_with_gate_retry(
                                    dream_tools.apply_vocabulary,
                                    [item.operation],
                                    expected_records=item.fences,
                                    verified=True,
                                    records=item.records,
                                )
                        except (review_store.ReviewConflict, review_store.ReviewNotFound):
                            status = 'invalid_evidence'
                        except ValueError as exc:
                            if str(exc) == 'dream_gate_contention':
                                raise
                            status = 'invalid_evidence'
                        report['outcomes'].append({'key': item.key, 'kind': item.kind, 'status': status})
                    elif item.value > 2:
                        offered.append((item, sum(vote is True for vote in support[item.id])))
                    elif decision == 'unverified':
                        report['outcomes'].append({'key': item.key, 'kind': item.kind, 'status': 'verifier_unverified'})
                # Actual enqueue shares Review's daily proposal/answer attention
                # ledger. Failed/suppressed offers cannot consume an apply slot.
                offered.sort(key=lambda pair: (pair[0].value, pair[1]), reverse=True)
                for item, _ in offered[:3]:
                    try:
                        if isinstance(item.operation, HarnessQuestion):
                            status = await effect_with_gate_retry(
                                dream_review_policy.ask_ranked,
                                item.operation,
                                item.records,
                                lease['run_id'] if lease else 'dry-run',
                            )
                        elif isinstance(item.operation, HarnessEdit):
                            status = await effect_with_gate_retry(
                                dream_review_policy.suggest_edit,
                                item.operation,
                                item.records,
                                run_id=lease['run_id'] if lease else 'dry-run',
                            )
                        else:
                            status = await effect_with_gate_retry(
                                dream_review_policy.suggest_vocabulary, item.operation, item.records
                            )
                    except (review_store.ReviewConflict, review_store.ReviewNotFound):
                        status = 'invalid_evidence'
                    except ValueError as exc:
                        if str(exc) == 'dream_gate_contention':
                            raise
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
        if isinstance(exc, TimeoutError) and gate_retry_in_progress:
            exc = ValueError('dream_gate_contention')
        code = error_code(exc)
        report.update(status='failed', error_type=type(exc).__name__, error_code=code)
        if code == 'dream_gate_contention':
            report['stop_reason'] = code
        if isinstance(exc, dream_harness_transport.CapacityWait) or str(exc) == 'dream_minute_headroom':
            report.update(status='waiting', reason='reserved_capacity')
    report['accounted_tokens'] += session.counters['search_embedding_token_upper_bound']
    report['price_weighted_tokens'] += session.counters['search_embedding_token_upper_bound']
    report.update(
        tool_counts={key[5:]: count for key, count in session.counters.items() if key.startswith('tool:')},
        turns=len([lane for lane in report['model_lanes'] if lane == dream_harness_transport.MAIN_LANE]),
        rejected=dict(session.rejections),
        resubmits_succeeded=session.counters['resubmits_succeeded'],
        records_read=len(session.records),
        read_bytes=session.read_bytes,
        usage_complete=not report['usage_unknown'],
        cost_status=report.get('cost_status', 'unpriced'),
        cost_usd=(report['cost_micro_usd'] / 1000000 if report.get('cost_status') == 'priced' else None),
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
    # Reject stale queue entries before capacity waits or owner-data loading.
    # Synthetic canaries have separate, authoritative admission in acquire().
    if not canary and not may_be_eligible(uid):
        report = {'status': 'not_admitted', 'reason': 'ineligible'}
        record_pass(report)
        if not dry_run:
            await run_blocking(db_executor, dream_scheduler.remove_due, uid)
        return report
    mode, allowlisted = admission_for(uid)
    slot = (
        await dream_capacity.claim(
            concurrency(), slot_seconds=timeout_seconds + 120, mode=mode, owner_allowlisted=allowlisted
        )
        if not dry_run
        else None
    )
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
            completion_tokens=caps.completion_tokens,
            verifier_completion_tokens=min(limits.verifier_completion_tokens, caps.verifier_completion_tokens),
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
                run_id=lease['run_id'], trigger=trigger, mode=lease['mode'], cost_status=report.get('cost_status')
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
            reserved_open = await dream_capacity.available_model(mode='reserved') is not None
            if not reserved_open and not on_demand_enabled():
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
