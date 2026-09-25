import json
import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key-not-real")
os.environ.setdefault("PINECONE_API_KEY", "test-pinecone-key-not-real")

import routers.apps as apps

MARKDOWN = '# Setup\n1. Open settings\n2. Paste your key'


def _run_update(monkeypatch, instructions):
    stored = {
        'id': 'app-1',
        'uid': 'owner',
        'approved': False,
        'private': True,
        'external_integration': {
            'triggers_on': 'memory_creation',
            'webhook_url': 'https://example.com/hook',
            'setup_instructions_file_path': MARKDOWN,
            'is_instructions_url': False,
        },
    }
    written = {}
    monkeypatch.setattr(apps, 'get_available_app_by_id', lambda app_id, uid: stored)
    monkeypatch.setattr(apps, 'update_app_in_db', lambda data: written.update(data))
    monkeypatch.setattr(apps, 'upsert_app_payment_link', lambda *a, **k: None)
    monkeypatch.setattr(apps, 'delete_app_cache_by_id', lambda *a, **k: None)
    monkeypatch.setattr(apps, 'invalidate_approved_apps_cache', lambda *a, **k: None)
    payload = {
        'id': 'app-1',
        'name': 'Renamed',
        'external_integration': {
            'triggers_on': 'memory_creation',
            'webhook_url': 'https://example.com/hook',
            'setup_instructions_file_path': instructions,
            'app_home_url': '',
            'chat_tools_manifest_url': '',
            'auth_steps': [],
        },
    }
    apps.update_app('app-1', app_data=json.dumps(payload), file=None, uid='owner')
    return written['external_integration']


def test_editing_app_keeps_inline_markdown_instructions_flag(monkeypatch):
    ext = _run_update(monkeypatch, MARKDOWN)
    assert ext.get('is_instructions_url') is False


def test_editing_app_marks_url_instructions(monkeypatch):
    ext = _run_update(monkeypatch, ' https://example.com/setup ')
    assert ext.get('is_instructions_url') is True
    assert ext['setup_instructions_file_path'] == 'https://example.com/setup'
