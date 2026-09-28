import json
import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key-not-real")
os.environ.setdefault("PINECONE_API_KEY", "test-pinecone-key-not-real")

from routers import apps
from models.app import App


def _run_update(monkeypatch, payload, stored=None):
    if stored is None:
        stored = {
            'id': 'app-1',
            'uid': 'owner',
            'name': 'Original Name',
            'category': 'productivity',
            'author': 'Original Author',
            'description': 'Original Description',
            'image': 'https://example.com/logo.png',
            'capabilities': ['chat'],
            'approved': False,
            'private': True,
            'source_code_url': 'https://github.com/original/repo',
        }
    written = {}
    monkeypatch.setattr(apps, 'get_available_app_by_id', lambda app_id, uid: dict(stored))
    monkeypatch.setattr(apps, 'update_app_in_db', lambda data: written.update(data))
    monkeypatch.setattr(apps, 'upsert_app_payment_link', lambda *a, **k: None)
    monkeypatch.setattr(apps, 'delete_app_cache_by_id', lambda *a, **k: None)
    monkeypatch.setattr(apps, 'invalidate_approved_apps_cache', lambda *a, **k: None)

    payload_with_id = {'id': 'app-1', **payload}
    apps.update_app('app-1', app_data=json.dumps(payload_with_id), file=None, uid='owner')
    return written


def test_patch_drops_explicit_null_on_required_fields(monkeypatch):
    """Explicit null on required non-nullable fields must be dropped so stored values are not overwritten."""
    payload = {
        'name': None,
        'category': None,
        'author': None,
        'description': None,
        'image': None,
        'capabilities': None,
    }
    written = _run_update(monkeypatch, payload)

    for field in ('name', 'category', 'author', 'description', 'image', 'capabilities'):
        assert field not in written, f"Expected {field} to be dropped from update payload, but was present"


def test_patch_preserves_explicit_null_on_optional_fields(monkeypatch):
    """Explicit null on optional fields must pass through to allow clearing stored values."""
    payload = {
        'source_code_url': None,
        'email': None,
        'memory_prompt': None,
    }
    written = _run_update(monkeypatch, payload)

    assert 'source_code_url' in written
    assert written['source_code_url'] is None
    assert 'email' in written
    assert written['email'] is None
    assert 'memory_prompt' in written
    assert written['memory_prompt'] is None


def test_patch_updates_real_values_for_required_fields(monkeypatch):
    """Real non-null values for required fields must update normally."""
    payload = {
        'name': 'Updated Name',
        'category': 'utilities',
        'description': 'Updated Description',
    }
    written = _run_update(monkeypatch, payload)

    assert written.get('name') == 'Updated Name'
    assert written.get('category') == 'utilities'
    assert written.get('description') == 'Updated Description'


def test_patch_mixed_null_required_and_null_optional(monkeypatch):
    """Mixed payloads drop nulls for required fields while keeping updates and optional nulls."""
    payload = {
        'name': None,
        'description': 'Updated Description',
        'source_code_url': None,
    }
    written = _run_update(monkeypatch, payload)

    assert 'name' not in written
    assert written.get('description') == 'Updated Description'
    assert 'source_code_url' in written
    assert written['source_code_url'] is None


def test_patch_does_not_poison_stored_app_model(monkeypatch):
    """End-to-end check: applying the PATCH update to stored document must produce a valid App."""
    stored = {
        'id': 'app-1',
        'uid': 'owner',
        'name': 'Original Name',
        'category': 'productivity',
        'author': 'Original Author',
        'description': 'Original Description',
        'image': 'https://example.com/logo.png',
        'capabilities': ['chat'],
        'approved': False,
        'private': True,
    }
    # Client sends nulls on some required fields
    payload = {
        'category': None,
        'author': None,
        'description': None,
    }
    written = _run_update(monkeypatch, payload, stored=stored)

    # Simulate Firestore document update
    merged = dict(stored)
    merged.update(written)

    # App model must validate without raising ValidationError
    app = App(**merged)
    assert app.name == 'Original Name'
    assert app.category == 'productivity'
    assert app.author == 'Original Author'
    assert app.description == 'Original Description'


def test_update_app_in_db_drops_explicit_null_required_fields(monkeypatch):
    """database.apps:update_app_in_db must drop explicit-null required fields before writing to Firestore."""
    from unittest.mock import MagicMock
    from database import apps as apps_db

    written = {}
    mock_doc = MagicMock()
    mock_doc.update.side_effect = lambda data: written.update(data)
    mock_collection = MagicMock()
    mock_collection.document.return_value = mock_doc
    mock_db = MagicMock()
    mock_db.collection.return_value = mock_collection

    monkeypatch.setattr(apps_db, 'db', mock_db)

    payload = {
        'id': 'app-1',
        'name': None,
        'category': None,
        'author': None,
        'description': None,
        'image': None,
        'capabilities': None,
        'memory_prompt': None,
    }
    apps_db.update_app_in_db(payload)

    for field in ('name', 'category', 'author', 'description', 'image', 'capabilities'):
        assert field not in written
    assert 'memory_prompt' in written
    assert written['memory_prompt'] is None

