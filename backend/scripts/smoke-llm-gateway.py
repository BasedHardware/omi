#!/usr/bin/env python3
from __future__ import annotations
from typing import Any, Dict, List, cast

import argparse
import json
import os
import time

import httpx


def _raise_for_status(response: httpx.Response, label: str) -> None:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError:
        print(f'ERROR: {label} returned HTTP {response.status_code}')
        print(response.text[:1000])
        raise


def _get_ready(client: httpx.Client, url: str, headers: dict[str, str]) -> httpx.Response:
    last_error: Exception | None = None
    for attempt in range(1, 31):
        try:
            ready = client.get(f'{url}/ready', headers=headers)
            if ready.status_code < 500:
                _raise_for_status(ready, '/ready')
                return ready
            last_error = httpx.HTTPStatusError(
                f'/ready returned HTTP {ready.status_code}',
                request=ready.request,
                response=ready,
            )
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as exc:
            last_error = exc
        if attempt < 30:
            time.sleep(2)
    print(f'ERROR: /ready did not become available: {last_error}')
    return client.get(f'{url}/ready', headers=headers)


def _assert_success_metric(client: httpx.Client, url: str, metrics_token: str) -> None:
    headers = {'Authorization': f'Bearer {metrics_token}'}
    for attempt in range(1, 11):
        response = client.get(f'{url}/metrics', headers=headers)
        _raise_for_status(response, '/metrics')
        metric_line = _find_success_request_metric(response.text)
        if metric_line is not None:
            print(f'LLM gateway success metric observed: {metric_line}')
            return
        if attempt < 10:
            time.sleep(2)
    print('ERROR: llm_gateway_requests_total success metric was not observed')
    raise RuntimeError('llm gateway success metric missing')


def _find_success_request_metric(metrics_text: str) -> str | None:
    for line in metrics_text.splitlines():
        if not line.startswith('llm_gateway_requests_total{'):
            continue
        if 'lane_id="omi:auto:chat-structured"' not in line or 'outcome="success"' not in line:
            continue
        try:
            value = float(line.rsplit(' ', 1)[-1])
        except ValueError:
            continue
        if value > 0:
            return line
    return None


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
    parser.add_argument(
        '--check-metrics',
        action='store_true',
        help='Verify llm_gateway_requests_total increments after the smoke request',
    )
    parser.add_argument(
        '--metrics-token',
        default=None,
        help='Metrics bearer token (default: read from METRICS_SECRET env var)',
    )
    args = parser.parse_args()

    token = (args.token or os.environ.get('OMI_LLM_GATEWAY_SERVICE_TOKEN') or '').strip()
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
                    'properties': {'value': {'type': 'boolean'}},
                    'required': ['value'],
                    'additionalProperties': False,
                },
            },
        },
        'metadata': {'omi_feature': 'chat_extraction.requires_context'},
    }

    with httpx.Client(timeout=20.0) as client:
        _get_ready(client, base_url, headers)
        response = client.post(f'{base_url}/v1/chat/completions', headers=headers, json=payload)
        _raise_for_status(response, '/v1/chat/completions')
        body: Dict[str, Any] = cast(Dict[str, Any], response.json())
        if args.check_metrics:
            metrics_token = (args.metrics_token or os.environ.get('METRICS_SECRET') or '').strip()
            if not metrics_token:
                print('ERROR: provide --metrics-token or set METRICS_SECRET env var when --check-metrics is used')
                return 2
            _assert_success_metric(client, base_url, metrics_token)

    choices: List[Dict[str, Any]] = cast(List[Dict[str, Any]], body.get('choices') or [{}])
    message: Dict[str, Any] = cast(Dict[str, Any], choices[0].get('message', {}))
    content = message.get('content')
    if not isinstance(content, str):
        print('ERROR: response did not contain choices[0].message.content')
        return 1
    try:
        decoded = json.loads(content)
    except ValueError:
        print('ERROR: response content was not JSON')
        return 1
    if not isinstance(decoded.get('value'), bool):
        print('ERROR: response JSON did not contain boolean value')
        return 1
    print('LLM gateway smoke passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
