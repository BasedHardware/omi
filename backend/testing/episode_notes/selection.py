"""Selection experiment uses production volume/timeout guards and conservative fallback."""

from testing.episode_notes.cache import cached_call
from testing.episode_notes.schema import LLMCallError
from testing.episode_notes.prompts import candidate_request
from types import SimpleNamespace
from utils.llm.episode_writer import episode_budget_exceeded
from utils.conversations.episode_selection import (
    SELECTION_PROMPT,
    deterministic_episode_selection,
    selected_episode_items,
    selection_payload,
    model_selection_allowed,
)


def routed_candidate_request(episode, arm, settings, items, candidate_prompt=None):
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
            'selection': settings.selection,
            'claims': settings.claims,
        }
    return prompt, payload, arm


def evaluate_selection(items, episode, *, cache_dir, candidate_model, llm, settings):
    conservative = deterministic_episode_selection(items, finished_at=episode.evidence.finished_at)
    if not model_selection_allowed(items):
        return conservative, None, 'selection_long_input'
    receipt = None
    try:
        receipt = cached_call(
            cache_dir,
            'selection',
            candidate_model,
            SELECTION_PROMPT,
            {
                **selection_payload(items, episode.evidence.started_at, episode.evidence.finished_at),
                '_request_options': {
                    'effort': settings.selection_effort,
                    'timeout_seconds': settings.selection_timeout,
                },
            },
            llm,
        )
        return selected_episode_items(items, receipt.content, finished_at=episode.evidence.finished_at), receipt, None
    except Exception as exc:
        if isinstance(exc, LLMCallError):
            receipt = exc.result
        return conservative, receipt, 'selection_unavailable'
