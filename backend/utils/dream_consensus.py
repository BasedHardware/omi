"""Independent sample votes, with one vote per item per returned sample."""

from collections import Counter
from functools import lru_cache
import json
import unicodedata

from models.dream_agent import Plan, FullPlan
from utils.dream_grounding import rank_questions


def normalized(text):
    # Preserve case: capitalization edits and reciprocal case flips have direction.
    return ' '.join(unicodedata.normalize('NFKC', text).split())


def item_key(field, item):
    if field == 'edits':
        return item.kind, item.target, normalized(item.before), normalized(item.after)
    if field == 'questions':
        return item.source_ref, item.quote
    if field == 'vocabulary':
        return item.kind, item.spelling
    return json.dumps(item.model_dump(mode='json'), sort_keys=True)


@lru_cache(maxsize=1)
def array_limits(model=Plan):
    return {field: schema['maxItems'] for field, schema in model.model_json_schema()['properties'].items()}


def majority(plans, *, usage_sink=None):
    if not plans:
        raise ValueError('dream_no_samples')
    threshold = len(plans) // 2 + 1
    model = type(plans[0])
    retained = {}
    rejected = 0
    for field in Plan.model_fields:
        votes = Counter()
        candidates = {}
        for plan in plans:
            seen = set()
            for item in getattr(plan, field):
                key = item_key(field, item)
                candidates.setdefault(key, item)
                seen.add(key)
            votes.update(seen)
        survivors = []
        for key, item in candidates.items():
            if votes[key] >= threshold:
                item = item.model_copy(deep=True)
                item.set_agreement(votes[key], len(plans))
                survivors.append(item)
        if field == 'questions':
            if model is FullPlan:
                survivors = rank_questions(survivors, usage_sink=usage_sink)
            else:
                survivors.sort(key=lambda item: (item.agreement, getattr(item, 'value', 0)), reverse=True)
        retained[field] = survivors[: array_limits(model)[field]]
        rejected += sum(count < threshold for count in votes.values())
    if usage_sink is not None:
        usage_sink['consensus_threshold'] = threshold
        counts = Counter(usage_sink.get('rejected', {}))
        counts['consensus_rejected'] += rejected
        usage_sink['rejected'] = dict(+counts)
    return model.model_validate(retained)


def unanimous_spelling(edit):
    return edit.kind == 'spelling' and edit.samples >= 2 and edit.agreement == edit.samples


def plan_dump(plan, *, full=False):
    result = plan.model_dump(mode='python')
    if full:
        for field in Plan.model_fields:
            for item, row in zip(getattr(plan, field), result[field]):
                row.update(agreement=item.agreement, samples=item.samples)
    return result


def item_dump(item):
    return {**item.model_dump(mode='python'), 'agreement': item.agreement, 'samples': item.samples}
