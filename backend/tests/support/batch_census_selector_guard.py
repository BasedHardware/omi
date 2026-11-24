"""Apply the recurring-selector contract to executed Firestore shapes."""

from datetime import date, datetime
import math

from config.batch_census_selectors import (
    CALLER_PREFIXES,
    COLLECTION_PREFIXES,
    DUE_FIELDS,
    EXCEPTIONS,
    STATE_FIELDS,
)


def _bounded(tree):
    if not tree:
        return False
    if 'filters' in tree:
        children = tree['filters']
        combine = all if tree['op'] == 'OR' else any
        return bool(children) and combine(_bounded(child) for child in children)
    if tree['field'] == '__name__' and tree['operator'] == '==':
        return True  # Keyed claim or existence read.
    value = tree.get('value')
    finite = isinstance(value, datetime) or (type(value) in (int, float) and math.isfinite(value))
    return tree['field'] in DUE_FIELDS and tree['operator'] in ('<', '<=') and finite


def requires_exception(shape):
    if not shape.serving or shape.aggregations:
        return False
    if not (
        shape.collection_group.startswith(COLLECTION_PREFIXES) or shape.calling_function.startswith(CALLER_PREFIXES)
    ):
        return False
    fields = {item.field for item in shape.filters}
    return bool(fields & STATE_FIELDS) and not _bounded(shape.filter_tree)


def violation(shape, today, exceptions=EXCEPTIONS):
    if not requires_exception(shape):
        return None
    entry = exceptions.get(shape.calling_function)
    if entry is None:
        return f'{shape.calling_function}: state-selected page has no actionable due bound or reviewed exception'
    if entry.expiry < today:
        return f'{shape.calling_function}: recurring selector exception expired on {entry.expiry}'
    if shape.limit is None or not 0 < shape.limit <= entry.max_rows:
        return f'{shape.calling_function}: limit {shape.limit} exceeds exception bound {entry.max_rows}'
    return None
