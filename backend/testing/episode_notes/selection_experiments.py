"""DEV selector ablations: veto existing links rather than add coincidental context."""

from dataclasses import replace
from config.jev_decisions import JEV_MODEL
from testing.episode_notes.cache import cached_call
from testing.episode_notes.schema import LLMResult
from utils.conversations.episode_jev import JEV_SELECTOR_PROMPT, evidence_question_batches
from utils.conversations.episode_selection import deterministic_episode_selection

MODES = ('jev_veto', 'jev_per_source', 'jev_rank', 'jev_discussed', 'jev_choice', 'jev_per_source_pool')


def experiment_batches(items, episode, mode):
    batches = evidence_question_batches(
        items, started_at=episode.evidence.started_at, finished_at=episode.evidence.finished_at
    )
    if mode not in {'jev_discussed', 'jev_choice'}:
        return batches
    changed = []
    for batch in batches:
        questions = {}
        for name in batch.questions:
            if mode == 'jev_discussed':
                question = {
                    'type': 'noul',
                    'instructions': f'Was candidate {name} discussed or referred to by the people in this conversation?',
                    'criteria': {
                        'true': 'An explicit speech reference or an interaction with this item evidenced during this capture.',
                        'false': 'Only visible nearby, a vocabulary or name overlap, an unrelated activity, or uncertain reference.',
                    },
                }
            else:
                question = {
                    'type': 'choice',
                    'instructions': f'How does candidate {name} relate to the interaction captured in the speech?',
                    'criteria': {
                        'discussed': 'Explicitly discussed, referred to, or interacted with by these people during this capture.',
                        'background': 'An evidenced link explains a current interaction or capture condition, but was not discussed.',
                        'unrelated': 'Only co-occurs on screen, vocabulary/name overlap, or connection is uncertain.',
                    },
                }
            questions[name] = question
        changed.append(replace(batch, questions=questions))
    return changed


def experiment_selection(items, episode, *, mode, cutoff, cache_dir, llm):
    conservative = deterministic_episode_selection(items, finished_at=episode.evidence.finished_at)
    question_items = conservative if mode == 'jev_per_source_pool' else items
    mode = 'jev_per_source' if mode == 'jev_per_source_pool' else mode
    receipts, scores = [], {}
    batches = experiment_batches(question_items, episode, mode)
    for batch in batches:
        result = cached_call(
            cache_dir,
            'jev-selection',
            JEV_MODEL,
            JEV_SELECTOR_PROMPT,
            {'state': batch.state, 'questions': batch.questions},
            llm,
        )
        receipts.append(result)
        for name, ids in batch.item_ids.items():
            value = result.content['scores'][name]
            if isinstance(value, dict):
                value = value['discussed'] + value['background']
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
                raise ValueError('invalid_experiment_score')
            scores.update({item_id: value for item_id in ids})
    fixed = {'speech', 'device_state', 'roster', 'calendar'}
    pool = [i for i in conservative if i.source_kind not in fixed]
    if mode == 'jev_rank':
        # Strict sub-budget of the existing deterministic pool; never add new evidence.
        budget = sum(len(i.content) for i in pool) * cutoff
        chosen, used = set(), 0
        for item in sorted(pool, key=lambda i: scores.get(i.id, 0), reverse=True):
            if used + len(item.content) <= budget:
                chosen.add(item.id)
                used += len(item.content)
    else:
        chosen = {
            i.id
            for i in pool
            if scores.get(i.id, 0)
            >= (
                max(cutoff, 0.7)
                if mode == 'jev_per_source' and i.source_kind in {'screen_frame', 'screen_ocr', 'message'}
                else cutoff
            )
        }
    selected = [i for i in conservative if i.source_kind in fixed or i.id in chosen]
    receipt = (
        LLMResult(
            content={'scores': scores},
            **{
                k: (
                    sum(r.cost()[k] for r in receipts)
                    if receipts and all(r.cost()[k] is not None for r in receipts)
                    else None
                )
                for k in LLMResult(content={}).cost()
            },
        )
        if receipts
        else None
    )
    return selected, receipt, None
