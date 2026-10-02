"""Synthetic, globally leased reservation probe; never accepts user content."""

import logging
import os
from collections.abc import Awaitable, Callable

import httpx

from utils.llm import vertex_pt_routing as ptr
from utils.llm.vertex_reservation_response import completed_provisioned_traffic

logger = logging.getLogger(__name__)


async def probe_reservation(
    client: httpx.AsyncClient, token: Callable[[], Awaitable[str]], model: str, location: str
) -> str:
    host, location = ptr.target_capacity_endpoint(location=location)
    project = os.getenv('GOOGLE_CLOUD_PROJECT', '').strip()
    if not project:
        return 'inconclusive'
    url = f'https://{host}/v1/projects/{project}/locations/{location}/publishers/google/models/{model}:generateContent'
    response = await client.post(
        url,
        headers={'Authorization': 'Bearer ' + await token(), ptr.REQUEST_TYPE_HEADER: 'dedicated'},
        json=ptr.model_payload(
            {
                'contents': [{'role': 'user', 'parts': [{'text': 'Reply OK.'}]}],
                # 2.x uses zero thinking; adaptation applies the declared 3.x level.
                'generationConfig': {'maxOutputTokens': 16, 'thinkingConfig': {'thinkingBudget': 0}},
            },
            model,
        ),
        timeout=30,
    )
    try:
        payload = response.json()
    except ValueError:
        return 'inconclusive'
    usage = payload.get('usageMetadata', {}) if isinstance(payload, dict) else {}
    usage = usage if isinstance(usage, dict) else {}
    counts = [usage.get(key) for key in ('promptTokenCount', 'candidatesTokenCount', 'thoughtsTokenCount')]
    logger.info(
        'vertex_reservation_probe model=%s status=%d input_tokens=%s output_tokens=%s thinking_tokens=%s',
        model,
        response.status_code,
        *(n if type(n) is int and n >= 0 else None for n in counts),
    )
    if 200 <= response.status_code < 300 and completed_provisioned_traffic(payload):
        return 'dedicated_success'
    if ptr.is_provisioned_capacity_exhausted(response.status_code, response.text):
        return 'capacity_error'
    return 'inconclusive'
