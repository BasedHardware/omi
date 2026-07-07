"""Marketplace list builders must skip a malformed app record, not 500 the whole listing.

get_popular_apps / get_available_apps / get_approved_available_apps build App(**doc) in a loop
over raw Firestore docs. The listings are shared and Redis/process-cached across all users, so
one malformed or legacy app document previously raised ValidationError and 500'd the entire page
for everyone. _safe_build_app skips such a record (returns None) and logs its id + field names.

The helper is a pure function, so the test imports and calls it directly (functional core, no
monkeypatch, no sys.modules).
"""

import os

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

import utils.apps as apps_utils  # noqa: E402
from models.app import App  # noqa: E402


def _valid_app_dict():
    return {
        'id': 'app1',
        'name': 'Test App',
        'category': 'productivity',
        'author': 'Someone',
        'description': 'Does things',
        'image': 'http://img',
        'capabilities': ['chat'],
    }


def test_safe_build_app_returns_app_for_valid_record():
    built = apps_utils._safe_build_app(_valid_app_dict())
    assert isinstance(built, App)
    assert built.id == 'app1'


def test_safe_build_app_skips_record_missing_required_fields():
    # A legacy doc missing required fields (name/category/author/...) is skipped, not raised.
    assert apps_utils._safe_build_app({'id': 'broken'}) is None


def test_safe_build_app_skips_empty_record():
    assert apps_utils._safe_build_app({}) is None


def test_safe_build_app_valid_record_survives_next_to_a_poison_one():
    # A poison record between good ones must not take the whole batch down.
    records = [_valid_app_dict(), {'id': 'broken'}, {**_valid_app_dict(), 'id': 'app2'}]
    built = [a for a in (apps_utils._safe_build_app(r) for r in records) if a is not None]
    assert [a.id for a in built] == ['app1', 'app2']
