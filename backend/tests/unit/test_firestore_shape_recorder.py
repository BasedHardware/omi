"""Focused tests for the recording Firestore fake (tests.support.firestore_shape_recorder)."""

import dataclasses
import datetime
import enum
import json

import pytest
import google.cloud.firestore as gcloud_firestore
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import And, BaseCompositeFilter, FieldFilter, Or

from database import _client as client_module
from database._client import (
    data_plane_db,
    db,
    get_customer_firestore_client,
    get_data_plane_firestore_client,
    get_firestore_client,
    get_users_uid,
)
from tests.support.firestore_shape_recorder import (
    Aggregation,
    QueryShape,
    RecordingDocumentSnapshot,
    RecordingFirestore,
    install_recorder,
)

try:
    import firebase_admin.firestore as fa_firestore
except ImportError:
    fa_firestore = None


@pytest.fixture
def client():
    return RecordingFirestore()


def test_query_builder_is_immutable_and_forks_record_distinct_shapes(client):
    base = client.collection('users').document('u1').collection('conversations')
    fork_a = base.where('discarded', '==', False)
    fork_b = base.where('starred', '==', True)

    assert len(base._state.filter_nodes) == 0

    list(fork_a.stream())
    list(fork_b.stream())
    list(base.stream())

    assert len(client.shapes) == 3
    by_filters = {tuple((f.field, f.operator) for f in s.filters): s for s in client.shapes}
    assert (('discarded', '=='),) in by_filters
    assert (('starred', '=='),) in by_filters
    assert () in by_filters
    assert by_filters[(('discarded', '=='),)].signature() != by_filters[(('starred', '=='),)].signature()


def test_no_shape_recorded_until_terminal_call(client):
    query = (
        client.collection('conversations')
        .where(filter=FieldFilter('discarded', '==', False))
        .order_by('created_at')
        .limit(10)
    )
    query2 = query.where('starred', '==', True)
    assert client.shapes == []
    query2.get()
    assert len(client.shapes) == 1


def test_positional_and_composite_filters_preserve_tree(client):
    leaf_a = FieldFilter('a', '==', 1)
    leaf_b = FieldFilter('b', 'array-contains', 'x')
    leaf_c = FieldFilter('c', '>=', 5)
    composite = Or([leaf_a, And([leaf_b, leaf_c])])

    query = client.collection_group('items').where('z', '!=', 0).where(filter=composite)
    query.get()

    (shape,) = client.shapes
    assert [f.field for f in shape.filters] == ['z', 'a', 'b', 'c']
    assert {f.field: f.operator for f in shape.filters}['b'] == 'array_contains'
    assert shape.filter_tree == {
        'op': 'AND',
        'filters': [
            {'field': 'z', 'operator': '!=', 'value': 0},
            {
                'op': 'OR',
                'filters': [
                    {'field': 'a', 'operator': '==', 'value': 1},
                    {
                        'op': 'AND',
                        'filters': [
                            {'field': 'b', 'operator': 'array_contains', 'value': 'x'},
                            {'field': 'c', 'operator': '>=', 'value': 5},
                        ],
                    },
                ],
            },
        ],
    }


def test_base_composite_and_filter_preserves_tree(client):
    composite = BaseCompositeFilter('AND', [FieldFilter('a', '==', 1), FieldFilter('b', '<', 2)])
    client.collection('c').where(filter=composite).get()
    (shape,) = client.shapes
    assert [f.field for f in shape.filters] == ['a', 'b']
    assert shape.filter_tree == {
        'op': 'AND',
        'filters': [
            {'field': 'a', 'operator': '==', 'value': 1},
            {'field': 'b', 'operator': '<', 'value': 2},
        ],
    }


def test_all_modifiers_and_scopes_are_retained(client):
    reference = client.document('users/u1')
    query = (
        client.collection('users')
        .document('u1')
        .collection('conversations')
        .where(filter=FieldFilter('source', 'in', ['a', 'b']))
        .order_by('created_at', direction=firestore.Query.DESCENDING)
        .order_by('title')
        .offset(3)
        .limit(25)
        .select(['created_at', 'title'])
        .start_after(reference)
        .end_at({'created_at': 'x'})
    )
    query.get()

    (shape,) = client.shapes
    assert shape.scope == 'COLLECTION'
    assert shape.collection_group == 'conversations'
    assert shape.collection_path == 'users/u1/conversations'
    assert shape.document_path_template == 'users/{uid}/conversations/{document_id}'
    assert shape.orders == (('created_at', 'DESCENDING'), ('title', 'ASCENDING'))
    assert shape.limit == 25
    assert shape.offset == 3
    assert shape.projection == ('created_at', 'title')
    assert shape.uses_cursors is True
    assert [c[0] for c in shape.cursors] == ['start_after', 'end_at']

    client.collection_group('conversations').limit_to_last(7).stream()
    grouped = client.shapes[-1]
    assert grouped.scope == 'COLLECTION_GROUP'
    assert grouped.collection_group == 'conversations'
    assert grouped.limit == 7 and grouped.limit_to_last is True


def test_aggregations_record_kind_field_alias_and_return_neutral(client):
    query = client.collection('events').where(filter=FieldFilter('uid', '==', 'u1'))

    results = query.count(alias='total').sum('duration', alias='sum_d').avg('score').get()
    assert results[0][0].value == 0 and results[0][0].alias == 'total'
    assert results[0][1].alias == 'sum_d' and results[0][2].alias == 'score'

    streamed = list(query.count().stream())
    assert streamed[0][0].value == 0 and streamed[0][0].alias == 'count_1'

    shapes = client.shapes
    assert len(shapes) == 2
    assert shapes[0].aggregations == (
        Aggregation('count', None, 'total'),
        Aggregation('sum', 'duration', 'sum_d'),
        Aggregation('avg', 'score', None),
    )
    assert shapes[1].aggregations == (Aggregation('count', None, None),)


def test_document_reads_are_not_queries_and_seed_payloads():
    seeded = RecordingFirestore(documents={'users/u1': {'name': 'Ada'}})
    snapshot = seeded.collection('users').document('u1').get()
    assert snapshot.exists is True
    assert snapshot.to_dict() == {'name': 'Ada'}
    assert snapshot.id == 'u1'
    assert snapshot.reference.path == 'users/u1'

    missing = seeded.document('users/nope').get()
    assert missing.exists is False
    assert missing.to_dict() is None

    assert seeded.shapes == []


def test_nested_subcollection_path_and_ids(client):
    query = client.collection('users').document('u9').collection('files').document('f1').collection('chunks')
    assert query.id == 'chunks'
    assert query.path == 'users/u9/files/f1/chunks'
    assert query.parent.id == 'f1'
    query.get()
    (shape,) = client.shapes
    assert shape.collection_group == 'chunks'
    assert shape.collection_path == 'users/u9/files/f1/chunks'
    assert shape.document_path_template == 'users/{uid}/files/{document_id}/chunks/{document_id}'


def test_real_transactional_decorator_with_query_read_then_write(client):
    @firestore.transactional
    def _transact(transaction):
        docs = list(
            transaction.get(client.collection('users').document('u1').collection('logs').where('kind', '==', 'x'))
        )
        ref = client.collection('users').document('u1')
        transaction.update(ref, {'seen': len(docs)})
        return 'done'

    result = _transact(client.transaction())
    assert result == 'done'
    assert len(client.shapes) == 1
    assert client.shapes[0].collection_path == 'users/u1/logs'


def test_install_recorder_covers_all_getters_and_lazy_proxies(client):
    previous_main = client_module._firestore_client
    previous_customer = client_module._customer_firestore_client
    previous_data_plane = client_module._data_plane_firestore_client

    with install_recorder(client) as installed:
        assert installed is client
        assert get_firestore_client() is client
        assert get_customer_firestore_client() is client
        assert get_data_plane_firestore_client() is client
        assert db.collection('users') is not None
        db.collection('users').document('u1').collection('conversations').stream()
        data_plane_db.collection('users').get()
        assert gcloud_firestore.Client() is client
        if fa_firestore is not None:
            assert fa_firestore.client() is client

    assert len(client.shapes) == 2
    assert client_module._firestore_client is previous_main
    assert client_module._customer_firestore_client is previous_customer
    assert client_module._data_plane_firestore_client is previous_data_plane


def test_stack_attribution_matches_calling_database_function(client):
    with install_recorder(client):
        assert get_users_uid() == []
    (shape,) = client.shapes
    assert shape.calling_function == 'database._client.get_users_uid'


def test_recording_context_stamps_driver_and_combo_without_overriding_stack(client):
    with install_recorder(client), client.recording_context('driver:example', combo={'flag': True}):
        get_users_uid()
    (shape,) = client.shapes
    assert shape.calling_function == 'database._client.get_users_uid'
    assert shape.driver_function == 'driver:example'
    assert shape.parameter_combo == {'flag': True}
    assert client.driver_function == '' and client.parameter_combo == {}

    client.collection('users').get()
    assert client.shapes[-1].signature() != shape.signature()


def test_to_dict_serializes_tagged_values_deterministically(client):
    stamp = datetime.datetime(2024, 1, 2, 3, 4, 5, tzinfo=datetime.timezone.utc)
    reference = client.document('users/u2')
    query = (
        client.collection('conversations')
        .where(filter=FieldFilter('created_at', '>=', stamp))
        .where(filter=FieldFilter('owner', '==', reference))
        .where(filter=FieldFilter('blob', '==', b'\x01\x02'))
        .limit(4)
    )
    query.get()
    (shape,) = client.shapes

    payload = shape.to_dict()
    encoded = {f['field']: f['value'] for f in payload['filters']}
    assert encoded['created_at'] == {'type': 'timestamp', 'value': '2024-01-02T03:04:05+00:00'}
    assert encoded['owner'] == {'type': 'reference', 'value': 'users/u2'}
    assert encoded['blob'] == {'type': 'bytes', 'value': 'AQI='}

    serialized = json.dumps(payload, sort_keys=True)
    assert serialized == json.dumps(payload, sort_keys=True)
    json.dumps(shape.signature())

    other = dataclasses.replace(shape, limit=99)
    assert other.signature() == shape.signature()


def test_unsupported_representative_value_raises(client):
    class Opaque:
        pass

    client.collection('c').where(filter=FieldFilter('f', '==', Opaque())).get()
    with pytest.raises(TypeError, match='unsupported query representative value'):
        client.shapes[0].to_dict()


def test_enum_values_encode_underlying_value_and_sets_encode_sorted(client):
    class Source(enum.Enum):
        OMI = 'omi'
        DESKTOP = 'desktop'

    query = client.collection('c').where(filter=FieldFilter('source', '==', Source.DESKTOP))
    query.get()
    encoded = client.shapes[0].to_dict()['filters'][0]['value']
    assert encoded['value'] == 'desktop' and encoded['enum'] == Source.__qualname__

    client.parameter_combo = {'members': {'b', 'a'}, 'frozen': frozenset({2, 1})}
    client.collection('c').get()
    combo = client.shapes[-1].to_dict()['parameter_combo']
    assert combo['members']['value'] == [
        {'type': 'str', 'value': 'a'},
        {'type': 'str', 'value': 'b'},
    ]
    assert [item['value'] for item in combo['frozen']['value']] == [1, 2]


def test_cursor_snapshot_encodes_reference_and_payload(client):
    seeded = RecordingFirestore(documents={'users/u1': {'name': 'Ada'}})
    snapshot = seeded.document('users/u1').get()
    assert isinstance(snapshot, RecordingDocumentSnapshot)
    seeded.collection('c').order_by('updated_at').start_after(snapshot).get()
    cursor = seeded.shapes[0].to_dict()['cursors'][0]
    assert cursor['kind'] == 'start_after'
    assert cursor['value']['type'] == 'snapshot'
    assert cursor['value']['reference'] == 'users/u1'
    assert cursor['value']['value']['name'] == {'type': 'str', 'value': 'Ada'}


def test_order_by_direction_validation(client):
    query = client.collection('c').order_by('a', direction='desc')
    assert query._state.orders == (('a', 'DESCENDING'),)
    with pytest.raises(ValueError, match='unrecognized order_by direction'):
        client.collection('c').order_by('a', direction='sideways')


def test_transaction_kwargs_forward_and_aggregation_get(client):
    transaction = client.transaction(max_attempts=7, read_only=True)
    assert transaction._max_attempts == 7 and transaction._read_only is True

    results = transaction.get(client.collection('c').count(alias='total'))
    rows = list(results)
    assert rows[0][0].alias == 'total' and rows[0][0].value == 0
    assert len(client.shapes) == 1
    assert client.shapes[0].aggregations[0].kind == 'count'


def test_transaction_get_query_consumes_queued_results(client):
    client.queue_results([client.snapshot('users/u1/c/d1', {'v': 1})])
    transaction = client.transaction()
    rows = list(transaction.get(client.collection('users/u1/c').where('v', '==', 1)))
    assert len(rows) == 1 and rows[0].to_dict() == {'v': 1}
    assert client.queued_leftovers() == []
    assert len(client.shapes) == 1


def test_model_dump_and_dataclass_combo_encoding(client):
    @dataclasses.dataclass
    class Combo:
        uid: str

    class Pydanticish:
        def model_dump(self):
            return {'flag': True}

    client.parameter_combo = {'combo': Combo('u1'), 'model': Pydanticish()}
    client.collection('c').get()
    combo = client.shapes[0].to_dict()['parameter_combo']
    assert combo['combo']['value']['uid'] == {'type': 'str', 'value': 'u1'}
    assert combo['model']['value']['flag'] == {'type': 'bool', 'value': True}


@pytest.mark.parametrize(
    'op, value, expected',
    [
        ('==', None, '=='),
        ('!=', None, '!='),
        ('==', float('nan'), '=='),
        ('!=', float('nan'), '!='),
    ],
)
def test_sdk_unary_filter_operators_normalize(client, op, value, expected):
    """SDK unary op_strings (IS_NULL/IS_NOT_NULL/IS_NAN/IS_NOT_NAN) normalize to canonical operators."""
    client.collection('c').where(filter=FieldFilter('f', op, value)).get()
    assert client.shapes[0].filters[0].operator == expected
    assert client.shapes[0].to_dict()['filters'][0]['operator'] == expected


@pytest.mark.parametrize(
    'value, expected',
    [
        (float('nan'), 'NaN'),
        (float('inf'), 'Infinity'),
        (float('-inf'), '-Infinity'),
        (1.5, 1.5),
        (None, None),
    ],
)
def test_encode_value_non_finite_floats_are_json_safe(client, value, expected):
    client.parameter_combo = {'v': value}
    client.collection('c').get()
    encoded = client.shapes[0].to_dict()['parameter_combo']['v']
    assert encoded['value'] == expected
    json.dumps(client.shapes[0].to_dict(), allow_nan=False)
