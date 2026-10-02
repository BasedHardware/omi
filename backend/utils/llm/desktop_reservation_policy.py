"""Desktop reservation admission; classify protocol shape, never prompt content."""

import json
import logging
from collections.abc import Mapping

from prometheus_client import Counter

from config.vertex_reservations import State, policy

logger = logging.getLogger(__name__)
POLICY_ACTIONS = Counter(
    'omi_vertex_reservation_policy_total', 'Reservation policy decisions', ['model', 'state', 'lane', 'action']
)
TASK_TOOLS = frozenset({'search_similar', 'search_keywords', 'no_task_found', 'extract_task', 'reject_task'})


def desktop_lane(headers: Mapping[str, str], payload: object) -> str:
    if not isinstance(payload, dict):
        return 'desktop_other'
    names = set()
    tools = payload.get('tools', [])
    if not isinstance(tools, list):
        return 'desktop_other'
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        declarations = tool.get('functionDeclarations', tool.get('function_declarations', []))
        if isinstance(declarations, list):
            names.update(d.get('name') for d in declarations if isinstance(d, dict) and isinstance(d.get('name'), str))
    platform = headers.get('x-app-platform', '').lower()
    tagged = headers.get('x-omi-lane', '')
    # Shipped Windows has the same tools, but no workload header. Do not infer
    # its feature from a screenshot alone. A future lane tag refines the row.
    if TASK_TOOLS <= names:
        if platform == 'windows' or headers.get('user-agent', '').lower().startswith('omi-windows/'):
            return 'windows_tasks'
        if headers.get('x-omi-workload', '') == 'extraction' or tagged == 'task_extraction':
            return 'macos_legacy_tasks'
        return 'windows_tasks'  # includes unidentified legacy tool clients: preserve service
    tags = {'focus': 'windows_focus', 'dictation': 'macos_dictation', 'suggestions': 'macos_suggestions'}
    return tags.get(tagged, 'desktop_other')


def admission(model: str, state: State, lane: str, mode: str) -> str:
    action = policy(model, state, lane=lane).kind
    if action == 'refuse' and mode.strip().lower() == 'observe':
        action = 'would_refuse'
    POLICY_ACTIONS.labels(
        model if model in {'gemini-2.5-flash', 'gemini-3.8-flash'} else 'other',
        state.value,
        (
            lane
            if lane
            in {
                'macos_legacy_tasks',
                'windows_tasks',
                'windows_focus',
                'macos_dictation',
                'macos_suggestions',
                'desktop_other',
            }
            else 'other'
        ),
        action,
    ).inc()
    logger.info(
        'vertex_reservation_policy model=%s state=%s lane=%s action=%s',
        model if model in {'gemini-2.5-flash', 'gemini-3.8-flash'} else 'other',
        state.value,
        (
            lane
            if lane
            in {
                'macos_legacy_tasks',
                'windows_tasks',
                'windows_focus',
                'macos_dictation',
                'macos_suggestions',
                'desktop_other',
            }
            else 'other'
        ),
        action,
    )
    return action


def refusal_body(*, streaming: bool) -> bytes:
    # The shipped loop terminates on this tool without retries, model fallback,
    # Sentry errors or UI alerts. Headers carry refusal; never invent screen facts.
    payload = {
        'candidates': [
            {
                'content': {
                    'role': 'model',
                    'parts': [
                        {
                            'functionCall': {
                                'name': 'no_task_found',
                                'args': {'context_summary': '', 'current_activity': ''},
                            }
                        }
                    ],
                },
                'finishReason': 'STOP',
            }
        ]
    }
    raw = json.dumps(payload, separators=(',', ':'))
    return (f'data: {raw}\n\n' if streaming else raw).encode()
