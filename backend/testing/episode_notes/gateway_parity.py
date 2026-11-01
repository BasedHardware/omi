"""Read serving policy without importing the gateway or production clients."""

from dataclasses import replace
from pathlib import Path

import yaml

from testing.episode_notes.schema import LLMCallError, _result

ROUTE_OVERRIDES = Path(__file__).resolve().parents[2] / 'llm_gateway/config/generated_route_overrides.yaml'


def gateway_structure_effort(path=None):
    routes = yaml.safe_load((path or ROUTE_OVERRIDES).read_text())['generated_route_overrides']
    matches = [route for route in routes if route['feature'] == 'conv_structure']
    if len(matches) != 1:
        raise ValueError('expected exactly one conv_structure gateway override')
    effort = matches[0]['provider_options']['reasoning_effort']
    if effort not in {'none', 'minimal', 'low', 'medium', 'high', 'xhigh'}:
        raise ValueError('invalid conv_structure gateway effort')
    return effort


class CandidateEffortParity:
    def __init__(self, llm, *, excluded_prompts, jev_prompt, provider_default=False):
        self.llm = llm
        self.excluded_prompts = set(excluded_prompts)
        self.jev_prompt = jev_prompt
        self.default_effort = 'default' if provider_default else gateway_structure_effort()

    def prepare_payload(self, prompt, payload):
        if prompt in self.excluded_prompts:
            return payload
        options = dict(payload.get('_request_options') or {})
        if options.get('effort', 'default') == 'default':
            options['effort'] = self.default_effort
        return {**payload, '_request_options': options}

    def __call__(self, prompt, payload):
        effort = None if prompt == self.jev_prompt else (payload.get('_request_options') or {}).get('effort', 'default')
        try:
            return replace(_result(self.llm(prompt, payload)), effective_effort=effort)
        except LLMCallError as exc:
            raise LLMCallError(exc.error_class, replace(exc.result, effective_effort=effort)) from None
