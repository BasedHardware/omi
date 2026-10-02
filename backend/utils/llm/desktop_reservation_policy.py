"""Desktop reservation admission; classify protocol shape, never prompt content."""

import json
import logging
import os
import re
from collections.abc import Mapping, Callable, Awaitable

from fastapi import Response

from prometheus_client import Counter

from config.vertex_reservations import State, policy, RESERVATIONS, ENFORCEMENT_ENV
from utils.llm.vertex_reservation_state import effective_states
from utils.llm.desktop_gemini_gateway import _sanitize  # pyright: ignore[reportPrivateUsage]

logger = logging.getLogger(__name__)
POLICY_ACTIONS = Counter(
    'omi_vertex_reservation_policy_total', 'Reservation policy decisions', ['model', 'state', 'lane', 'action']
)
TASK_TOOLS = frozenset({'search_similar', 'search_keywords', 'no_task_found', 'extract_task', 'reject_task'})

# Source-audited release tags before screen_task_jev_gate. Unknown/unaudited
# builds, including every capable current build, are deliberately served.
LEGACY_MACOS_BUILDS = {'12425': '0.12.425', '12432': '0.12.432', '12433': '0.12.433', '12434': '0.12.434'}
_MACOS_AGENT = re.compile(r'(?:Omi|Omi%20Beta)/(\d+) CFNetwork/[\d.]+ Darwin/[\d.]+')


def identified_legacy_macos(headers: Mapping[str, str]) -> bool:
    platform = headers.get('x-app-platform', '').lower()
    if platform and platform != 'macos':
        return False
    agent = headers.get('user-agent', '')
    match = _MACOS_AGENT.fullmatch(agent) if len(agent) <= 256 else None
    agent_build = match.group(1) if match else ''
    build = headers.get('x-app-build', '')
    version = headers.get('x-app-version', '')
    if build:
        # Explicit version headers must identify the platform and agree with
        # the UA when both are present. Never let a stale hint mask a new build.
        if platform != 'macos' or LEGACY_MACOS_BUILDS.get(build) != version:
            return False
        if agent_build and agent_build != build:
            return False
        return True
    return agent_build in LEGACY_MACOS_BUILDS and (not version or version == LEGACY_MACOS_BUILDS[agent_build])


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
        if identified_legacy_macos(headers) and (
            headers.get('x-omi-workload', '') == 'extraction' or tagged == 'task_extraction'
        ):
            return 'macos_legacy_tasks'
        return 'desktop_other'
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


async def should_refuse(
    model: str,
    action: str,
    body: bytes,
    headers: Mapping[str, str],
    *,
    byok: bool,
    refresh: Callable[[], Awaitable[dict[str, State]]],
) -> bool:
    if byok or model not in RESERVATIONS or action not in {'generateContent', 'streamGenerateContent'}:
        return False
    payload = json.loads(_sanitize(body, action))
    states = effective_states(await refresh(), os.environ, admission=True)
    lane = desktop_lane(headers, payload)
    return admission(model, states.get(model, State.UNKNOWN), lane, os.getenv(ENFORCEMENT_ENV, 'enforce')) == 'refuse'


def refusal_response(*, streaming: bool, headers: Mapping[str, str]) -> Response:
    return Response(
        refusal_body(streaming=streaming),
        media_type='text/event-stream' if streaming else 'application/json',
        headers={
            **headers,
            'X-Omi-Reservation-State': 'inactive',
            'X-Omi-Error-Class': 'legacy_task_reservation_inactive',
        },
    )
