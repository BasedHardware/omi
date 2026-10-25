"""Agentic meeting notes on the shaped harness: read-only tools, then a terminal submit.

The loop is transport-agnostic (``complete`` performs one provider turn) so the
owner lab can replay it against a snapshot. Production binds the conv-structure
gateway lane through :func:`langchain_complete`.

Budget: :func:`utils.llm.notes_agent_policy.plan_notes_agent` sets turns, tool
calls, an estimated-cost cap and a wall-clock point after which the next turn
must submit. Over-budget lookups are answered with "submit now" and the next
turn is forced to ``submit_notes``. Submissions are normalized from the schema's
declared aliases, then checked; the harness send-back budget returns a submission
once per failure class (format, content, evidence) and anything later is repaired
and accepted.
"""

from __future__ import annotations

import json
import logging
import time
from collections import Counter
from dataclasses import dataclass, field, replace
from typing import Any, Awaitable, Callable, Mapping, Optional, Protocol, Sequence

from prometheus_client import Counter as PromCounter, Histogram
from pydantic import ValidationError

from models.structured_extraction import AgentNotesSubmission
from utils.llm.notes_agent_policy import NotesAgentBudget, estimate_cost_usd
from utils.llm.notes_agent_prompt import INSTRUCTIONS, SUBMIT, TOOL_SCHEMAS, screenshot_message
from utils.llm.notes_output_contract import FORMAT, check_notes, repair_notes, repair_contract, OUTPUT_RULES
from utils.llm.notes_output import NotesOutput, submit_tool
from utils.llm.notes_packet import PACKET_RULES
from utils.llm.notes_identity import NotesIdentity, repair_identity
from utils.llm.notes_output_contract import record_identity_repair
from utils.llm.shaped_agent import (
    Budget,
    LoopStop,
    Mount,
    Problem,
    SendBackBudget,
    Turn,
    normalize_output,
    run_loop,
    validate_output,
)
from utils.model_text import ContextWindow

logger = logging.getLogger(__name__)

FEATURE = 'conversation_notes_agent'
MAX_COMPLETION_TOKENS = 6000
MAX_ARGUMENT_BYTES = 65536
REJECTION_HEADROOM_SECONDS = 30.0
EVIDENCE = 'evidence'
# One send-back per failure class: a format slip cannot spend the evidence retry.
SEND_BACKS = {FORMAT: 1, 'content': 1, EVIDENCE: 1}

RUNS = PromCounter('omi_notes_agent_runs_total', 'Agentic notes runs by how they ended', ['stop'])
DECISIONS = PromCounter('omi_notes_agent_decisions_total', 'Agentic notes eligibility decisions', ['reason'])
TOOL_USE = PromCounter('omi_notes_agent_tool_use_total', 'Agentic notes read-tool calls by tool', ['tool'])
REPAIRS = PromCounter('omi_notes_agent_repairs_total', 'Static repairs and rejections of submissions', ['kind'])
TOKENS = PromCounter('omi_notes_agent_tokens_total', 'Agentic notes tokens', ['kind'])
TOOL_CALLS = Histogram(
    'omi_notes_agent_tool_calls', 'Read-tool calls per agentic notes run', buckets=(0, 1, 2, 3, 5, 8, 12, 15, 20)
)
TURNS = Histogram('omi_notes_agent_turns', 'Model turns per agentic notes run', buckets=(1, 2, 3, 4, 5, 7, 9, 12))
COST = Histogram(
    'omi_notes_agent_estimated_cost_usd',
    'Estimated marginal token cost per agentic notes run',
    buckets=(0.001, 0.002, 0.004, 0.006, 0.008, 0.012, 0.016, 0.02, 0.03, 0.05),
)
CACHE_RATIO = Histogram(
    'omi_notes_agent_cache_hit_ratio',
    'Cached share of input tokens per agentic notes run',
    buckets=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)
LATENCY = Histogram(
    'omi_notes_agent_latency_seconds', 'Agentic notes wall time', buckets=(5, 10, 15, 20, 30, 45, 60, 90, 120, 180)
)


@dataclass
class CompletionTurn:
    """One provider turn, normalized. ``tool_calls`` items are ``{id, name, arguments}``."""

    content: str = ''
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    prompt_tokens: int = 0
    cached_tokens: int = 0
    completion_tokens: int = 0


Complete = Callable[[list[Any], Any], Awaitable[CompletionTurn]]


class Toolbox(Protocol):
    @property
    def names(self) -> frozenset[str]: ...

    async def call(self, name: str, arguments: Mapping[str, Any]) -> Any: ...


@dataclass
class NotesAgentResult:
    submission: Optional[dict[str, Any]]
    stop: str
    turns: int = 0
    tool_calls: int = 0
    prompt_tokens: int = 0
    cached_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    latency_seconds: float = 0.0
    forced: bool = False
    rejections: list[str] = field(default_factory=list)
    repairs: list[str] = field(default_factory=list)
    tools: Counter = field(default_factory=Counter)

    @property
    def cache_ratio(self) -> float:
        return self.cached_tokens / self.prompt_tokens if self.prompt_tokens else 0.0


def notes_agent_mount(
    budget: NotesAgentBudget, owner: Mapping[str, Any], context_window: Optional[ContextWindow] = None
) -> Mount:
    # The run_loop tool cap carries slack: the real lookup cap is enforced per call
    # below, so a submit_notes that shares a turn with lookups is never discarded.
    return Mount(
        instructions=INSTRUCTIONS,
        tools=TOOL_SCHEMAS,
        stable_context=(owner,),
        cache_breakpoint=False,
        feature=FEATURE,
        context_window=context_window,
        budget=Budget(
            turns=budget.max_turns,
            tool_calls=budget.max_tool_calls + 4 * budget.max_turns,
            deadline_seconds=budget.deadline_seconds,
            graceful=True,
        ),
    )


def _force_submit_choice() -> dict[str, Any]:
    return {'type': 'function', 'function': {'name': SUBMIT}}


async def run_notes_agent(
    *,
    owner: Mapping[str, Any],
    seed: Mapping[str, Any],
    complete: Complete,
    toolbox: Toolbox,
    budget: NotesAgentBudget,
    transcript_words: int,
    open_tasks: Sequence[Any] = (),
    owner_names: Sequence[str] = (),
    naming_leads: Sequence[str] = (),
    clock: Callable[[], float] = time.monotonic,
    contract_v2: bool = False,
    transcript_segment_ids: Sequence[str] = (),
    uid: str | None = None,
    identity: NotesIdentity | None = None,
) -> NotesAgentResult:
    started = clock()
    mount = notes_agent_mount(budget, owner, getattr(toolbox, 'window', None))
    from utils.llm.action_item_v2 import instructions_for

    mount = replace(mount, instructions=instructions_for(uid, mount.instructions))
    if contract_v2:
        mount = replace(
            mount,
            instructions=mount.instructions + '\n\n' + PACKET_RULES + '\n\n' + OUTPUT_RULES,
            tools=tuple(tool for tool in mount.tools if tool['function']['name'] != SUBMIT) + (submit_tool(),),
        )
    last_submission: Optional[dict[str, Any]] = None
    last_identity_repaired = False
    send_backs = SendBackBudget(SEND_BACKS)
    result = NotesAgentResult(submission=None, stop='no_submission')
    state: dict[str, Any] = {'last_turn_cost': 0.0, 'force': False}

    def must_submit(index: int) -> bool:
        return bool(
            state['force']
            or index >= budget.max_turns - 1
            or result.tool_calls >= budget.max_tool_calls
            or result.cost_usd + state['last_turn_cost'] >= budget.max_cost_usd
            or clock() - started >= budget.force_submit_after_seconds
        )

    async def model_turn(_shape: Mount, messages: list[Any]) -> Turn:
        forced = must_submit(result.turns)
        result.forced = result.forced or forced
        reply = await complete(messages, _force_submit_choice() if forced else 'required')
        result.turns += 1
        turn_cost = estimate_cost_usd(reply.prompt_tokens, reply.cached_tokens, reply.completion_tokens)
        state['last_turn_cost'] = turn_cost
        result.cost_usd += turn_cost
        result.prompt_tokens += reply.prompt_tokens
        result.cached_tokens += min(reply.cached_tokens, reply.prompt_tokens)
        result.completion_tokens += reply.completion_tokens
        if not reply.tool_calls and not forced:
            # A text-only answer still ends in a submit: ask once, forced.
            state['force'] = True
            reply.tool_calls = []
        assistant = {
            'role': 'assistant',
            'content': reply.content or '',
            'tool_calls': [
                {
                    'id': call['id'],
                    'type': 'function',
                    'function': {'name': call['name'], 'arguments': call.get('arguments') or '{}'},
                }
                for call in reply.tool_calls
            ],
        }
        if not reply.tool_calls:
            assistant.pop('tool_calls')
        return Turn(
            value=reply.content,
            # run_loop stops on an empty tool list; a nudge keeps the loop alive for the forced submit.
            tool_calls=tuple(reply.tool_calls) or (({'id': 'nudge', 'name': '__nudge__'},) if state['force'] else ()),
            messages=(assistant,),
            tokens=reply.prompt_tokens + reply.completion_tokens,
            prompt_tokens=reply.prompt_tokens,
            completion_tokens=reply.completion_tokens,
            cached_tokens=reply.cached_tokens,
        )

    async def execute(calls: tuple[Any, ...]) -> list[Any] | LoopStop:
        nonlocal last_submission, last_identity_repaired
        responses: list[Any] = []
        images: list[Any] = []
        accepted: Optional[dict[str, Any]] = None
        for call in calls:
            name = call.get('name')
            if name == '__nudge__':
                responses.append({'role': 'user', 'content': 'Call submit_notes now with the finished notes.'})
                continue
            raw = call.get('arguments') or '{}'
            try:
                if len(raw.encode()) > MAX_ARGUMENT_BYTES:
                    raise ValueError('arguments too large')
                arguments = json.loads(raw)
                if not isinstance(arguments, dict):
                    raise ValueError('arguments must be an object')
            except (ValueError, TypeError):
                responses.append(_tool_reply(call, {'error': 'arguments were not a JSON object; retry'}))
                continue
            if name == SUBMIT:
                arguments = normalize_output(AgentNotesSubmission, arguments)
                if contract_v2:
                    try:
                        candidate = validate_output(NotesOutput, arguments).model_dump(mode='json')
                        candidate, candidate_repairs = repair_contract(
                            candidate,
                            transcript_words=transcript_words,
                            open_tasks=open_tasks,
                            owner_names=owner_names,
                            transcript_segment_ids=transcript_segment_ids,
                            identity=identity,
                        )
                        # Save only a usable, schema-valid submission; later malformed turns cannot erase it.
                        if candidate.get('sections') and candidate.get('title'):
                            last_submission = candidate
                            last_identity_repaired = 'unsupported_speaker_identity' in candidate_repairs
                    except ValidationError:
                        pass
                sent_back, payload = _review_submission(
                    arguments,
                    transcript_words=transcript_words,
                    lookups_missing=max(0, budget.min_tool_calls - result.tool_calls),
                    naming_leads=naming_leads,
                    contract_v2=contract_v2,
                    identity=identity,
                    send_backs=send_backs,
                    # Only while a further turn still fits the budget.
                    may_reject=result.turns < budget.max_turns
                    and clock() - started < budget.deadline_seconds - REJECTION_HEADROOM_SECONDS,
                )
                if payload is None:
                    verdict = ' '.join(problem.message for problem in sent_back)
                    result.rejections.append(verdict)
                    REPAIRS.labels(kind='rejected').inc()
                    for kind in dict.fromkeys(problem.kind for problem in sent_back):
                        REPAIRS.labels(kind='rejected_' + kind).inc()
                    # A note sent back to investigate keeps its lookups; a format fix resubmits next turn.
                    state['force'] = result.tool_calls >= budget.min_tool_calls and not any(
                        problem.kind == EVIDENCE for problem in sent_back
                    )
                    responses.append(_tool_reply(call, {'status': 'rejected', 'fix': verdict}))
                    continue
                accepted = payload
                responses.append(_tool_reply(call, {'status': 'accepted'}))
                continue
            if name not in toolbox.names:
                responses.append(_tool_reply(call, {'error': f'unknown tool {name}'}))
                continue
            if result.tool_calls >= budget.max_tool_calls:
                state['force'] = True
                responses.append(_tool_reply(call, {'error': 'lookup budget exhausted; call submit_notes now'}))
                continue
            result.tool_calls += 1
            result.tools[name] += 1
            outcome = await toolbox.call(name, arguments)
            responses.append({'role': 'tool', 'tool_call_id': call['id'], 'content': outcome.content})
            image = getattr(outcome, 'image', None)
            if image is not None:
                images.append(screenshot_message(image.frame_id, image.offset_label, image.data_url))
        if accepted is not None:
            return LoopStop(accepted, messages=tuple(responses))
        return responses + images

    try:
        loop = await run_loop(mount, [dict(seed)], model_turn, execute, explicit_cache=False)
        if isinstance(loop.value, dict) and loop.reason == 'finished':
            result.submission = loop.value
            result.stop = 'forced_submit' if result.forced else 'submitted'
        else:
            result.stop = 'deadline' if loop.reason == 'deadline' else 'no_submission'
    except Exception:
        if not contract_v2 or last_submission is None:
            raise
        result.stop = 'malformed'
    finally:
        result.latency_seconds = clock() - started
    if contract_v2 and result.submission is None and last_submission is not None:
        result.submission = last_submission
        result.repairs.append('salvaged_submission')
        if last_identity_repaired:
            result.repairs.append('unsupported_speaker_identity')
        REPAIRS.labels(kind='salvaged_submission').inc()
    if result.submission is not None:
        if contract_v2:
            result.submission, repairs = repair_contract(
                result.submission,
                transcript_words=transcript_words,
                open_tasks=open_tasks,
                owner_names=owner_names,
                transcript_segment_ids=transcript_segment_ids,
                identity=identity,
            )
            result.repairs.extend(repairs)
        result.submission, final_repairs = _final_repairs(result.submission, open_tasks, owner_names)
        result.repairs.extend(final_repairs)
        if identity is not None:
            result.submission, identity_repairs = repair_identity(result.submission, identity)
            result.repairs.extend(identity_repairs)
            for repair in identity_repairs:
                REPAIRS.labels(kind=repair).inc()
        if 'unsupported_speaker_identity' in result.repairs:
            record_identity_repair()
    return result


def _tool_reply(call: Mapping[str, Any], body: Mapping[str, Any]) -> dict[str, Any]:
    return {'role': 'tool', 'tool_call_id': call['id'], 'content': json.dumps(body, ensure_ascii=False)}


def _review_submission(
    arguments: dict[str, Any],
    *,
    transcript_words: int,
    lookups_missing: int,
    may_reject: bool,
    send_backs: SendBackBudget,
    naming_leads: Sequence[str] = (),
    contract_v2: bool = False,
    identity: NotesIdentity | None = None,
) -> tuple[list[Problem], Optional[dict[str, Any]]]:
    """``(problems sent back, None)`` or ``([], accepted payload)``."""
    try:
        validate_output(NotesOutput if contract_v2 else AgentNotesSubmission, arguments)
    except ValidationError as error:
        fields = sorted({'.'.join(map(str, row['loc'])) for row in error.errors(include_input=False)})[:6]
        problem = Problem(FORMAT, 'Schema problems at: ' + ', '.join(fields))
        # An invalid payload cannot be accepted; past the format budget it is returned uncharged.
        return send_backs.review([problem], may_send_back=may_reject) or [problem], None
    check = check_notes(arguments, transcript_words=transcript_words, contract_v2=contract_v2, identity=identity)
    if lookups_missing:
        check.findings.insert(
            0,
            Problem(
                EVIDENCE,
                f'Investigate before submitting: make at least {lookups_missing} more lookups to verify the people, '
                'unnamed speakers and uncertain names (search_people, view_screenshot, get_screen_activity, '
                'get_calendar, search_memories, search_past_meetings), then resubmit the complete notes.',
            ),
        )
    named = [
        person
        for person in arguments.get('participants') or []
        if isinstance(person, dict) and str(person.get('name') or '').strip() and not person.get('is_ai_agent')
    ]
    if naming_leads and not named:
        check.add(
            EVIDENCE,
            'No other speaker is named, but the evidence names possible participants: '
            + ', '.join(naming_leads)
            + '. Check them against the transcript; name the one who spoke in participants (with speaker key and '
            'evidence), the title and the notes, or keep the role description only if none of them fits.',
        )
    sent_back = send_backs.review(check.findings, may_send_back=may_reject)
    if sent_back:
        return sent_back, None
    if check.findings:
        REPAIRS.labels(kind='accepted_with_problems').inc()
    return [], arguments


def _final_repairs(
    submission: dict[str, Any], open_tasks: Sequence[Any], owner_names: Sequence[str]
) -> tuple[dict[str, Any], list[str]]:
    repaired, repairs = repair_notes(submission, open_tasks=open_tasks, owner_names=owner_names)
    for repair in repairs:
        REPAIRS.labels(kind=repair).inc()
    return repaired, repairs


def record_decision(reason: str) -> None:
    DECISIONS.labels(reason=reason).inc()


def record_run(result: NotesAgentResult) -> None:
    RUNS.labels(stop=result.stop).inc()
    TOOL_CALLS.observe(result.tool_calls)
    TURNS.observe(max(1, result.turns))
    COST.observe(result.cost_usd)
    LATENCY.observe(result.latency_seconds)
    if result.prompt_tokens:
        CACHE_RATIO.observe(result.cache_ratio)
    TOKENS.labels(kind='input_cached').inc(result.cached_tokens)
    TOKENS.labels(kind='input_uncached').inc(max(0, result.prompt_tokens - result.cached_tokens))
    TOKENS.labels(kind='output').inc(result.completion_tokens)
    for tool, count in result.tools.items():
        TOOL_USE.labels(tool=tool).inc(count)
    logger.info(
        'conversation_notes_agent_receipt stop=%s turns=%s tool_calls=%s tools=%s prompt_tokens=%s '
        'cached_tokens=%s completion_tokens=%s est_cost_usd=%.5f cache_ratio=%.3f latency_seconds=%.1f '
        'forced=%s rejections=%s repairs=%s',
        result.stop,
        result.turns,
        result.tool_calls,
        ','.join(f'{name}:{count}' for name, count in sorted(result.tools.items())) or 'none',
        result.prompt_tokens,
        result.cached_tokens,
        result.completion_tokens,
        result.cost_usd,
        result.cache_ratio,
        result.latency_seconds,
        result.forced,
        len(result.rejections),
        ','.join(result.repairs) or 'none',
    )


def _usage(response: Any) -> tuple[int, int, int]:
    usage = getattr(response, 'usage_metadata', None) or {}
    prompt = usage.get('input_tokens') or 0
    output = usage.get('output_tokens') or 0
    cached = (usage.get('input_token_details') or {}).get('cache_read') or 0
    return int(prompt), int(cached), int(output)


def langchain_complete(
    model: Any, *, cache_options: Optional[Mapping[str, Any]] = None, cache_key: Optional[str] = None
) -> Complete:
    """One conv-structure gateway turn through the notes model (usage callbacks preserved)."""
    base: dict[str, Any] = {'tools': list(TOOL_SCHEMAS), 'max_completion_tokens': MAX_COMPLETION_TOKENS}
    if cache_options:
        base['extra_body'] = {'prompt_cache_options': dict(cache_options)}
    if cache_key:
        base['prompt_cache_key'] = cache_key

    async def complete(messages: list[Any], tool_choice: Any) -> CompletionTurn:
        response = await model.bind(**base, tool_choice=tool_choice).ainvoke(messages)
        calls = [
            {'id': call.get('id') or f'call_{index}', 'name': call.get('name'), 'arguments': json.dumps(call['args'])}
            for index, call in enumerate(getattr(response, 'tool_calls', None) or [])
        ]
        calls += [
            {'id': call.get('id') or f'bad_{index}', 'name': call.get('name'), 'arguments': call.get('args') or ''}
            for index, call in enumerate(getattr(response, 'invalid_tool_calls', None) or [])
        ]
        content = getattr(response, 'content', '')
        if isinstance(content, list):
            content = ''.join(part.get('text', '') if isinstance(part, dict) else str(part) for part in content)
        prompt, cached, output = _usage(response)
        return CompletionTurn(
            content=str(content or ''),
            tool_calls=calls,
            prompt_tokens=prompt,
            cached_tokens=cached,
            completion_tokens=output,
        )

    return complete
