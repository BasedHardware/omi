"""Dual-backend contract for trends (ADR-0044 facade + ADR-0002 store port).

`database/trends.py` is the public trending board: `save_trends` folds every processed memory into a
per-category topic list, and the number the user sees next to a topic is the SIZE of the memory-id set
that topic accumulated. One shape carries all of it.

    atomic_field_ops   `topic_doc_ref.update({'memory_ids': ArrayUnion([memory_id])})`. The union is the
                       ranking: `get_trends_data` publishes `memories_count = len(memory_ids)` and sorts
                       the board by it. A backend that translated ArrayUnion as an assignment would reset
                       every topic to exactly one memory on each save, so the board would show every
                       topic tied at 1 and the ordering would become the arbitrary order of the last
                       batch. A backend that appended instead of unioning would count a retried memory
                       twice and float it to the top. Both are numbers a user reads directly.

                       The same `update` must also be FIELD-WISE: the topic label was written by a
                       separate `set(..., merge=True)` a line earlier, and `get_trends_data` drops any
                       topic whose label is not in `valid_items`. An update that replaced the document
                       would leave `{'memory_ids': [...]}` with no label, and the topic would silently
                       disappear from /v1/trends rather than fail loudly.

THE READER, and why it is in this file. Writing this suite surfaced a real on-prem defect:
`get_trends_data` streams with ``trends_ref.stream(retry=Retry())`` (database/trends.py:16 and :33),
the facade's ``_Query.stream`` took only ``transaction``, and so on STORAGE_BACKEND=mongo the FIRST
line of the reader body raised ``TypeError: _Query.stream() got an unexpected keyword argument
'retry'`` — outside the try/except, i.e. a 500 on every /v1/trends request. The second call sits
inside ``except Exception: continue``, so a fix that only reached line 16 would have served every
category with zero topics: an empty board instead of an error, which is worse. The facade now accepts
the SDK's transport kwargs (retry/timeout are adapter-owned policy; see the comment on
``_Query.stream``), and the reader tests below are the regression test for that fix — they fail on the
mongo leg against the previous facade.

Ids: unlike every other suite here, trends document ids CANNOT be randomised — they are
`document_id_from_seed(category + type)` and `document_id_from_seed(topic)`, and the topic must be a
member of `models.trend.valid_items` to be publishable at all. `trends` is also a TOP-LEVEL collection,
not uid-scoped, so the fixture deletes exactly the two category documents it writes and the topics
underneath them, and never touches the collection as a whole. Memory ids stay unique per run, which is
what the union assertions turn on.

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest

# Topics have to be real: `get_trends_data` filters on membership in `valid_items`, so a made-up label
# would be unpublishable and the assertions would be about a row no user can ever see.
MUSK, COOK = 'Elon Musk', 'Tim Cook'


@pytest.fixture
def trends(bind_store):
    """Unique memory ids, deterministic document ids, and a teardown scoped to exactly those documents."""
    from database.document_ids import document_id_from_seed

    run = uuid.uuid4().hex[:8]
    categories = {
        'best': document_id_from_seed('ceo' + 'best'),
        'worst': document_id_from_seed('ceo' + 'worst'),
    }

    rig = {
        'run': run,
        'store': bind_store,
        'categories': categories,
        'memories': [f'mem-a-{run}', f'mem-b-{run}'],
        'topic_id': document_id_from_seed,
    }
    _purge(rig)

    yield rig

    _purge(rig)


def _purge(trends) -> None:
    """Delete only the documents this suite addresses — topics first, since neither backend cascades."""
    for category_id in trends['categories'].values():
        for topic in trends['store'].query(f'trends/{category_id}/topics'):
            trends['store'].delete(topic.path)
        trends['store'].delete(f'trends/{category_id}')


def _save(trends, memory_id, *, topics, trend_type='best'):
    import database.trends as trends_db
    from models.trend import Trend

    trends_db.save_trends(memory_id, [Trend(category='ceo', type=trend_type, topics=topics)])


def _category(trends, trend_type='best'):
    stored = trends['store'].get(f"trends/{trends['categories'][trend_type]}")
    return stored.data if stored is not None and stored.exists else None


def _topic(trends, topic, trend_type='best'):
    path = f"trends/{trends['categories'][trend_type]}/topics/{trends['topic_id'](topic)}"
    stored = trends['store'].get(path)
    return stored.data if stored is not None and stored.exists else None


# --- atomic field ops -------------------------------------------------------------------------------


def test_a_saved_memory_is_recorded_against_its_topic(trends):
    """The base case the union builds on: one memory, one topic, one member."""
    memory_a, _memory_b = trends['memories']

    _save(trends, memory_a, topics=[MUSK])

    assert _topic(trends, MUSK)['memory_ids'] == [memory_a]
    assert _topic(trends, MUSK)['topic'] == MUSK


def test_two_memories_about_the_same_topic_accumulate(trends):
    """ArrayUnion, and the number it produces. `memories_count = len(memory_ids)` is the figure beside
    the topic on the trending board and the key it is sorted by, so a union translated as an assignment
    leaves every topic reading 1 and the board ordered by nothing."""
    memory_a, memory_b = trends['memories']

    _save(trends, memory_a, topics=[MUSK])
    _save(trends, memory_b, topics=[MUSK])

    assert sorted(_topic(trends, MUSK)['memory_ids']) == sorted([memory_a, memory_b])


def test_the_same_memory_reported_twice_is_counted_once(trends):
    """Set semantics, not append. Trend extraction is retried, and a retry that re-added the same memory
    id would inflate that topic's count and float it to the top of a board it did not earn."""
    memory_a, _memory_b = trends['memories']

    _save(trends, memory_a, topics=[MUSK])
    _save(trends, memory_a, topics=[MUSK])

    assert _topic(trends, MUSK)['memory_ids'] == [memory_a]


def test_the_union_does_not_erase_the_topic_label(trends):
    """The label is written by a `set(..., merge=True)` one line before the union, and `get_trends_data`
    skips any topic whose label is not in `valid_items`. A field-replacing update would leave the topic
    holding only its memory ids — and it would then vanish from /v1/trends quietly, with the count
    intact and nothing logged."""
    memory_a, memory_b = trends['memories']

    _save(trends, memory_a, topics=[MUSK])
    _save(trends, memory_b, topics=[MUSK])

    stored = _topic(trends, MUSK)
    assert stored['topic'] == MUSK, 'the union replaced the document instead of updating a field'
    assert stored['id'] == trends['topic_id'](MUSK)


def test_each_topic_keeps_its_own_memories(trends):
    """The union is per topic document. Merging two topics' sets would make an unrelated CEO inherit
    another one's mentions — a wrong name at the top of the board."""
    memory_a, memory_b = trends['memories']

    _save(trends, memory_a, topics=[MUSK])
    _save(trends, memory_b, topics=[COOK])

    assert _topic(trends, MUSK)['memory_ids'] == [memory_a]
    assert _topic(trends, COOK)['memory_ids'] == [memory_b]


def test_one_memory_can_open_several_topics_at_once(trends):
    """A single trend carries a list of topics; each gets its own document and its own union."""
    memory_a, _memory_b = trends['memories']

    _save(trends, memory_a, topics=[MUSK, COOK])

    assert _topic(trends, MUSK)['memory_ids'] == [memory_a]
    assert _topic(trends, COOK)['memory_ids'] == [memory_a]


def test_best_and_worst_are_separate_boards(trends):
    """`document_id_from_seed(category + type)` is what keeps them apart. Collapsing them would put a
    'worst CEO' mention into the 'best CEO' count — the most visible way to get this wrong."""
    memory_a, memory_b = trends['memories']

    _save(trends, memory_a, topics=[MUSK], trend_type='best')
    _save(trends, memory_b, topics=[MUSK], trend_type='worst')

    assert _category(trends, 'best')['type'] == 'best'
    assert _category(trends, 'worst')['type'] == 'worst'
    assert _topic(trends, MUSK, 'best')['memory_ids'] == [memory_a]
    assert _topic(trends, MUSK, 'worst')['memory_ids'] == [memory_b]


def test_resaving_a_category_keeps_its_identity(trends):
    """`set(..., merge=True)` on the category document. The id it carries is the one `get_trends_data`
    uses to reach the topics subcollection (`trends_ref.document(category_data['id'])`), so a merge that
    dropped or re-derived it would publish a category with no topics under it."""
    memory_a, memory_b = trends['memories']

    _save(trends, memory_a, topics=[MUSK])
    _save(trends, memory_b, topics=[COOK])

    stored = _category(trends)
    assert stored['id'] == trends['categories']['best']
    assert stored['category'] == 'ceo'
    assert isinstance(stored['created_at'], datetime)


def test_the_stored_shape_is_the_one_the_public_reader_consumes(trends):
    """Pinned at the storage boundary as well as through the reader: the exact fields `get_trends_data`
    indexes must be present and identically typed on both backends."""
    memory_a, _memory_b = trends['memories']

    _save(trends, memory_a, topics=[MUSK])

    category = _category(trends)
    assert set(category) >= {'id', 'category', 'type', 'created_at'}
    assert category['category'] in ['ceo', 'company', 'software_product', 'hardware_product', 'ai_product']

    topic = _topic(trends, MUSK)
    assert set(topic) >= {'id', 'topic', 'memory_ids'}
    assert isinstance(topic['memory_ids'], list)


def test_nothing_is_written_for_an_empty_topic_list(trends):
    """A trend with no topics still registers its category — the board shows an empty section rather than
    failing — but must not invent a topic document."""
    memory_a, _memory_b = trends['memories']

    _save(trends, memory_a, topics=[])

    assert _category(trends) is not None
    assert trends['store'].query(f"trends/{trends['categories']['best']}/topics") == []


# --- the reader: regression coverage for the facade transport-kwarg fix ---------------------------
#
# `trends` is a TOP-LEVEL collection and `get_trends_data` reads all of it, so these assert about the
# rows this run wrote rather than about the whole board — anything else would be a test that fails
# when a second suite runs beside it.


def _board_topic(topic_label):
    """This run's topic as the public reader publishes it, or None."""
    import database.trends as trends_db

    for category in trends_db.get_trends_data():
        for topic in category.get('topics') or []:
            if topic.get('topic') == topic_label:
                return category, topic
    return None, None


def test_the_public_reader_serves_the_board_on_both_backends(trends):
    """The regression test for the defect in the module docstring: before the facade accepted the SDK's
    transport kwargs this raised TypeError on its first line under Mongo, and /v1/trends was a 500 for
    every on-prem user. It is one line of production code and no test anywhere caught it, because the
    reader had never been run against the backend we deploy."""
    memory_a, _memory_b = trends['memories']

    _save(trends, memory_a, topics=[MUSK])

    category, topic = _board_topic(MUSK)
    assert category is not None, 'the reader did not publish the category this run wrote'
    assert category['category'] == 'ceo'
    assert topic['memories_count'] == 1


def test_the_published_count_is_the_size_of_the_unioned_set(trends):
    """The number the user actually reads, end to end: two distinct memories about one topic count 2,
    and the same memory reported twice still counts 1. This is the union proven through the reader
    rather than through the stored document."""
    memory_a, memory_b = trends['memories']

    _save(trends, memory_a, topics=[MUSK])
    _save(trends, memory_b, topics=[MUSK])
    _save(trends, memory_a, topics=[MUSK])

    _category_row, topic = _board_topic(MUSK)
    assert topic['memories_count'] == 2


def test_a_topic_the_reader_cannot_validate_is_dropped_rather_than_served(trends):
    """`get_trends_data` publishes only labels in `models.trend.valid_items`. A topic document whose
    label was lost — the failure mode the field-wise-update test above guards — must vanish from the
    board rather than surface as an unnamed row."""
    memory_a, _memory_b = trends['memories']

    _save(trends, memory_a, topics=[MUSK])
    topic_path = f"trends/{trends['categories']['best']}/topics/{trends['topic_id'](MUSK)}"
    stored = trends['store'].get(topic_path).data
    trends['store'].set(topic_path, {k: v for k, v in stored.items() if k != 'topic'})

    _category_row, topic = _board_topic(MUSK)
    assert topic is None
