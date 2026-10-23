"""Offline candidate-writer request routing."""

from types import SimpleNamespace

from testing.episode_notes.prompts import candidate_request
from testing.episode_notes.writer_runtime import episode_budget_exceeded


def routed_candidate_request(episode, arm, settings, items, candidate_prompt=None):
    from utils.conversations.episode_tiers import episode_tier

    if arm == 'episode':
        settings, _, _ = episode_tier(items, settings)
    prompt, payload = candidate_request(episode, arm, settings=settings, items=items)
    if arm == 'episode':
        prompt = candidate_prompt or prompt
        if settings.thinking_max_input_bytes > 0 and episode_budget_exceeded(
            [SimpleNamespace(content=prompt), SimpleNamespace(content=payload['instructions'])], settings, None
        ):
            prompt, payload = candidate_request(episode, 'baseline')
            return prompt, payload, 'baseline'
        payload['_request_options'] = {
            'effort': settings.effort,
            'claims': settings.claims,
        }
    if arm == 'episode' and settings.apply_deadlines:
        payload['_request_options']['timeout_seconds'] = (
            settings.c6_timeout if settings.effort == 'xhigh' else settings.writer_timeout
        )
    return prompt, payload, arm
