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
            'selection': settings.selection,
            'claims': settings.claims,
        }
    if arm == 'episode' and settings.apply_deadlines:
        payload['_request_options']['timeout_seconds'] = (
            settings.c6_timeout if settings.effort == 'xhigh' else settings.writer_timeout
        )
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


def evaluate_jev_selection(items, episode, *, cache_dir, llm, settings):
    from config.jev_decisions import JEV_MODEL
    from utils.conversations.episode_jev import JEV_SELECTOR_PROMPT
    from testing.episode_notes.schema import LLMResult
    from utils.conversations.episode_jev import evidence_question_batches, scored_episode_items

    conservative = deterministic_episode_selection(items, finished_at=episode.evidence.finished_at)
    receipt, scores = None, {}
    try:
        batches = evidence_question_batches(
            items, started_at=episode.evidence.started_at, finished_at=episode.evidence.finished_at
        )
        for batch in batches:
            result = cached_call(
                cache_dir,
                'jev-selection',
                JEV_MODEL,
                JEV_SELECTOR_PROMPT,
                {'state': batch.state, 'questions': batch.questions},
                llm,
            )
            scores.update(result.content['scores'])
            if receipt is None:
                receipt = result
            else:
                receipt = LLMResult(
                    content={},
                    **{
                        key: (
                            receipt.cost()[key] + result.cost()[key]
                            if receipt.cost()[key] is not None and result.cost()[key] is not None
                            else None
                        )
                        for key in receipt.cost()
                    }
                )
        if receipt is not None:
            receipt = LLMResult(content={'scores': scores}, **receipt.cost())
        return (
            scored_episode_items(
                items, batches, scores, threshold=settings.jev_threshold, finished_at=episode.evidence.finished_at
            ),
            receipt,
            None,
        )
    except Exception as exc:
        if isinstance(exc, LLMCallError):
            receipt = exc.result
        return conservative, receipt, 'jev_unavailable'
