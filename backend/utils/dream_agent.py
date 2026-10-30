"""One owner session, two independent verifiers, one reversible effect boundary."""

from utils.generated_compute import generated_compute_allowed, generated_compute_configured
from config.vertex_reservations import PROBE_SECONDS, PROBE_TIMEOUT_SECONDS

import asyncio
import json
import time
import logging
import uuid
from datetime import datetime, timezone
from collections import Counter
from dataclasses import replace
from functools import partial
from pathlib import Path
from typing import Any

from config.dream_agent import (
    Caps,
    admission_for,
    auto_apply_kinds,
    concurrency,
    enabled,
    may_be_eligible,
    number,
    on_demand_enabled,
    PASS_TIMEOUT_SECONDS,
    DRAIN_TIMEOUT_SECONDS,
    FINISH_MARGIN_SECONDS,
)
from config import dream_levers
from config.dream_session import HEAVY_TOKENS, LIGHT_TOKENS, MEDIUM_TOKENS
from database import dream_feedback
from database import dream_scheduler, dream_store, dream_turns, legal_holds, review_store
from database.account_deletion_marker import account_deletion_blocks_user_work
from config.rollout_cohorts import warm_rollout_cohorts, RolloutCohortUnavailable
from database.dream_dirty import dream_writing
from database.legal_holds import DestructiveOperationInProgress, LegalHoldActive
from models.agent_tools import HarnessQuestion
from models.agent_edit import HarnessEdit
from utils.agent_capabilities import tools as dream_tools
from utils.agent_capabilities import verifiers
from utils import dream_review_policy, dream_capacity, dream_harness_transport, dream_seed, dream_prescan, dream_verify
from utils import dream_required_intake
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
from utils import dream_telemetry
from utils.agent_capabilities.guards import FEEDBACK_PER_PASS
from database.dream_effect_fence import ACTIVE_RUN
from utils.executors import db_executor, run_blocking
from utils.model_text import ContextWindow
from utils.memory.required_intake import retry_sweep
from utils.memory.canonical_consolidation import complete_receipted_required_intake

TAIL_BUDGET_NOTICE_THRESHOLD = 0.20
logger = logging.getLogger(__name__)

# Lever B3 (no-progress stop): this many consecutive tool batches without a new
# staged proposal, after the pass spent this share of its token budget.
NO_PROGRESS_BATCHES_DEFAULT = 8
NO_PROGRESS_MIN_TOKEN_SHARE_DEFAULT = 0.25
# Lever B4 (history compaction): once the main prompt reaches this size, older
# large tool results are replaced by a stub. Only tool results are elided; the
# system prompt, seed, assistant tool calls and the latest results stay intact.
COMPACT_TRIGGER_PROMPT_TOKENS_DEFAULT = 64000
COMPACT_KEEP_RECENT_TOOL_RESULTS_DEFAULT = 6
COMPACT_MIN_CHARS = 2000
ELIDED_TOOL_RESULT = 'UNTRUSTED TOOL DATA\n' + json.dumps(
    {
        'status': 'elided',
        'note': 'Older tool result removed to save budget. Records already read stay available to '
        'propose_edit and the verifiers; read a ref again if you need its details.',
    }
)
# Lever B5 (material budget): new-material thresholds for the medium and heavy token ceilings.
MATERIAL_MEDIUM = 5
MATERIAL_HEAVY = 16


def _tunable(key, default):
    # A malformed tuning value keeps the default; tuning never fails a pass.
    try:
        return number(key, default)
    except (TypeError, ValueError):
        return default


def cap_tail(staged, capped, outcomes):
    """B5 shadow: work staged after the pass crossed the would-be cap, and how much of it applied."""
    late = set() if capped is None else {key for key in staged if key not in capped}
    return {
        'crossed': capped is not None,
        'staged_after_cap': len(late),
        'applied_after_cap': sum(
            1 for row in outcomes if isinstance(row, dict) and row.get('key') in late and row.get('status') == 'applied'
        ),
    }


def material_tokens(material, current):
    """Token ceiling by new material, never above today's size ceiling nor below the light budget."""
    tier = (
        HEAVY_TOKENS if material >= MATERIAL_HEAVY else MEDIUM_TOKENS if material >= MATERIAL_MEDIUM else LIGHT_TOKENS
    )
    return min(current, max(tier, min(current, LIGHT_TOKENS)))


def _backlog_owed(uid):
    # Required-intake backlog rides Dream passes without a dirty mark. Unknown means owed.
    try:
        from config import required_memory_intake

        return required_memory_intake.backlog_enabled(uid)
    except Exception:
        return True


_FAILURE_STAGES = {
    ('dream_seed.py', 'load'): 'seed',
    ('dream_store.py', 'acquire'): 'acquire',
    ('dream_store.py', 'assert_lease'): 'lease_check',
    ('dream_store.py', 'finish'): 'finish',
    ('dream_turns.py', 'reserve'): 'turn_reserve',
    ('dream_turns.py', 'settle'): 'turn_settle',
    ('dream_harness_transport.py', 'attempt_room'): 'request_sizing',
    ('dream_harness_transport.py', 'model_turn'): 'model_turn',
    ('dream_verify.py', 'verify'): 'verify',
    ('session.py', 'execute'): 'tools',
}


def _log_pass_failure(exc, *, stage):
    # Frame metadata identifies the failing boundary without exception messages,
    # traceback locals, owner ids, tool arguments, or provider response bodies.
    site = 'unknown'
    for error in _exception_chain(exc):
        frame = error.__traceback__
        while frame is not None:
            code = frame.tb_frame.f_code
            name = Path(code.co_filename).name
            stage = _FAILURE_STAGES.get((name, code.co_name), stage)
            if Path(__file__).resolve().parents[1] in Path(code.co_filename).resolve().parents:
                site = f'{name}:{code.co_name}:{frame.tb_lineno}'
            frame = frame.tb_next
    logger.error(
        'Dream pass failure stage=%s exception_type=%s cause_type=%s site=%s',
        stage,
        type(exc).__name__,
        type(exc.__cause__).__name__ if exc.__cause__ is not None else 'none',
        site,
    )


MINUTE_HEADROOM_RETRIES = 3
CAPACITY_CALL_RETRIES = 5
CAPACITY_RETRY_HEADROOM_SECONDS = 20
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
    arms=None,
    budget_probe=None,
):
    caps = caps or Caps.from_env()
    arms = arms or {}
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
        'completion_tokens': 0,
        'token_limit': limits.tokens,
    }
    timing = {'wait_ms': 0, 'waits': 0, 'wait_gateway_ms': 0, 'wait_headroom_ms': 0, 'model_ms': 0, 'verify_ms': 0}
    levers: dict[str, dict[str, Any]] = {}
    session = Session(
        uid,
        OwnerSearch(
            uid,
            required_candidates={
                ref: row[dream_required_intake.MARKER]
                for ref, row in records.items()
                if dream_required_intake.MARKER in row
            },
        ),
        limits,
        seed,
        authority='dream',
        records=records,
        instructions=INSTRUCTIONS,
        question_policy=lambda item: item.value > 2,
        # Dream reviews the owner's day: temporal search defaults to the trailing 24 hours.
        context_window=ContextWindow.trailing_day(label='dream day'),
    )
    session.counters['search_embedding_token_upper_bound'] += seed.get('required_intake_embedding_tokens', 0)
    stage = 'session'

    async def active():
        nonlocal stage
        previous, stage = stage, 'lease_check'
        if not enabled():
            raise ValueError('dream_disabled')
        if lease is not None:
            await run_blocking(db_executor, dream_store.assert_lease, uid, lease['run_id'])
        if seed.get('required_intake_candidates'):
            await run_blocking(db_executor, dream_required_intake.assert_owner_active, uid)
        stage = previous

    session.check_active = active

    defects: Counter = Counter()

    async def defect_sink(item):
        # The model always hears 'recorded': a rejection or storage failure never steers or fails the pass.
        defects['attempt'] += 1
        if defects['attempt'] > FEEDBACK_PER_PASS:
            defects['capped'] += 1
            return {'status': 'recorded'}
        try:
            await run_blocking(
                db_executor,
                dream_feedback.store,
                uid,
                item,
                {'seed': seed, 'records': dict(session.records)},
                seed.get('vocabulary') or [],
            )
            defects['stored'] += 1
            logger.info('event=dream_defect_report outcome=stored')
        except ValueError as exc:
            reason = (
                str(exc)
                if str(exc).startswith('feedback_') or str(exc) in {'not_a_failure', 'language_not_defect', 'ref_leak'}
                else 'invalid'
            )
            reason = reason if reason.isidentifier() else 'invalid'
            defects['rejected_' + reason] += 1
            logger.info('event=dream_defect_report outcome=rejected reason=%s', reason)
        except Exception as exc:
            defects['error'] += 1
            logger.warning('event=dream_defect_report outcome=error exc=%s', type(exc).__name__)
        return {'status': 'recorded'}

    try:
        if dream_levers.defect_reports_enabled() and not dry_run:
            session.defect_sink = defect_sink
    except Exception:
        pass

    stop_arm = arms.get('no_progress_stop', 'off')
    stop_batches = int(_tunable('DREAM_NO_PROGRESS_BATCHES', NO_PROGRESS_BATCHES_DEFAULT))
    stop_share = _tunable('DREAM_NO_PROGRESS_MIN_TOKEN_SHARE', NO_PROGRESS_MIN_TOKEN_SHARE_DEFAULT)
    progress: dict[str, Any] = {'batches': 0, 'idle': 0, 'staged': 0, 'fired': None, 'capped': None}

    async def after_execute(current):
        try:
            # B5 shadow: staged keys when the pass crossed the material cap, so the
            # report can count the edits a served cap would have cut.
            if budget_probe and progress['capped'] is None and report['price_weighted_tokens'] >= budget_probe:
                progress['capped'] = set(current.staged)
        except Exception as error:
            logger.warning('event=dream_lever_error lever=material_budget exc=%s', type(error).__name__)
        if stop_arm == 'off':
            return False
        try:
            progress['batches'] += 1
            staged_now = len(current.staged)
            if staged_now > progress['staged']:
                progress['staged'] = staged_now
                progress['idle'] = 0
            else:
                progress['idle'] += 1
            if (
                progress['fired'] is None
                and progress['idle'] >= stop_batches
                and report['price_weighted_tokens'] >= limits.tokens * stop_share
            ):
                progress['fired'] = {
                    'batch': progress['batches'],
                    'keys': set(current.staged),
                    'tokens': report['price_weighted_tokens'],
                }
                return stop_arm == 'serve'
        except Exception as error:
            logger.warning('event=dream_lever_error lever=no_progress_stop exc=%s', type(error).__name__)
        return False

    if stop_arm != 'off' or budget_probe:
        session.after_execute = after_execute

    async def usage(result):
        nonlocal stage
        previous, stage = stage, 'usage'
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
        report['completion_tokens'] += max(0, int(getattr(result, 'completion_tokens', 0) or 0))
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
            stage = 'turn_settle'
            await run_blocking(db_executor, dream_turns.settle, uid, lease['run_id'], result)
        stage = previous

    main_history = {'prompt_tokens': None, 'messages': 0, 'cached_tokens': None}
    budget_notice_sent = False

    def remember_main(result, messages):
        main_history['prompt_tokens'] = result.prompt_tokens
        main_history['messages'] = len(messages)
        report.setdefault('first_prompt_tokens', result.prompt_tokens)
        report['last_prompt_tokens'] = result.prompt_tokens

    compact_arm = arms.get('history_compact', 'off')
    compact_trigger = _tunable('DREAM_HISTORY_COMPACT_TRIGGER_TOKENS', COMPACT_TRIGGER_PROMPT_TOKENS_DEFAULT)
    compact_keep = int(_tunable('DREAM_HISTORY_COMPACT_KEEP_RESULTS', COMPACT_KEEP_RECENT_TOOL_RESULTS_DEFAULT))
    compaction = {'arm': compact_arm, 'fired': False, 'compactions': 0, 'elided_chars': 0, 'would_elide_chars': 0}

    def compact(messages):
        # Fail open: compaction trouble leaves the conversation exactly as it was.
        try:
            prior = main_history['prompt_tokens']
            if not prior or prior < compact_trigger:
                return
            tools = [
                index
                for index, message in enumerate(messages)
                if isinstance(message, dict) and message.get('role') == 'tool'
            ]
            older = tools[: max(0, len(tools) - max(1, compact_keep))]
            elide = [
                index
                for index in older
                if isinstance(messages[index].get('content'), str)
                and len(messages[index]['content']) >= COMPACT_MIN_CHARS
                and messages[index]['content'] != ELIDED_TOOL_RESULT
            ]
            chars = sum(len(messages[index]['content']) for index in elide)
            if not elide:
                return
            compaction['fired'] = True
            compaction['would_elide_chars'] = max(compaction['would_elide_chars'], chars)
            if compact_arm != 'serve':
                return
            for index in elide:
                messages[index] = {**messages[index], 'content': ELIDED_TOOL_RESULT}
            compaction['compactions'] += 1
            compaction['elided_chars'] += chars
            # The next size estimate must be recomputed from the shortened history.
            main_history.update(prompt_tokens=None, messages=0, cached_tokens=None)
        except Exception as error:
            compaction['errors'] = compaction.get('errors', 0) + 1
            logger.warning('event=dream_lever_error lever=history_compact exc=%s', type(error).__name__)

    async def invoke(lane, mount, messages):
        for attempt in range(CAPACITY_CALL_RETRIES + 1):
            try:
                return await invoke_once(lane, mount, messages)
            except dream_harness_transport.CapacityWait as exc:
                if not exc.retryable or attempt == CAPACITY_CALL_RETRIES:
                    raise
                await active()
                mode, allowlisted = admission_for(uid)
                waited_from = asyncio.get_running_loop().time()
                try:
                    admitted = await dream_capacity.wait_for_capacity(
                        deadline,
                        CAPACITY_RETRY_HEADROOM_SECONDS,
                        mode=mode,
                        owner_allowlisted=allowlisted,
                    )
                finally:
                    waited = int(1000 * (asyncio.get_running_loop().time() - waited_from))
                    timing['waits'] += 1
                    timing['wait_ms'] += waited
                    timing['wait_gateway_ms'] += waited
                if not admitted:
                    raise
                logger.info('Dream capacity retry lane=%s attempt=%d', lane, attempt + 1)
                # invoke_once rechecks the kill switch/lease and reserves this attempt.
                # The shaped loop retains history, tool results and staged proposals.

    async def invoke_once(lane, mount, messages):
        nonlocal budget_notice_sent, stage
        await active()
        if lane == dream_harness_transport.MAIN_LANE and compact_arm != 'off':
            compact(messages)
        stage = 'request_sizing'
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
        # Hold uncached input plus output burndown: the previous turn's cache hit
        # cannot guarantee this call's hit. Settlement refunds reported cache savings.
        reserve = minute_burndown_tokens(
            'gemini',
            'gemini-3.8-flash',
            weighted_tokens=price_weighted_tokens(
                'gemini',
                'gemini-3.8-flash',
                prompt_tokens=estimate,
                cached_tokens=0,
                completion_tokens=completion_room,
            ),
            completion_tokens=completion_room,
            prompt_tokens=estimate,
        )
        micro, price_status = conservative_attempt_micro('gemini', 'gemini-3.8-flash', estimate, completion_room)
        if lease is not None:
            stage = 'turn_reserve'
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
                    timing['waits'] += 1
                    timing['wait_ms'] += 1000 * pause
                    timing['wait_headroom_ms'] += 1000 * pause
                    await asyncio.sleep(pause)
                    await active()
        stage = 'model_turn'
        sink = {}
        counted = False
        turn_started = asyncio.get_running_loop().time()
        try:
            if turn is not None:
                result = await turn(uid, lane, mount, messages)
                report['model_lanes'].append(lane)
                await usage(result)
                if lane == dream_harness_transport.MAIN_LANE and result.prompt_tokens:
                    remember_main(result, messages)
                    main_history['cached_tokens'] = (
                        result.cached_tokens
                        if result.cached_tokens is not None and getattr(result, 'cache_unreported_tokens', 0) == 0
                        else None
                    )
                stage = 'tools' if lane == dream_harness_transport.MAIN_LANE else 'verify'
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
            report['model_lanes'].append(lane)
            counted = True
            if lane == dream_harness_transport.MAIN_LANE and result.prompt_tokens:
                remember_main(result, messages)
                main_history['cached_tokens'] = (
                    result.cached_tokens
                    if result.cached_tokens is not None and result.cache_unreported_tokens == 0
                    else None
                )
            stage = 'tools' if lane == dream_harness_transport.MAIN_LANE else 'verify'
            return result
        finally:
            # A call counts as a model turn once its transport completed, even if the
            # payload then fails to parse; zero-cost capacity retries never complete.
            if not counted and turn is None and sink.get('transport_complete'):
                report['model_lanes'].append(lane)
            if lane == dream_harness_transport.VERIFY_LANE and sink.get('transport_complete'):
                report['verifier_transport_responses'] = report.get('verifier_transport_responses', 0) + 1
            report['usage_unknown'] |= sink.get('usage_unknown', False)
            timing['model_ms'] += int(1000 * (asyncio.get_running_loop().time() - turn_started))

    async def effect(fn, *args, **kwargs):
        await active()
        if dry_run:
            return 'dry_run'
        return await run_blocking(db_executor, partial(fn, uid, *args, **kwargs))

    gate_retry_deadline = None
    gate_retry_sleeping = False

    async def effect_with_gate_retry(fn, *args, **kwargs):
        nonlocal gate_retry_deadline, gate_retry_sleeping
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
                return result
            except Exception as exc:
                if not _retryable_gate_contention(exc):
                    raise
                now = loop.time()
                if gate_retry_deadline is None:
                    gate_retry_deadline = min(deadline, now + GATE_CONTENTION_RETRY_BUDGET_SECONDS)
                retry_allowed = await run_blocking(db_executor, legal_holds.dream_gate_contention_retry_allowed, uid)
                if not retry_allowed:
                    raise
                now = loop.time()
                if delay_index >= len(GATE_CONTENTION_BACKOFF_SECONDS):
                    raise ValueError('dream_gate_contention') from exc
                delay = GATE_CONTENTION_BACKOFF_SECONDS[delay_index]
                delay_index += 1
                retry_deadline = min(deadline, gate_retry_deadline)
                if now + delay + GATE_CONTENTION_APPLY_HEADROOM_SECONDS >= retry_deadline:
                    raise ValueError('dream_gate_contention') from exc
                gate_retry_sleeping = True
                try:
                    await _sleep_gate_retry(delay)
                except (asyncio.CancelledError, TimeoutError):
                    # A pass timeout during the sleep leaves no apply in flight; keep the flag for the outer rewrite.
                    raise
                except BaseException:
                    gate_retry_sleeping = False
                    raise
                gate_retry_sleeping = False
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
                    if result.reason == 'finished' and session.finish is None and progress['fired'] is not None:
                        report['stop_reason'] = 'no_progress'
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
                stage = 'verify'
                verify_started = asyncio.get_running_loop().time()
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
                timing['verify_ms'] += int(1000 * (asyncio.get_running_loop().time() - verify_started))
            report['verifier_calls'] = calls
            report['verifier_transport_responses'] = max(
                report.get('verifier_transport_responses', 0), verification_telemetry.get('transport_responses', 0)
            )
            report['verifier_valid_responses'] = sum(
                isinstance(vote, bool) for votes in support.values() for vote in votes
            )
            decisions = Counter()
            stage = 'demotion_check'
            demoted = await run_blocking(db_executor, dream_store.demoted_types, uid, caps)
            automatic = auto_apply_kinds(uid) - demoted
            offered = []
            if not dry_run and lease is None:
                raise ValueError('dream_lease_required')
            effect_scope = ACTIVE_RUN.set((uid, lease['run_id']) if lease else None)
            token = dream_writing.set(True)
            stage = 'effects'
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
                    if item.kind == 'resolve_required_memory' and (decision != 'agree' or not auto_allowed):
                        # A split never spills hidden submissions into Review.
                        report['outcomes'].append({'key': item.key, 'kind': item.kind, 'status': 'intake_deferred'})
                    elif decision == 'disagree' or (decision == 'unverified' and default_policy):
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
        if isinstance(exc, TimeoutError) and gate_retry_sleeping:
            exc = ValueError('dream_gate_contention')
        code = error_code(exc)
        report.update(status='failed', error_type=type(exc).__name__, error_code=code)
        if code == 'dream_gate_contention':
            report['stop_reason'] = code
        if isinstance(exc, dream_harness_transport.CapacityWait) or str(exc) == 'dream_minute_headroom':
            report.update(
                status='waiting',
                reason='reserved_capacity',
                wait_cause='minute_headroom' if str(exc) == 'dream_minute_headroom' else 'gateway',
            )
        else:
            _log_pass_failure(exc, stage=stage)
    report['accounted_tokens'] += session.counters['search_embedding_token_upper_bound']
    report['price_weighted_tokens'] += session.counters['search_embedding_token_upper_bound']
    try:
        if stop_arm != 'off':
            fired = progress['fired']
            levers['no_progress_stop'] = {'arm': stop_arm, 'fired': fired is not None}
            if fired is not None:
                late = {key for key in session.staged if key not in fired['keys']}
                levers['no_progress_stop'].update(
                    batch=fired['batch'],
                    staged_after=len(late),
                    applied_after=sum(
                        1 for row in report['outcomes'] if row.get('key') in late and row.get('status') == 'applied'
                    ),
                    tokens_after=max(0, report['price_weighted_tokens'] - fired['tokens']),
                )
        if budget_probe:
            levers['material_budget'] = cap_tail(session.staged, progress['capped'], report['outcomes'])
        if compact_arm != 'off':
            levers['history_compact'] = dict(compaction)
    except Exception as error:
        logger.warning('event=dream_lever_error lever=report exc=%s', type(error).__name__)
    report.update(timing=timing, levers=levers, defect_reports=dict(defects))
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
    if await run_blocking(db_executor, account_deletion_blocks_user_work, uid):
        report = {'status': 'not_admitted', 'reason': 'account_pending_deletion'}
        if not dry_run:
            record_pass(report)
        return report
    if generated_compute_configured() and not await run_blocking(
        db_executor, generated_compute_allowed, uid, 'dream', allow_byok=False
    ):
        return {'status': 'not_admitted', 'reason': 'usage_budget_exhausted'}
    if not enabled():
        report = {'status': 'not_admitted', 'reason': 'disabled'}
        if not dry_run:
            record_pass(report)
        return report
    caps = caps or Caps.from_env()
    if bootstrap_tools is not None and not canary:
        raise ValueError('dream_bootstrap_requires_synthetic_canary')
    await warm_rollout_cohorts(uid)
    # Reject stale queue entries before capacity waits or owner-data loading.
    # Synthetic canaries have separate, authoritative admission in acquire().
    try:
        owner_eligible = canary or may_be_eligible(uid)
    except RolloutCohortUnavailable:
        # Keep the due row: an unreadable cohort is retryable, not a revocation.
        from utils.observability.fallback import record_fallback

        logger.error('event=dream_admission outcome=waiting reason=eligibility_unavailable')
        record_fallback(
            component='agent_tools',
            from_mode='dream_admission',
            to_mode='retry_eligibility',
            reason='unavailable',
            outcome='degraded',
            log=logger,
        )
        report = {'status': 'waiting', 'reason': 'eligibility_unavailable'}
        record_pass(report)
        return report
    if not owner_eligible:
        report = {'status': 'not_admitted', 'reason': 'ineligible'}
        record_pass(report)
        if not dry_run:
            await run_blocking(db_executor, dream_scheduler.remove_due, uid)
        return report
    pass_started = asyncio.get_running_loop().time()
    arms = {} if canary else dream_levers.arms(uid)
    backlog = _backlog_owed(uid)
    idle_arm = arms.get('idle_skip', 'off')
    skip_idle = idle_arm == 'serve' and trigger == 'schedule' and not canary and not dry_run and not backlog
    if skip_idle:
        # Before any capacity slot or seed read: an owner with nothing new is parked
        # until mark_dirty re-enqueues it. Any error falls through to today's pass.
        try:
            parked = await run_blocking(db_executor, dream_store.park_if_idle, uid)
        except Exception as error:
            logger.warning('event=dream_lever_error lever=idle_skip exc=%s', type(error).__name__)
            parked = False
        if parked:
            report = {
                'status': 'not_admitted',
                'reason': 'idle_no_material',
                'trigger': trigger,
                'levers': {'idle_skip': {'arm': idle_arm, 'skipped': True}},
            }
            record_pass(report)
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
        report = {'status': 'waiting', 'reason': 'reserved_capacity', 'wait_cause': 'gateway'}
        record_pass(report)
        return report
    lease = None
    release_slot = False
    pass_levers: dict[str, dict[str, Any]] = {}
    try:
        seed_started = asyncio.get_running_loop().time()
        seed, records, dirty, limits = await run_blocking(db_executor, dream_seed.load, uid, caps)
        seed_ms = int(1000 * (asyncio.get_running_loop().time() - seed_started))
        limits = replace(
            limits,
            completion_tokens=caps.completion_tokens,
            verifier_completion_tokens=min(limits.verifier_completion_tokens, caps.verifier_completion_tokens),
        )
        caps = replace(caps, tokens=limits.tokens)
        if not dry_run:
            reclaimed = {}
            denied: dict[str, Any] = {}
            try:
                lease = await run_blocking(
                    db_executor,
                    dream_store.acquire,
                    uid,
                    caps,
                    trigger=trigger,
                    canary=canary,
                    reclaim_sink=reclaimed,
                    denial_sink=denied,
                    skip_idle=skip_idle,
                )
            finally:
                if reclaimed:
                    record_reclaimed(**reclaimed)
            if lease is None:
                release_slot = True
                report = {'status': 'not_admitted', 'reason': denied.get('reason', 'unknown')}
                record_pass(report)
                return report
            if idle_arm != 'off':
                pass_levers['idle_skip'] = {
                    'arm': idle_arm,
                    'would_skip': bool(lease.get('hunt')) and trigger == 'schedule' and not backlog,
                }
            backoff_arm = arms.get('hunt_backoff', 'off')
            if backoff_arm != 'off' and lease.get('hunt'):
                pass_levers['hunt_backoff'] = {
                    'arm': backoff_arm,
                    'dry_hunts': int(lease.get('dry_hunts', 0) or 0),
                    'would_defer': bool(lease.get('backoff_would_defer')) and trigger == 'schedule',
                }
        if not dry_run and not canary:
            assert lease is not None
            intake_scope = ACTIVE_RUN.set((uid, lease['run_id']))
            try:
                seed, records = await dream_required_intake.prepare(uid, seed, records, limits, OwnerSearch(uid))
            finally:
                ACTIVE_RUN.reset(intake_scope)
        material = len(dirty) + len(seed.get('required_intake_candidates') or [])
        prescan_arm = arms.get('prescan', 'off')
        prescan = None
        if prescan_arm != 'off' and trigger == 'schedule' and lease is not None:
            # Pre-scan after admission only: bounded projected reads hand hunts
            # concrete targets. Any failure leaves the pass exactly as today.
            try:
                prescan = await asyncio.wait_for(run_blocking(db_executor, dream_prescan.scan, uid), timeout=5.0)
                pass_levers['prescan'] = {'arm': prescan_arm, 'targets': len(prescan['refs']), **prescan['counts']}
                # Serve only hunts: a pass admitted for dirty work keeps its targets first, and an
                # owner parked as an empty-bucket idle pass is never woken into a model session.
                served = 0
                if prescan_arm == 'serve' and lease.get('hunt') and limits.bucket != 'empty':
                    served = dream_prescan.serve_targets(seed, prescan['refs'], limits)
                pass_levers['prescan']['served'] = served
            except Exception as error:
                logger.warning('event=dream_lever_error lever=prescan exc=%s', type(error).__name__)
                prescan = None
        budget_arm = arms.get('material_budget', 'off')
        budget_probe = None
        if budget_arm != 'off':
            try:
                sized = material_tokens(material, limits.tokens)
                pass_levers['material_budget'] = {
                    'arm': budget_arm,
                    'tokens_before': limits.tokens,
                    'tokens_after': sized,
                }
                if budget_arm == 'shadow' and sized < limits.tokens:
                    budget_probe = sized
                if budget_arm == 'serve' and sized < limits.tokens:
                    limits = replace(limits, tokens=sized)
                    caps = replace(caps, tokens=limits.tokens)
            except Exception as error:
                logger.warning('event=dream_lever_error lever=material_budget exc=%s', type(error).__name__)
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
                arms=arms,
                budget_probe=budget_probe,
            )
        if 'prescan' in pass_levers:
            # Recall of the finalized report, merged into the admission-time row
            # like the material-budget tail merge.
            try:
                pass_levers['prescan']['hits'] = dream_prescan.applied_hits(report, (prescan or {}).get('refs'))
            except Exception as error:
                logger.warning('event=dream_lever_error lever=prescan exc=%s', type(error).__name__)
        session_levers = report.get('levers') or {}
        report['levers'] = {
            **pass_levers,
            **session_levers,
            # Merge the session's B5 tail counts into the admission-time sizing row.
            **(
                {'material_budget': {**pass_levers['material_budget'], **session_levers['material_budget']}}
                if 'material_budget' in pass_levers and 'material_budget' in session_levers
                else {}
            ),
        }
        report['material'] = material
        report.setdefault('timing', {})['seed_ms'] = seed_ms
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
                park_when_idle=skip_idle,
            )
        if report.get('reason') == 'idle':
            report.pop('run_id', None)
        report['timing']['total_ms'] = int(1000 * (asyncio.get_running_loop().time() - pass_started))
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


RESERVED_RECHECK_SECONDS = 30
# A previous replica can leave a full discovery lease after an inconclusive
# probe or shutdown. Wait for its expiry, one bounded probe, and a final read.
RESERVED_RECHECKS = (PROBE_SECONDS + PROBE_TIMEOUT_SECONDS) // RESERVED_RECHECK_SECONDS + 1
# A pass starting late in the drain gets only the drain's remaining budget, so
# it ends through its own deadline (and finish) instead of being cancelled by the
# drain's outer timeout; below this floor the owner waits for the next sweep.
# 10-29: passes started with under 5 minutes left made 20 edits in 116 passes (most of
# that window is gateway wait), so an owner waits for the next half-hour sweep instead.
MIN_PASS_SECONDS = 600


async def drain(*, limit=5000, sweep=None):
    """Run due owners until the drain budget ends; ``sweep`` (optional) receives sweep telemetry.

    A capacity wait retries the same owner, so ``results`` holds attempts;
    ``sweep['finals']`` holds each reached owner's last attempt for owner-level counts.
    """
    sweep = {} if sweep is None else sweep
    if limit <= 0:
        return []
    sweep.setdefault('sweep_id', str(uuid.uuid4()))
    sweep_token = dream_telemetry.SWEEP_ID.set(sweep['sweep_id'])
    sweep_started = time.monotonic()
    results = []
    finals = sweep.setdefault('finals', [])
    reached = {'owners': 0}
    drain_deadline = time.monotonic() + DRAIN_TIMEOUT_SECONDS
    try:
        async with asyncio.timeout(DRAIN_TIMEOUT_SECONDS):
            # Required intake has its own Flex route and no Dream capacity or
            # paid-cohort dependency. Discover owed owners before model waits.
            await retry_sweep(limit=min(limit, 4990), complete_owner=complete_receipted_required_intake)
            if not enabled():
                return results
            reserved_open = await dream_capacity.available_model(mode='reserved') is not None
            if not reserved_open and not on_demand_enabled():
                # The first check can only start the probe that refreshes stale evidence; recheck
                # before giving up the hourly sweep.
                for _ in range(RESERVED_RECHECKS):
                    await asyncio.sleep(RESERVED_RECHECK_SECONDS)
                    if not enabled():
                        return results
                    if await dream_capacity.available_model(mode='reserved') is not None:
                        reserved_open = True
                        break
            if not reserved_open and not on_demand_enabled():
                sweep['capacity_closed'] = True
                report = {'status': 'waiting', 'reason': 'reserved_capacity'}
                record_pass(report)
                return [report]
            rows = await run_blocking(db_executor, dream_scheduler.candidates, limit=min(limit, 5000), with_due=True)
            rows = [row if isinstance(row, tuple) else (row, None) for row in rows]
            page = [uid for uid, _ in rows]
            sweep['due_owners'] = len(page)
            page = await _payoff_order(rows, page, sweep)
            owners = iter(page)

            async def worker():
                for uid in owners:
                    last = None
                    while enabled():
                        remaining = drain_deadline - time.monotonic() - FINISH_MARGIN_SECONDS
                        if remaining < MIN_PASS_SECONDS:
                            # Too little drain budget left for a useful pass; the owner stays
                            # due and runs with a full window next sweep.
                            if last is not None:
                                finals.append(last)
                            return
                        if last is None:
                            reached['owners'] += 1
                        try:
                            report = await run_pass(uid, timeout_seconds=int(min(PASS_TIMEOUT_SECONDS, remaining)))
                        except Exception as exc:
                            _log_pass_failure(exc, stage='pass')
                            report = {
                                'status': 'failed',
                                'error_type': type(exc).__name__,
                                'error_code': error_code(exc),
                            }
                            record_pass(report)
                        results.append(report)
                        last = report
                        if report['status'] != 'waiting':
                            break
                        await asyncio.sleep(dream_capacity.COOLDOWN_SECONDS)
                    if last is not None:
                        finals.append(last)

            async with asyncio.TaskGroup() as group:
                for _ in range(concurrency()):
                    group.create_task(worker())
    except TimeoutError:
        sweep['deadline'] = True
        results.append({'status': 'deadline'})
    finally:
        dream_telemetry.SWEEP_ID.reset(sweep_token)
        sweep['owners_started'] = reached['owners']
        sweep['owners_unreached'] = max(0, int(sweep.get('due_owners', 0)) - reached['owners'])
        # Owners whose pass the drain deadline cancelled have no final report.
        sweep['owners_inflight'] = max(0, reached['owners'] - len(finals))
        sweep['duration_ms'] = int(1000 * (time.monotonic() - sweep_started))
    return results


async def _payoff_order(rows, page, sweep):
    """Lever B2: shadow logs how far payoff ranking would move owners; serve uses it. Fails open."""
    arm = dream_levers.arm(dream_levers.PAYOFF_ORDER_MODE_ENV, None)
    sweep['payoff_order'] = arm
    if arm == 'off' or len(page) < 2:
        return page
    try:
        ranked = await run_blocking(db_executor, dream_scheduler.payoff_order, rows, datetime.now(timezone.utc))
        sweep['reordered'] = sum(1 for before, after in zip(page, ranked) if before != after)
        return ranked if arm == 'serve' and sorted(ranked) == sorted(page) else page
    except Exception as error:
        logger.warning('event=dream_lever_error lever=payoff_order exc=%s', type(error).__name__)
        return page
