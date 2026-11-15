"""Transaction-bound domain helpers. No simulator or Firestore SDK dependency."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime
from functools import wraps
from typing import Any, Callable, Iterable, ParamSpec, TypeVar, cast

from pydantic import BaseModel, ValidationError

from database.ports.base import MutationConflict, RevisionConflict

# Keep malformed rows in the ordered window, then validate after LIMIT. JSON
# numbers can exceed bigint; numeric is safe only behind the JSON type guard.
EVENT_SEQUENCE_SQL = (
    "CASE WHEN jsonb_typeof(doc->'sequence')='number' "
    "AND doc->>'sequence' ~ '^-?[0-9]+([.][0-9]+)?$' THEN (doc->>'sequence')::numeric END"
)
EVENT_SEQUENCE_TYPE_SQL = (
    "CASE jsonb_typeof(doc->'sequence') WHEN 'null' THEN 0 WHEN 'boolean' THEN 1 "
    "WHEN 'number' THEN 2 WHEN 'string' THEN 4 WHEN 'array' THEN 8 "
    "WHEN 'object' THEN CASE WHEN doc->'sequence' ? '$datetime' THEN 3 ELSE 10 END ELSE 10 END"
)
EVENT_SEQUENCE_DESC_SQL = (
    f"({EVENT_SEQUENCE_TYPE_SQL}) DESC, ({EVENT_SEQUENCE_SQL}) DESC NULLS LAST, "
    "(CASE WHEN jsonb_typeof(doc->'sequence') IN ('string','boolean') THEN doc->>'sequence' END) "
    'COLLATE "C" DESC, entity_id COLLATE "C" DESC'
)


# Typed generation match: a missing field is generation 0; wrong-typed legacy
# values (strings, booleans) are nonmatches instead of a failing bigint cast.
ACCOUNT_GENERATION_SQL = "coalesce(doc->'account_generation', '0'::jsonb)=to_jsonb(%s::bigint)"


def generation_matches(row: dict, expected: int) -> bool:
    """Python twin of ACCOUNT_GENERATION_SQL: missing is 0, only JSON numbers match."""
    if 'account_generation' not in row:
        return expected == 0
    stored = row['account_generation']
    return isinstance(stored, (int, float)) and not isinstance(stored, bool) and stored == expected


def event_payloads(model: type[BaseModel], rows):
    """Match the Firestore presentation model's skip-malformed read boundary."""
    for _, row in rows:
        # Firestore integer fields are signed 64-bit. Out-of-range numerics can
        # only be doubles, rejected by Pydantic's float-to-int coercion. JSONB
        # may decode those integral doubles as Python ints, losing that type.
        sequence = row.get('sequence')
        if isinstance(sequence, (int, float)) and not -9223372036854775808 <= sequence <= 9223372036854775807:
            continue
        try:
            yield model.model_validate(row).model_dump()
        except (ValidationError, TypeError):
            continue


def _jsonb_text(value) -> str:
    """Render like PostgreSQL jsonb::text: object keys by (length, bytes)."""
    if isinstance(value, dict):
        keys = sorted(value, key=lambda key: (len(key.encode()), key.encode()))
        return (
            '{' + ', '.join(f'{json.dumps(key, ensure_ascii=False)}: {_jsonb_text(value[key])}' for key in keys) + '}'
        )
    if isinstance(value, (list, tuple)):
        return '[' + ', '.join(_jsonb_text(item) for item in value) + ']'
    return json.dumps(value, ensure_ascii=False, default=str)


def scalar_order(value):
    if value is None:
        return (0, 0)
    if isinstance(value, bool):
        return (1, value)
    if isinstance(value, (int, float)):
        return (2, value)
    if isinstance(value, datetime):
        return (3, value.timestamp())
    if isinstance(value, str):
        return (4, value.encode())
    return (5, _jsonb_text(value))


P = ParamSpec('P')
R = TypeVar('R')


def atomic(fn: Callable[P, R]) -> Callable[P, R]:
    @wraps(fn)
    def call(*args: P.args, **kwargs: P.kwargs) -> R:
        self: Any = args[0]
        if self.store.bound:
            value = fn(*args, **kwargs)
            return cast(R, iter(list(cast(Iterable[Any], value)))) if fn.__name__ == 'iter_all' else value
        return self.store.run(lambda tx: getattr(getattr(tx, self.domain), fn.__name__)(*args[1:], **kwargs))

    return call


class Repo:
    domain: str

    def __init__(self, store: Any):
        self.store = store

    def receipt_entry(self, mutation_id, operation, data):
        """Return the digest and the saved receipt itself, so a saved None result stays a replay."""
        digest = hashlib.sha256(json.dumps([operation, data], sort_keys=True, default=str).encode()).hexdigest()
        prior = self.store.state['receipts'].get(mutation_id) if mutation_id is not None else None
        if prior is not None and prior['digest'] != digest:
            raise MutationConflict(mutation_id)
        return digest, prior

    def receipt(self, mutation_id, operation, data):
        digest, prior = self.receipt_entry(mutation_id, operation, data)
        return digest, prior['result'] if prior is not None else None

    def save(self, mutation_id, digest, result):
        if mutation_id is not None:
            self.store.state['receipts'][mutation_id] = {
                'digest': digest,
                'result': deepcopy(result),
                'domain': self.domain,
            }

    def _lock_in_order(self, collection, ids):
        """Read (and so row-lock) ids in flush's sorted address order.

        Multi-row bodies otherwise lock in caller order while buffered raw
        writes lock sorted, and two such transactions can deadlock.
        """
        rows = self.store.state[collection]
        for entity_id in sorted({i for i in ids if isinstance(i, str) and i}):
            rows.get(entity_id)

    def check(self, entity, entity_id, data, expected_revision):
        revision = data.get('revision', 1)
        if expected_revision is not None and revision != expected_revision:
            raise RevisionConflict(self.store.space_id, entity, entity_id, revision)
        return revision


class WorkflowRepo(Repo):
    entity_type: type[BaseModel]
    generation_error: type[Exception]
    collection = ''

    def _entity(self, row: Any, *, entity_id: str | None = None) -> Any:
        if row is None:
            return None
        data = deepcopy(row)
        if entity_id is not None:
            data['id'] = entity_id
        return self.entity_type.model_construct(**data)

    def _rows(self):
        return self.store.state[self.collection]

    def _read(self, entity_id):
        return self._rows().get(entity_id)

    def _write_task(self):
        self.store._task_write()

    def _generation(self, expected=None):
        control = self.store.state['task_intelligence_control'].get('state', {})
        generation = control.get('account_generation', 0)
        if expected is not None and (generation != expected or control.get('writes_blocked')):
            raise self.generation_error('account generation mismatch')
        return generation

    def _idempotent(self, operation, key, request, body):
        digest, prior = self.receipt_entry(key, operation, request)
        if prior is not None:
            return deepcopy(prior['result'])
        result = body()
        self.save(key, digest, result)
        return result

    @atomic
    def purge(self, space_id: str) -> int:
        if space_id != self.store.space_id:
            raise ValueError('purge must belong to this space')
        count = len(self._rows())
        self._rows().clear()
        for key, receipt in list(self.store.state['receipts'].items()):
            if receipt['domain'] == self.collection:
                del self.store.state['receipts'][key]
                count += 1
        if self.collection == 'action_items':
            count += len(self.store.state['task_intelligence_control'])
            self.store.state['task_intelligence_control'].clear()
        return count
