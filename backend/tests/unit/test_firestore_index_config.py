import json
from pathlib import Path


def _index_specs():
    path = Path(__file__).resolve().parents[3] / 'firestore.indexes.json'
    return json.loads(path.read_text())['indexes']


def _fields(index):
    return [(field.get('fieldPath'), field.get('order')) for field in index['fields']]


def test_firestore_config_declares_memory_items_canary_read_index():
    required_fields = [
        ('uid', 'ASCENDING'),
        ('generation', 'ASCENDING'),
        ('updated_at', 'DESCENDING'),
        ('__name__', 'ASCENDING'),
    ]

    assert any(
        index.get('collectionGroup') == 'memory_items'
        and index.get('queryScope') == 'COLLECTION_GROUP'
        and _fields(index) == required_fields
        for index in _index_specs()
    )


def test_firestore_config_does_not_declare_same_direction_single_field_composites():
    # Firestore auto-serves field+__name__ when both orders match (ASC+ASC /
    # DESC+DESC). Declaring those is rejected as redundant. Opposite-direction
    # pairs (e.g. updated_at DESC + __name__ ASC) are real composites and must
    # stay in the manifest (#11684).
    for index in _index_specs():
        fields = _fields(index)
        non_name = [(path, order) for path, order in fields if path != '__name__']
        name = [(path, order) for path, order in fields if path == '__name__']
        if len(non_name) != 1 or len(name) != 1:
            continue
        (_, field_order), (_, name_order) = non_name[0], name[0]
        if field_order is None or name_order is None:
            continue
        assert field_order != name_order, index


def test_firestore_config_declares_opposite_direction_universal_list_scans():
    # Prod GET /v3/memories 503ed because these were omitted from the manifest.
    required = [
        (
            'memory_items',
            'COLLECTION',
            (('updated_at', 'DESCENDING'), ('__name__', 'ASCENDING')),
        ),
        (
            'memories',
            'COLLECTION',
            (('updated_at', 'DESCENDING'), ('__name__', 'ASCENDING')),
        ),
        (
            'memories',
            'COLLECTION',
            (('created_at', 'DESCENDING'), ('__name__', 'ASCENDING')),
        ),
        (
            'memory_review_queue',
            'COLLECTION',
            (('status', 'ASCENDING'), ('__name__', 'DESCENDING')),
        ),
    ]
    specs = {
        (
            index.get('collectionGroup'),
            index.get('queryScope'),
            tuple(_fields(index)),
        )
        for index in _index_specs()
    }
    for collection, scope, fields in required:
        assert (collection, scope, fields) in specs


def test_firestore_config_declares_mcp_conversation_category_filter_index():
    required_fields = [
        ('discarded', 'ASCENDING'),
        ('status', 'ASCENDING'),
        ('structured.category', 'ASCENDING'),
        ('created_at', 'DESCENDING'),
        ('__name__', 'DESCENDING'),
    ]

    assert any(
        index.get('collectionGroup') == 'conversations'
        and index.get('queryScope') == 'COLLECTION'
        and _fields(index) == required_fields
        for index in _index_specs()
    )


def test_firestore_config_declares_screen_activity_app_filter_index():
    # Regression for #9189: the MCP get_screen_activity tool filters by appName
    # and orders/ranges on timestamp, which needs this composite index — without
    # it Firestore raises FailedPrecondition and the tool returned an opaque 500.
    required_fields = [
        ('appName', 'ASCENDING'),
        ('timestamp', 'ASCENDING'),
        ('__name__', 'ASCENDING'),
    ]

    assert any(
        index.get('collectionGroup') == 'screen_activity'
        and index.get('queryScope') == 'COLLECTION'
        and _fields(index) == required_fields
        for index in _index_specs()
    )
