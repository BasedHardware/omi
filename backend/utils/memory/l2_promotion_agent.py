from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from database import memory_ledger
from models.memory_contracts import (
    DurableMemoryPatch,
    DurablePatchDecision,
    LifecycleState,
    deterministic_contract_id,
)
from utils.memory.memory_tools import (
    MemoryToolContext,
    apply_patch_with_memory_tools,
    evidence_ids_from_bundle,
    facts_from_bundle,
)
from utils.retrieval.safety import AgentSafetyGuard, SafetyGuardError

try:
    from utils.llm.durable_memory_patches import PROMOTION_RUBRIC

    _PROMOTION_RUBRIC_IMPORT_ERROR = None
except Exception as exc:
    _PROMOTION_RUBRIC_IMPORT_ERROR = exc
    PROMOTION_RUBRIC = """
- Promote to active when a Future agent/user would benefit from remembering this, it is stable or meaningfully recurring, it is about the primary user, user-owned work, a close relationship, or an entity the user cares about, and it has direct source evidence.
- Use review when attribution, durability, or sensitivity is uncertain but the packet may still be useful.
- Use context_only when the source may help future search/reasoning but should not become durable profile memory.
- Use reject for unsupported, transient, generic, wrong-subject, media/story narration, or conversational activity facts.
- Do not rewrite unidentified non-primary speaker facts as user facts; set relationship_to_user=other_speaker or unclear and choose review/context_only/reject unless the user tie is explicit.
""".strip()

try:
    from utils.llm.clients import get_llm

    _GET_LLM_IMPORT_ERROR = None
except Exception as exc:
    get_llm = None
    _GET_LLM_IMPORT_ERROR = exc


@dataclass(frozen=True)
class PromotionAgentConfig:
    max_tool_calls: int = 15
    max_context_tokens: int = 50000
    max_vector_results: int = 8
    max_graph_hops: int = 2

    def __post_init__(self):
        if self.max_tool_calls < 1:
            raise ValueError('max_tool_calls must be positive')
        if self.max_context_tokens < 1000:
            raise ValueError('max_context_tokens must be at least 1000')
        if self.max_vector_results < 1:
            raise ValueError('max_vector_results must be positive')
        if self.max_graph_hops < 0:
            raise ValueError('max_graph_hops must be non-negative')


@dataclass(frozen=True)
class PromotionTool:
    name: str
    description: str
    args_schema: Dict[str, Any]
    handler: Callable[[Dict[str, Any]], Dict[str, Any]]


@dataclass
class PromotionToolRuntime:
    bundle: Dict[str, Any]
    memory_context: MemoryToolContext
    config: PromotionAgentConfig
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    decisions: List[Dict[str, Any]] = field(default_factory=list)
    results: List[Dict[str, Any]] = field(default_factory=list)

    def record(self, name: str, args: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
        summary = {
            'name': name,
            'args': args,
            'result': _summarize_tool_result(result),
        }
        self.tool_calls.append(summary)
        return result


PROMOTION_AGENT_SYSTEM_PROMPT = f"""
You are Omi Layer 2 durable memory promotion.

Use the tools to reconcile completed-session L1 observations against existing durable memory.
Before any write, search the existing graph or vector seed. Prefer add_evidence or merge over duplicate add.
Choose review over guessing subject, predicate, evidence, or target memory.

PROMOTION RUBRIC:
{PROMOTION_RUBRIC}

DRIFT GUARD: This production prompt, durable_memory_patch.v1, and the write_memory tool are the source of truth for benchmark L2 decisions. Benchmark runners may package evidence and export reports, but must call this product agent for L2 memory decisions.

When done, call finish. Do not write memories unless the evidence ids are present in the bundle.
""".strip()


def _trace_time() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_default(value: Any) -> str:
    return str(value)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), default=_json_default)


def _summarize_tool_result(result: Dict[str, Any]) -> Dict[str, Any]:
    summary = dict(result)
    for key in ('items', 'edges', 'facts', 'l1_items'):
        if isinstance(summary.get(key), list):
            summary[f'{key}_count'] = len(summary[key])
            summary[key] = summary[key][:3]
    return summary


def _tool_call_name(call: Any) -> str:
    if isinstance(call, dict):
        return call.get('name') or call.get('tool') or ''
    return getattr(call, 'name', '') or ''


def _tool_call_args(call: Any) -> Dict[str, Any]:
    if isinstance(call, dict):
        args = call.get('args') if 'args' in call else call.get('input', {})
    else:
        args = getattr(call, 'args', None)
        if args is None:
            args = getattr(call, 'input', {})
    return dict(args or {})


def _response_tool_calls(response: Any) -> List[Any]:
    calls = getattr(response, 'tool_calls', None)
    if calls is not None:
        return list(calls)
    if isinstance(response, dict):
        return list(response.get('tool_calls') or [])
    return []


def _content_from_response(response: Any) -> str:
    content = getattr(response, 'content', response.get('content') if isinstance(response, dict) else '')
    if isinstance(content, list):
        return '\n'.join(str(item) for item in content)
    return str(content or '')


def _bind_tools(llm: Any, tools: List[PromotionTool]) -> Any:
    if hasattr(llm, 'bind_tools'):
        return llm.bind_tools([_tool_schema(tool) for tool in tools])
    return llm


def _invoke_llm(llm: Any, messages: List[Dict[str, Any]]) -> Any:
    if hasattr(llm, 'invoke'):
        return llm.invoke(messages)
    if callable(llm):
        return llm(messages)
    raise RuntimeError('promotion agent llm does not support invoke')


def _tool_schema(tool: PromotionTool) -> Dict[str, Any]:
    return {
        'name': tool.name,
        'description': tool.description,
        'input_schema': tool.args_schema,
    }


def _bundle_prompt(bundle: Dict[str, Any]) -> str:
    compact = {
        'bundle_id': bundle.get('bundle_id'),
        'uid': bundle.get('uid'),
        'session_ids': bundle.get('session_ids') or [],
        'observed_head_commit_id': bundle.get('observed_head_commit_id'),
        'l1_items': bundle.get('l1_items') or [],
        'evidence_packets': bundle.get('evidence_packets') or [],
        'vector_seed_count': len(bundle.get('vector_seed') or []),
        'graph_edge_count': len((bundle.get('graph_snapshot') or {}).get('edges') or []),
    }
    return 'Promotion bundle:\n' + json.dumps(compact, sort_keys=True, default=_json_default)


def _fact_id(item: Dict[str, Any]) -> Optional[str]:
    return item.get('id') or item.get('memory_id') or item.get('fact_id')


def _make_patch_id(payload: Dict[str, Any]) -> str:
    return deterministic_contract_id('l2-promotion-tool-patch', payload)


def _build_tool_patch(bundle: Dict[str, Any], args: Dict[str, Any]) -> DurableMemoryPatch:
    decision = DurablePatchDecision(args.get('decision') or 'review')
    result_status = LifecycleState(
        args.get('result_status') or ('active' if decision == DurablePatchDecision.add else 'review')
    )
    payload = {
        'bundle_id': bundle.get('bundle_id'),
        'decision': decision.value,
        'result_status': result_status.value,
        'target_memory_id': args.get('target_memory_id'),
        'memory_text': args.get('memory_text'),
        'predicate': args.get('predicate'),
        'arguments': args.get('arguments') or {},
        'evidence_ids': sorted(args.get('evidence_ids') or []),
        'subject_entity_id': args.get('subject_entity_id'),
        'rationale': args.get('rationale'),
    }
    patch_id = _make_patch_id(payload)
    new_memory_id = args.get('new_memory_id')
    if decision in {DurablePatchDecision.add, DurablePatchDecision.keep_both}:
        new_memory_id = new_memory_id or 'mem_' + patch_id[:32]
    return DurableMemoryPatch(
        patch_id=patch_id,
        packet_id=args.get('packet_id')
        or (bundle.get('evidence_packets') or [{}])[0].get('packet_id')
        or bundle.get('bundle_id')
        or 'unknown_packet',
        run_id=args.get('run_id') or f"l2_promotion:{bundle.get('bundle_id') or 'unknown'}",
        observed_head_commit_id=bundle.get('observed_head_commit_id'),
        idempotency_key=deterministic_contract_id('l2-promotion-tool-idempotency', payload),
        decision=decision,
        result_status=result_status,
        evidence_ids=list(args.get('evidence_ids') or []),
        evidence_refs=[],
        target_memory_id=args.get('target_memory_id'),
        new_memory_id=new_memory_id,
        memory_text=args.get('memory_text'),
        predicate=args.get('predicate'),
        arguments=dict(args.get('arguments') or {}),
        supersedes=list(args.get('supersedes') or []),
        rationale=args.get('rationale'),
        confidence=args.get('confidence') or 'medium',
        relationship_to_user=args.get('relationship_to_user') or 'unclear',
        subject_entity_id=args.get('subject_entity_id'),
        subject_label=args.get('subject_label'),
        aboutness=args.get('aboutness') or 'unclear',
    )


def build_promotion_tools(runtime: PromotionToolRuntime) -> List[PromotionTool]:
    def vector_search(args: Dict[str, Any]) -> Dict[str, Any]:
        query = str(args.get('query') or '')
        k = min(max(int(args.get('k') or 5), 1), runtime.config.max_vector_results)
        query_terms = {term.lower() for term in query.split() if len(term) > 2}
        scored = []
        for item in runtime.bundle.get('vector_seed') or []:
            content = str(item.get('content') or item.get('memory_text') or '').lower()
            score = sum(1 for term in query_terms if term in content)
            if score or not query_terms:
                scored.append((score, item))
        scored.sort(key=lambda pair: (-pair[0], str(_fact_id(pair[1]) or '')))
        return runtime.record('vector_search', args, {'items': [item for _, item in scored[:k]]})

    def graph_walk(args: Dict[str, Any]) -> Dict[str, Any]:
        entity = str(args.get('entity') or '')
        hops = min(max(int(args.get('hops') or 1), 0), runtime.config.max_graph_hops)
        edges = []
        for edge in (runtime.bundle.get('graph_snapshot') or {}).get('edges') or []:
            if not entity or edge.get('subject_entity_id') == entity or edge.get('object') == entity:
                edges.append(edge)
        return runtime.record('graph_walk', {**args, 'hops': hops}, {'edges': edges})

    def fetch_fact(args: Dict[str, Any]) -> Dict[str, Any]:
        fact_id = str(args.get('fact_id') or '')
        for item in runtime.bundle.get('vector_seed') or []:
            if fact_id == _fact_id(item):
                return runtime.record('fetch_fact', args, {'fact': item})
        for edge in (runtime.bundle.get('graph_snapshot') or {}).get('edges') or []:
            if fact_id in {edge.get('fact_id'), edge.get('memory_id')}:
                return runtime.record('fetch_fact', args, {'fact': edge})
        return runtime.record('fetch_fact', args, {'fact': None})

    def list_session_l1(args: Dict[str, Any]) -> Dict[str, Any]:
        session_id = str(args.get('session_id') or '')
        items = [
            item
            for item in runtime.bundle.get('l1_items') or []
            if not session_id or item.get('session_id') == session_id or item.get('source_id') == session_id
        ]
        return runtime.record('list_session_l1', args, {'l1_items': items})

    def write_memory(args: Dict[str, Any]) -> Dict[str, Any]:
        patch = _build_tool_patch(runtime.bundle, args)
        runtime.decisions.append({'patch': patch.model_dump(mode='json'), 'rationale': patch.rationale})
        try:
            result = apply_patch_with_memory_tools(patch, runtime.memory_context)
            payload = {
                'ok': True,
                'patch_id': result.patch_id,
                'decision': result.decision,
                'commit_id': result.commit_id,
                'applied': result.applied,
                'head_conflict_retry': result.head_conflict_retry,
            }
            runtime.results.append(payload)
            return runtime.record('write_memory', args, payload)
        except Exception as exc:
            payload = {
                'ok': False,
                'error_type': type(exc).__name__,
                'error': str(exc),
            }
            runtime.results.append(payload)
            return runtime.record('write_memory', args, payload)

    def finish(args: Dict[str, Any]) -> Dict[str, Any]:
        return runtime.record('finish', args, {'ok': True, 'reason': args.get('reason') or 'finished'})

    return [
        PromotionTool(
            name='vector_search',
            description='Search seeded durable memories near a query before deciding whether to add, merge, or add evidence.',
            args_schema={'type': 'object', 'properties': {'query': {'type': 'string'}, 'k': {'type': 'integer'}}},
            handler=vector_search,
        ),
        PromotionTool(
            name='graph_walk',
            description='Walk the bounded existing memory graph for an entity.',
            args_schema={'type': 'object', 'properties': {'entity': {'type': 'string'}, 'hops': {'type': 'integer'}}},
            handler=graph_walk,
        ),
        PromotionTool(
            name='fetch_fact',
            description='Fetch a durable fact by memory/fact id from the seeded bundle.',
            args_schema={'type': 'object', 'properties': {'fact_id': {'type': 'string'}}},
            handler=fetch_fact,
        ),
        PromotionTool(
            name='list_session_l1',
            description='List L1 observations for a completed session in this promotion bundle.',
            args_schema={'type': 'object', 'properties': {'session_id': {'type': 'string'}}},
            handler=list_session_l1,
        ),
        PromotionTool(
            name='write_memory',
            description='Validate and append a durable memory patch. Returns commit_id or validation error.',
            args_schema={
                'type': 'object',
                'properties': {
                    'decision': {'type': 'string'},
                    'result_status': {'type': 'string'},
                    'memory_text': {'type': 'string'},
                    'predicate': {'type': 'string'},
                    'subject_entity_id': {'type': 'string'},
                    'arguments': {'type': 'object'},
                    'target_memory_id': {'type': 'string'},
                    'evidence_ids': {'type': 'array', 'items': {'type': 'string'}},
                    'rationale': {'type': 'string'},
                },
            },
            handler=write_memory,
        ),
        PromotionTool(
            name='finish',
            description='Finish the promotion loop after all needed writes/rejections/reviews are complete.',
            args_schema={'type': 'object', 'properties': {'reason': {'type': 'string'}}},
            handler=finish,
        ),
    ]


def _execute_tool(tool: PromotionTool, args: Dict[str, Any], safety_guard: AgentSafetyGuard) -> Dict[str, Any]:
    safety_guard.validate_tool_call(tool.name, args)
    result = tool.handler(args)
    safety_guard.check_context_size(_canonical_json(result))
    return result


def run_l2_promotion_agent(
    *,
    bundle: Dict[str, Any],
    uid: Optional[str] = None,
    llm=None,
    memory_context: Optional[MemoryToolContext] = None,
    config: Optional[PromotionAgentConfig] = None,
) -> Dict[str, Any]:
    cfg = config or PromotionAgentConfig()
    bundle_uid = uid or bundle.get('uid')
    if not bundle_uid:
        raise ValueError('bundle uid is required')
    context = memory_context or MemoryToolContext(
        uid=bundle_uid,
        allowed_evidence_ids=evidence_ids_from_bundle(bundle),
        existing_facts=facts_from_bundle(bundle),
        run_id=f"l2_promotion:{bundle.get('bundle_id') or 'unknown'}",
    )
    runtime = PromotionToolRuntime(bundle=bundle, memory_context=context, config=cfg)
    tools = build_promotion_tools(runtime)
    tool_registry = {tool.name: tool for tool in tools}
    safety_guard = AgentSafetyGuard(max_tool_calls=cfg.max_tool_calls, max_context_tokens=cfg.max_context_tokens)
    model = llm
    if model is None and get_llm is not None:
        model = get_llm('memory_l2')
    if model is None:
        raise RuntimeError('missing promotion agent llm')
    bound_model = _bind_tools(model, tools)
    messages = [
        {'role': 'system', 'content': PROMOTION_AGENT_SYSTEM_PROMPT},
        {'role': 'user', 'content': _bundle_prompt(bundle)},
    ]
    errors: List[Dict[str, Any]] = []
    status = 'success'

    while True:
        response = _invoke_llm(bound_model, messages)
        tool_calls = _response_tool_calls(response)
        if not tool_calls:
            messages.append({'role': 'assistant', 'content': _content_from_response(response)})
            break
        assistant_calls = []
        tool_results = []
        finish_seen = False
        for call in tool_calls:
            name = _tool_call_name(call)
            args = _tool_call_args(call)
            assistant_calls.append({'name': name, 'args': args})
            tool = tool_registry.get(name)
            if tool is None:
                result = {'ok': False, 'error_type': 'UnknownTool', 'error': f'unknown tool: {name}'}
                errors.append({'tool': name, **result})
            else:
                try:
                    result = _execute_tool(tool, args, safety_guard)
                except SafetyGuardError as exc:
                    result = {'ok': False, 'error_type': type(exc).__name__, 'error': str(exc)}
                    errors.append({'tool': name, **result})
                    status = 'blocked'
                    finish_seen = True
                except Exception as exc:
                    result = {'ok': False, 'error_type': type(exc).__name__, 'error': str(exc)}
                    errors.append({'tool': name, **result})
                    status = 'partial'
            tool_results.append({'tool': name, 'result': result})
            if name == 'finish':
                finish_seen = True
        messages.append({'role': 'assistant', 'content': assistant_calls})
        messages.append({'role': 'tool', 'content': tool_results})
        if finish_seen:
            break

    safety_stats = safety_guard.get_stats()
    trace = {
        'schema_version': 'l2_promotion_trace.v1',
        'trace_id': f"trace_{bundle.get('bundle_id') or 'unknown'}",
        'created_at': _trace_time(),
        'uid': bundle_uid,
        'bundle': bundle,
        'tool_calls': runtime.tool_calls,
        'decisions': runtime.decisions,
        'results': runtime.results,
        'commit_ids': [result.get('commit_id') for result in runtime.results if result.get('commit_id')],
        'decision_count': len(runtime.decisions),
        'safety_stats': safety_stats,
        'status': status,
        'errors': errors,
    }
    return trace


def replay_l2_promotion_trace(trace: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'schema_version': 'l2_promotion_trace_replay.v1',
        'trace_id': trace.get('trace_id'),
        'uid': trace.get('uid'),
        'bundle_id': (trace.get('bundle') or {}).get('bundle_id'),
        'decision_count': len(trace.get('decisions') or []),
        'result_count': len(trace.get('results') or []),
        'tool_call_count': len(trace.get('tool_calls') or []),
        'commit_ids': [result.get('commit_id') for result in trace.get('results') or [] if result.get('commit_id')],
        'status': trace.get('status') or 'unknown',
    }
