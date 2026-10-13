"""Independent sample votes, with one vote per item per returned sample."""

from collections import Counter
from functools import lru_cache
import json
import unicodedata

from models.dream_agent import Plan


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
def array_limits():
    return {field: schema['maxItems'] for field, schema in Plan.model_json_schema()['properties'].items()}


def majority(plans, *, usage_sink=None):
    if not plans:
        raise ValueError('dream_no_samples')
    threshold = len(plans) // 2 + 1
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
        retained[field] = [item for key, item in candidates.items() if votes[key] >= threshold][: array_limits()[field]]
        rejected += sum(count < threshold for count in votes.values())
    if usage_sink is not None:
        usage_sink['consensus_threshold'] = threshold
        counts = Counter(usage_sink.get('rejected', {}))
        counts['consensus_rejected'] += rejected
        usage_sink['rejected'] = dict(+counts)
    return Plan.model_validate(retained)
