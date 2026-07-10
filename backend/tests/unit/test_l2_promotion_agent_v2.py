import pytest

from database import memory_ledger
from utils.memory.l2_promotion_agent import PromotionAgentConfig, run_l2_promotion_agent
from utils.memory.memory_tools import MemoryToolContext
from utils.memory.promotion_bundle_builder import (
    UngroundedPromotionError,
    build_promotion_bundle,
    enforce_grounded_promotion_bundle,
)


class FakeResponse:
    def __init__(self, tool_calls=None, content='done'):
        self.tool_calls = tool_calls or []
        self.content = content


class ScriptedLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.bound_tools = None
        self.messages = []

    def bind_tools(self, tools):
        self.bound_tools = tools
        return self

    def invoke(self, messages):
        self.messages.append(messages)
        if self.responses:
            return self.responses.pop(0)
        return FakeResponse([])


def _bundle():
    return {
        'schema_version': 'promotion_bundle.v1',
        'bundle_id': 'pbn_test',
        'uid': 'u1',
        'session_ids': ['s1'],
        'observed_head_commit_id': 'head_0',
        'l1_items': [
            {
                'id': 'l1_1',
                'session_id': 's1',
                'content': 'User uses Warp daily.',
                'evidence_ids': ['ev_1'],
                'subject_entity_id': 'ent_user',
            }
        ],
        'evidence_packets': [
            {
                'packet_id': 'pkt_1',
                'evidence_ids': ['ev_1'],
                'observations': [{'id': 'l1_1', 'evidence_ids': ['ev_1']}],
            }
        ],
        'vector_seed': [
            {
                'memory_id': 'mem_existing',
                'content': 'User uses terminal tools.',
                'subject_entity_id': 'ent_user',
                'predicate': 'uses_tool',
            }
        ],
        'graph_snapshot': {
            'edges': [
                {
                    'fact_id': 'mem_existing',
                    'subject_entity_id': 'ent_user',
                    'predicate': 'uses_tool',
                    'object': 'terminal tools',
                    'content': 'User uses terminal tools.',
                }
            ]
        },
    }


def _context(state, commits):
    def append_commit(uid, parent_commit_id, mutations, *, run_id=None, use_current_head=False, **kwargs):
        return memory_ledger.append_commit_to_history(
            state,
            commits,
            parent_commit_id,
            mutations,
            run_id=run_id,
            use_current_head=use_current_head,
        )

    return MemoryToolContext(
        uid='u1',
        allowed_evidence_ids={'ev_1'},
        existing_facts={'mem_existing': {'id': 'mem_existing', 'subject_entity_id': 'ent_user'}},
        append_commit=append_commit,
        read_head=lambda uid: state.get('current_head_commit_id'),
        route_persister=lambda uid, patch, **kwargs: {'route': patch.decision.value},
    )


def test_agentic_loop_exercises_read_tools_and_write_memory_commit():
    state = {'current_head_commit_id': 'head_0'}
    commits = {}
    llm = ScriptedLLM(
        [
            FakeResponse(
                [
                    {'name': 'list_session_l1', 'args': {'session_id': 's1'}},
                    {'name': 'vector_search', 'args': {'query': 'Warp terminal', 'k': 3}},
                    {'name': 'graph_walk', 'args': {'entity': 'ent_user', 'hops': 1}},
                    {'name': 'fetch_fact', 'args': {'fact_id': 'mem_existing'}},
                    {
                        'name': 'write_memory',
                        'args': {
                            'decision': 'add',
                            'result_status': 'active',
                            'memory_text': 'User uses Warp daily.',
                            'predicate': 'uses_tool',
                            'subject_entity_id': 'ent_user',
                            'arguments': {'object': 'Warp'},
                            'evidence_ids': ['ev_1'],
                            'rationale': 'direct L1 evidence and graph search completed',
                            'relationship_to_user': 'self',
                            'aboutness': 'primary_user',
                        },
                    },
                    {'name': 'finish', 'args': {'reason': 'done'}},
                ]
            )
        ]
    )

    trace = run_l2_promotion_agent(
        bundle=_bundle(),
        llm=llm,
        memory_context=_context(state, commits),
        config=PromotionAgentConfig(max_tool_calls=10),
    )

    tool_names = [call['name'] for call in trace['tool_calls']]
    assert {'list_session_l1', 'vector_search', 'graph_walk', 'fetch_fact', 'write_memory', 'finish'} <= set(tool_names)
    assert trace['commit_ids']
    assert len(commits) == 1
    assert trace['results'][0]['commit_id'] == trace['commit_ids'][0]
    assert llm.bound_tools


def test_zero_tool_call_llm_writes_nothing():
    state = {'current_head_commit_id': 'head_0'}
    commits = {}
    llm = ScriptedLLM([FakeResponse([], content='I will not call tools.')])

    trace = run_l2_promotion_agent(bundle=_bundle(), llm=llm, memory_context=_context(state, commits))

    assert trace['tool_calls'] == []
    assert trace['commit_ids'] == []
    assert commits == {}


def test_agent_safety_guard_blocks_repeated_tool_loop():
    state = {'current_head_commit_id': 'head_0'}
    commits = {}
    repeated = [{'name': 'vector_search', 'args': {'query': 'Warp', 'k': 3}}]
    llm = ScriptedLLM([FakeResponse(repeated), FakeResponse(repeated), FakeResponse(repeated), FakeResponse(repeated)])

    trace = run_l2_promotion_agent(
        bundle=_bundle(),
        llm=llm,
        memory_context=_context(state, commits),
        config=PromotionAgentConfig(max_tool_calls=10),
    )

    assert trace['status'] == 'blocked'
    assert any(error['error_type'] == 'SafetyGuardError' for error in trace['errors'])
    assert commits == {}


def test_bundle_grounding_nonempty_and_unguarded_empty_head_fails():
    durable = [
        {
            'id': 'mem_existing',
            'content': 'User uses terminal tools.',
            'status': 'active',
            'subject_entity_id': 'ent_user',
            'predicate': 'uses_tool',
            'arguments': {'object': 'terminal tools'},
        }
    ]
    bundle = build_promotion_bundle(
        uid='u1',
        session_ids=['s1'],
        l1_items=_bundle()['l1_items'],
        durable_facts=durable,
        head_reader=lambda uid: 'head_0',
    ).to_dict()

    assert bundle['vector_seed'] or bundle['graph_snapshot']['edges']
    assert enforce_grounded_promotion_bundle(bundle)['ok'] is True

    empty = dict(bundle)
    empty['vector_seed'] = []
    empty['graph_snapshot'] = {'edges': []}
    with pytest.raises(UngroundedPromotionError):
        enforce_grounded_promotion_bundle(empty)
    prod = enforce_grounded_promotion_bundle(empty, environment='prod')
    assert prod['error'] == 'ungrounded_promotion'
