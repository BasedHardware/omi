#!/usr/bin/env python3
"""Measure how Gemini honors thinking configuration across model families.

Why this exists: 2.5 models take an integer `thinkingConfig.thinkingBudget`,
while 3.x models take `thinkingConfig.thinkingLevel` and cannot disable
thinking. `thinkingBudget` stays schema-valid on 3.x, so a stale budget is
accepted and then ignored — and thinking tokens bill as OUTPUT. This probe
reports the actual `thoughtsTokenCount` per configuration so that "accepted and
ignored" is visible instead of assumed.

Read-only: it calls generateContent with a fixed trivial prompt and prints
token counts. It mutates nothing.

Needs credentials that can call `aiplatform.endpoints.predict`. The read-only
bot account cannot; a human ADC can:

    gcloud auth login && gcloud auth application-default login
    python3 backend/scripts/probe_gemini_thinking_contract.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

PROJECT = os.getenv('GOOGLE_CLOUD_PROJECT', 'based-hardware')
LOCATION = os.getenv('GCP_LOCATION', 'us-central1')

# A prompt with a real (if small) reasoning step, so a model that thinks
# produces a non-zero thoughtsTokenCount and one that does not produces zero.
PROMPT = 'A pen and a notebook cost $1.10 together. The notebook costs $1.00 more than the pen. Cost of the pen?'

CASES: tuple[tuple[str, dict[str, object]], ...] = (
    ('budget=0', {'thinkingConfig': {'thinkingBudget': 0}}),
    ('budget=1024', {'thinkingConfig': {'thinkingBudget': 1024}}),
    ('level=minimal', {'thinkingConfig': {'thinkingLevel': 'minimal'}}),
    ('no thinking config', {}),
)

MODELS = ('gemini-2.5-flash-lite', 'gemini-2.5-flash', 'gemini-3.1-flash-lite')


def access_token() -> str:
    return subprocess.run(
        ['gcloud', 'auth', 'print-access-token'],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def probe(model: str, config: dict[str, object], token: str) -> str:
    url = (
        f'https://{LOCATION}-aiplatform.googleapis.com/v1/projects/{PROJECT}'
        f'/locations/{LOCATION}/publishers/google/models/{model}:generateContent'
    )
    payload = {
        'contents': [{'role': 'user', 'parts': [{'text': PROMPT}]}],
        'generationConfig': {'maxOutputTokens': 2048, **config},
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')
        try:
            message = json.loads(detail)['error']['message']
        except Exception:
            message = detail
        return f'HTTP {exc.code}: {message[:150]}'
    except Exception as exc:  # network / auth shape
        return f'{type(exc).__name__}: {exc}'
    usage = body.get('usageMetadata', {})
    return (
        f'prompt={usage.get("promptTokenCount", "?")} '
        f'thoughts={usage.get("thoughtsTokenCount", 0)} '
        f'output={usage.get("candidatesTokenCount", "?")} '
        f'total={usage.get("totalTokenCount", "?")}'
    )


def main() -> int:
    try:
        token = access_token()
    except subprocess.CalledProcessError as exc:
        print(f'could not mint an access token: {exc.stderr.strip()}', file=sys.stderr)
        print('run: gcloud auth login && gcloud auth application-default login', file=sys.stderr)
        return 2
    print(f'project={PROJECT} location={LOCATION}\n')
    for model in MODELS:
        print(model)
        for label, config in CASES:
            print(f'  {label:<20} {probe(model, config, token)}')
        print()
    print('Interpretation:')
    print('  A 3.x model that IGNORES thinkingBudget shows thoughts>0 for budget=0.')
    print('  A 3.x model that HONORS it shows thoughts=0, and thinkingBudget could stay.')
    print('  Compare total tokens against the price table in backend/docs/vertex-pt-flash.md;')
    print('  gemini-3.1-flash-lite output costs 3.75x gemini-2.5-flash-lite output.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
