"""Explicit offline SystemOne adapter; request/answer schema matches the production client."""

import json
from time import perf_counter
from urllib.request import Request, urlopen

from config.jev_decisions import JEV_MODEL, JEV_CLIENT_TIMEOUT_SECONDS
from testing.episode_notes.schema import LLMCallError, LLMResult
from utils.llm.jev_client import _validated_answers


class SystemOneEndpoint:
    def __init__(self, *, key, base_url):
        self.key, self.url = key, base_url.rstrip('/') + '/systemone'

    def __call__(self, prompt, payload):
        body = {'model': JEV_MODEL, 'state': payload['state'], 'questions': payload['questions']}
        request = Request(
            self.url,
            data=json.dumps(body).encode(),
            headers={'Authorization': f'Bearer {self.key}', 'Content-Type': 'application/json'},
        )
        started = perf_counter()
        receipt = LLMResult(content={})
        try:
            with urlopen(request, timeout=JEV_CLIENT_TIMEOUT_SECONDS) as response:
                result = json.load(response)
            usage = result.get('usage') or {}
            receipt = LLMResult(
                content={},
                input_tokens=usage.get('input_tokens'),
                output_tokens=usage.get('output_tokens'),
                latency_seconds=perf_counter() - started,
                provider_cost=usage.get('cost'),
            )
            validated = _validated_answers(result, body['questions'])
            if validated is None:
                raise ValueError('malformed')
            scores = {
                q: (dict(validated.answers[q]['probabilities']) if question['type'] == 'choice' else validated.noul(q))
                for q, question in body['questions'].items()
            }
            return LLMResult(content={'scores': scores}, **receipt.cost())
        except Exception as exc:
            raise LLMCallError(
                type(exc).__name__,
                LLMResult(content={}, **{**receipt.cost(), 'latency_seconds': perf_counter() - started}),
            ) from None
