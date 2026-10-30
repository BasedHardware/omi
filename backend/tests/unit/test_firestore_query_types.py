import pytest

from database.firestore_query_types import (
    FirestoreIndexField,
    FirestoreIndexRequirement,
    FirestoreQueryFilter,
    FirestoreQuerySpec,
)


def test_firestore_index_field_manifest_order():
    field = FirestoreIndexField(field_path='created_at', order='ASCENDING')
    manifest = field.to_manifest()
    assert manifest == {'fieldPath': 'created_at', 'order': 'ASCENDING'}


def test_firestore_index_field_manifest_array_config():
    field = FirestoreIndexField(field_path='tags', array_config='CONTAINS')
    manifest = field.to_manifest()
    assert manifest == {'fieldPath': 'tags', 'arrayConfig': 'CONTAINS'}


def test_firestore_index_field_manifest_missing_order_and_array_config():
    field = FirestoreIndexField(field_path='invalid_field')
    with pytest.raises(ValueError, match='needs order or array_config'):
        field.to_manifest()


def test_firestore_index_requirement_manifest_and_signature():
    f1 = FirestoreIndexField('user_id', order='ASCENDING')
    f2 = FirestoreIndexField('created_at', order='DESCENDING')
    req = FirestoreIndexRequirement(
        identifier='test_req',
        collection_group='conversations',
        query_scope='COLLECTION',
        fields=(f1, f2),
    )
    manifest = req.to_manifest()
    assert manifest['collectionGroup'] == 'conversations'
    assert manifest['queryScope'] == 'COLLECTION'
    assert len(manifest['fields']) == 2
    assert req.signature == (
        'conversations',
        'COLLECTION',
        (('user_id', 'ASCENDING'), ('created_at', 'DESCENDING')),
    )


def test_firestore_query_spec_index_requirement_and_signature():
    f1 = FirestoreIndexField('status', order='ASCENDING')
    q_filter = FirestoreQueryFilter(field_path='status', operator='==', value_name='status_val')
    spec = FirestoreQuerySpec(
        identifier='spec_1',
        collection_group='messages',
        query_scope='COLLECTION_GROUP',
        filters=(q_filter,),
        index_fields=(f1,),
    )
    assert spec.index_requirement.identifier == 'spec_1'
    assert spec.index_requirement.collection_group == 'messages'
    assert spec.query_signature == (
        'messages',
        'COLLECTION_GROUP',
        (('status', '=='),),
    )


def test_firestore_query_spec_build_success():
    class DummyQuery:
        def __init__(self):
            self.filters_applied = []

        def where(self, *, filter):
            self.filters_applied.append(filter)
            return self

    spec = FirestoreQuerySpec(
        identifier='spec_test',
        collection_group='tasks',
        query_scope='COLLECTION',
        filters=(
            FirestoreQueryFilter('user_id', '==', 'user_id_param'),
            FirestoreQueryFilter('status', '==', 'status_param'),
        ),
        index_fields=(),
    )

    query = DummyQuery()
    factory = lambda path, op, val: (path, op, val)
    built = spec.build(
        query,
        {'user_id_param': 'uid_123', 'status_param': 'active'},
        field_filter_factory=factory,
    )

    assert built is query
    assert query.filters_applied == [
        ('user_id', '==', 'uid_123'),
        ('status', '==', 'active'),
    ]


def test_firestore_query_spec_build_missing_value_raises():
    spec = FirestoreQuerySpec(
        identifier='spec_missing',
        collection_group='tasks',
        query_scope='COLLECTION',
        filters=(FirestoreQueryFilter('user_id', '==', 'missing_key'),),
        index_fields=(),
    )
    with pytest.raises(ValueError, match="spec_missing requires 'missing_key'"):
        spec.build(None, {}, field_filter_factory=lambda p, o, v: None)
