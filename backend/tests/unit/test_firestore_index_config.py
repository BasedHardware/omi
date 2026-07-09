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


def test_firestore_config_declares_v3_compatibility_projection_index():
    required_fields = [
        ('created_at', 'DESCENDING'),
        ('__name__', 'DESCENDING'),
    ]

    assert any(
        index.get('collectionGroup') == 'v3_compatibility_projection_items'
        and index.get('queryScope') == 'COLLECTION'
        and _fields(index) == required_fields
        for index in _index_specs()
    )


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
