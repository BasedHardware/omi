"""Regression: Dream duplicate captures in the projected MCP conversation reads.

Dream's ``merge_conversations`` cleanup folds a duplicate capture by writing
``dream_duplicate_of`` on the redundant row. The row keeps ``discarded`` false
and ``status`` completed, so the indexed list filters still return it and only
``is_visible_conversation`` hides it. The hosted MCP card reads select a field
mask, ``MCP_CONVERSATION_CARD_FIELD_PATHS``, that left the link out. The
predicate never saw it, so the MCP ``get_conversations`` tool, ``GET
/v1/mcp/conversations``, the Developer API card list and search hydration
returned both captures.
"""

from datetime import datetime, timedelta, timezone

import pytest

from database import conversations as conversations_db
from utils.mcp_server.handlers import conversations as conversations_handler

UID = 'uid-dream-duplicate'
T0 = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _project(row, field_paths):
    """Keep only the masked fields, the way Firestore returns a projected document."""
    if field_paths is None:
        return dict(row)
    projected = {}
    for path in field_paths:
        head, _, rest = path.partition('.')
        if head not in row:
            continue
        if not rest:
            projected[head] = row[head]
        elif isinstance(row[head], dict) and rest in row[head]:
            projected.setdefault(head, {})[rest] = row[head][rest]
    return projected


class _Snapshot:
    update_time = None
    exists = True

    def __init__(self, row, field_paths):
        self.id = row['id']
        self._data = _project(row, field_paths)

    def to_dict(self):
        return dict(self._data)


class _Ref:
    def __init__(self, doc_id):
        self.id = doc_id


class _Query:
    """Immutable query fake in ``(created_at DESC, __name__ DESC)`` order.

    Honors equality filters, ``select``, ``limit``, ``offset`` and a keyset
    ``start_after`` position. As in Firestore, a streamed document carries only
    the selected fields.
    """

    def __init__(self, rows, *, filters=(), field_paths=None, limit=None, offset=0, after=None):
        self._rows = rows
        self._filters = filters
        self._field_paths = field_paths
        self._limit = limit
        self._offset = offset
        self._after = after

    def _with(self, **changes):
        state = {
            'filters': self._filters,
            'field_paths': self._field_paths,
            'limit': self._limit,
            'offset': self._offset,
            'after': self._after,
        }
        state.update(changes)
        return _Query(self._rows, **state)

    def where(self, *, filter):
        assert filter.op_string == '=='
        return self._with(filters=self._filters + ((filter.field_path, filter.value),))

    def order_by(self, field_path, direction=None):
        return self

    def select(self, field_paths):
        return self._with(field_paths=tuple(field_paths))

    def limit(self, count):
        return self._with(limit=count)

    def offset(self, num_to_skip):
        return self._with(offset=num_to_skip)

    def start_after(self, position):
        return self._with(after=(position['created_at'], position['__name__'].id))

    def document(self, doc_id):
        return _Ref(doc_id)

    def stream(self, **kwargs):
        rows = [row for row in self._rows if all(row.get(field) == value for field, value in self._filters)]
        rows.sort(key=lambda row: (row['created_at'], row['id']), reverse=True)
        if self._after is not None:
            rows = [row for row in rows if (row['created_at'], row['id']) < self._after]
        rows = rows[self._offset :][: self._limit]
        return iter([_Snapshot(row, self._field_paths) for row in rows])


class _Client:
    def __init__(self, rows):
        self._rows = {row['id']: row for row in rows}
        self._conversations = _Query(rows)

    def collection(self, name):
        assert name in {'users', 'conversations'}
        return self if name == 'users' else self._conversations

    def document(self, uid):
        assert uid == UID
        return self

    def get_all(self, references, field_paths=None):
        return [_Snapshot(self._rows[reference.id], field_paths) for reference in references]


def _row(minute, **extra):
    return {
        'id': f'c{minute}',
        'created_at': T0 + timedelta(minutes=minute),
        'discarded': False,
        'status': 'completed',
        'structured': {'title': f'Conversation {minute}'},
        **extra,
    }


def _client():
    # A second device captured c3's moment as c2, and Dream folded c2 into c3.
    # The fold writes only the link; the row's lifecycle fields are unchanged.
    return _Client([_row(3), _row(2, dream_duplicate=True, dream_duplicate_of='c3'), _row(1)])


@pytest.mark.parametrize(
    ('arguments', 'expected_ids'),
    [
        ({'limit': 5}, ['c3', 'c1']),
        ({'limit': 5, 'offset': 1}, ['c1']),
    ],
    ids=['keyset-page', 'offset-page'],
)
def test_conversation_card_pages_hide_a_dream_duplicate(monkeypatch, arguments, expected_ids):
    client = _client()
    monkeypatch.setattr(conversations_handler.mcp_conversation_pages, 'get_firestore_client', lambda: client)

    result = conversations_handler.get_conversations(UID, arguments)

    assert [card['id'] for card in result['conversations']] == expected_ids
    assert result['has_more'] is False


def test_projected_reads_by_id_hide_a_dream_duplicate():
    conversations = conversations_db.get_mcp_conversations_by_id(
        UID, ['c3', 'c2', 'c1'], include_transcript=False, firestore_client=_client()
    )

    assert [conversation['id'] for conversation in conversations] == ['c3', 'c1']
