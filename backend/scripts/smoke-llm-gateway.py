#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys

import httpx


def main() -> int:
    parser = argparse.ArgumentParser(description='Smoke test the internal Omi LLM Gateway.')
    parser.add_argument(
        '--url',
        required=True,
        help='Base URL, for example http://dev-omi-llm-gateway.dev-omi-backend.svc.cluster.local:8080',
    )
    parser.add_argument('--token', required=True, help='Service bearer token')
    args = parser.parse_args()

    base_url = args.url.rstrip('/')
    headers = {
        'Authorization': f'Bearer {args.token}',
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
        ready.raise_for_status()
        response = client.post(f'{base_url}/v1/chat/completions', headers=headers, json=payload)
        response.raise_for_status()
        body = response.json()

    content = body.get('choices', [{}])[0].get('message', {}).get('content')
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
