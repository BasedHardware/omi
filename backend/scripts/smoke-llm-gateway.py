#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys

import httpx


def _raise_for_status(response: httpx.Response, label: str) -> None:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError:
        print(f'ERROR: {label} returned HTTP {response.status_code}')
        print(response.text[:1000])
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description='Smoke test the internal Omi LLM Gateway.')
    parser.add_argument(
        '--url',
        required=True,
        help='Base URL, for example http://dev-omi-llm-gateway.dev-omi-backend.svc.cluster.local:8080',
    )
    parser.add_argument(
        '--token',
        default=None,
        help='Service bearer token (default: read from OMI_LLM_GATEWAY_SERVICE_TOKEN env var)',
    )
    args = parser.parse_args()

    token = args.token or os.environ.get('OMI_LLM_GATEWAY_SERVICE_TOKEN')
    if not token:
        print('ERROR: provide --token or set OMI_LLM_GATEWAY_SERVICE_TOKEN env var')
        return 2

    base_url = args.url.rstrip('/')
    headers = {
        'Authorization': f'Bearer {token}',
        'X-Omi-Service-Caller': 'backend',
        'Content-Type': 'application/json',
    }
    payload = {
        'model': 'omi:auto:chat-structured',
        'messages': [
            {'role': 'user', 'content': 'Question: should this use prior conversation context? Answer false.'}
        ],
        'response_format': {
            'type': 'json_schema',
            'json_schema': {
                'name': 'RequiresContext',
                'strict': True,
                'schema': {
                    'type': 'object',
                    'properties': {'requires_context': {'type': 'boolean'}},
                    'required': ['requires_context'],
                    'additionalProperties': False,
                },
            },
        },
        'metadata': {'omi_feature': 'chat_extraction.requires_context.smoke'},
    }

    with httpx.Client(timeout=20.0) as client:
        ready = client.get(f'{base_url}/ready', headers=headers)
        _raise_for_status(ready, '/ready')
        response = client.post(f'{base_url}/v1/chat/completions', headers=headers, json=payload)
        _raise_for_status(response, '/v1/chat/completions')
        body = response.json()

    content = (body.get('choices') or [{}])[0].get('message', {}).get('content')
    if not isinstance(content, str):
        print('ERROR: response did not contain choices[0].message.content')
        return 1
    try:
        decoded = json.loads(content)
    except ValueError:
        print('ERROR: response content was not JSON')
        return 1
    if not isinstance(decoded.get('requires_context'), bool):
        print('ERROR: response JSON did not contain boolean requires_context')
        return 1
    print('LLM gateway smoke passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
