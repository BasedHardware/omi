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
    'omi_vertex_reservation_policy_total',
    'Reservation policy decisions',
    ['model', 'state', 'lane', 'action', 'build_bucket'],
)
TASK_TOOLS = frozenset({'search_similar', 'search_keywords', 'no_task_found', 'extract_task', 'reject_task'})

# Capability means the released sibling #20374 fix, not merely the flag-off
# pipeline already present in builds 12433/12434. Operators set this at release.
MIN_CAPABLE_BUILD_ENV = 'OMI_VERTEX_LEGACY_TASK_MIN_CAPABLE_MACOS_BUILD'
# v0.7.0 is the first audited five-tool family. Earlier JSON-only decoders
# cannot consume the terminal tool call and are excluded even with copied tools.
MIN_TERMINAL_TOOL_BUILD = 7000
_MACOS_AGENT = re.compile(r'(?:Omi|Omi%20Beta)/([0-9]+) CFNetwork/[0-9.]+ Darwin/[0-9.]+')


def positive_build(raw: str) -> int | None:
    if not re.fullmatch(r'[1-9][0-9]{0,9}', raw):
        return None
    value = int(raw)
    return value if value <= 2_147_483_647 else None


def identified_macos_build(headers: Mapping[str, str]) -> int | None:
    platform = headers.get('x-app-platform', '').lower()
    if 'x-app-platform' in headers and platform != 'macos':
        return None
    agent = headers.get('user-agent', '')
    match = _MACOS_AGENT.fullmatch(agent) if len(agent) <= 256 else None
    agent_build = positive_build(match.group(1)) if match else None
    raw_build = headers.get('x-app-build', '')
    version = headers.get('x-app-version', '')
    # Explicit versions use the source-audited 0.<minor>.<patch> release scheme.
    # Unrecognized/hotfix version shapes fail open; a UA alone needs no version.
    version_match = re.fullmatch(r'0\.([0-9]{1,3})\.([0-9]{1,3})', version)
    version_build = int(version_match[1]) * 1000 + int(version_match[2]) if version_match else None
    if 'x-app-build' in headers:
        build = positive_build(raw_build)
        if platform != 'macos' or build is None or version_build != build:
            return None
        if agent_build is not None and agent_build != build:
            return None
        # A generic transport UA supplies no app identity. A supplied Omi
        # identity must parse and agree; it cannot be rescued by stale headers.
        if agent.lower().startswith('omi') and agent_build is None:
            return None
        return build
    if 'x-app-version' in headers and (version_build is None or version_build != agent_build):
        return None
    return agent_build


def build_bucket(build: int | None) -> str:
    if build is None:
        return 'unidentified'
    for bound, label in (
        (MIN_TERMINAL_TOOL_BUILD, 'below_supported'),
        (10000, '7000_9999'),
        (12000, '10000_11999'),
        (12400, '12000_12399'),
        (12500, '12400_12499'),
        (13000, '12500_12999'),
    ):
        if build < bound:
            return label
    return '13000_plus'


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
        build = identified_macos_build(headers)
        minimum = positive_build(os.getenv(MIN_CAPABLE_BUILD_ENV, '').strip())
        if (build is not None and build >= MIN_TERMINAL_TOOL_BUILD and (minimum is None or build < minimum)) and (
            headers.get('x-omi-workload', '') == 'extraction' or tagged == 'task_extraction'
        ):
            return 'macos_legacy_tasks'
        return 'desktop_other'
    tags = {'focus': 'windows_focus', 'dictation': 'macos_dictation', 'suggestions': 'macos_suggestions'}
    return tags.get(tagged, 'desktop_other')


def admission(model: str, state: State, lane: str, mode: str, *, bucket: str = 'unidentified') -> str:
    action = policy(model, state, lane=lane).kind
    if action == 'refuse' and (
        mode.strip().lower() == 'observe' or positive_build(os.getenv(MIN_CAPABLE_BUILD_ENV, '').strip()) is None
    ):
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
        bucket,
    ).inc()
    logger.info(
        'vertex_reservation_policy model=%s state=%s lane=%s action=%s build_bucket=%s',
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
        bucket,
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
    return (
        admission(
            model,
            states.get(model, State.UNKNOWN),
            lane,
            os.getenv(ENFORCEMENT_ENV, 'enforce'),
            bucket=build_bucket(identified_macos_build(headers)),
        )
        == 'refuse'
    )


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
