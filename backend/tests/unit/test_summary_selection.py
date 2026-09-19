"""Backend conformance for the shared single-body summary projection."""

from __future__ import annotations

import json
from pathlib import Path

from utils.conversations.summary_selection import render_sections_markdown, select_primary_summary

ROOT_DIR = Path(__file__).resolve().parents[3]


def _fixture() -> dict:
    return json.loads((ROOT_DIR / 'contracts' / 'parity' / 'conversation_summary.json').read_text(encoding='utf-8'))


def test_summary_fixture_is_complete_and_uses_one_primary_body():
    fixture = _fixture()
    assert fixture['schema_version'] == 1
    cases = fixture['cases']
    assert len(cases) == len({case['id'] for case in cases})
    assert cases

    for case in cases:
        expected = case['expected']
        assert expected['kind'] in {'app', 'overview', 'sections', 'empty'}
        assert isinstance(expected['content'], str)
        assert set(expected) == {'kind', 'content', 'app_id', 'result_index'}
        selected = select_primary_summary(case['conversation'])
        assert selected.kind == expected['kind'], case['id']
        assert selected.content == expected['content'], case['id']
        assert selected.app_id == expected['app_id'], case['id']
        assert selected.result_index == expected['result_index'], case['id']


def test_section_renderer_omits_empty_sections_and_preserves_order():
    sections = [
        {'heading': 'First', 'body_markdown': 'Body one'},
        {'heading': 'Empty body', 'body_markdown': ' '},
        {'heading': '', 'body_markdown': 'Body two'},
        {'heading': 'Third', 'body_markdown': 'Body three'},
    ]

    assert render_sections_markdown(sections) == '## First\n\nBody one\n\nBody two\n\n## Third\n\nBody three'


def test_summary_share_email_uses_the_same_primary_selection(monkeypatch):
    from utils.conversations import share_email

    captured = {}

    class _Response:
        status_code = 200

    def fake_post(_url, *, json, headers, timeout):
        captured['json'] = json
        return _Response()

    monkeypatch.setenv('RESEND_API_KEY', 'test-key')
    monkeypatch.setattr(
        share_email, 'get_user_from_uid', lambda _uid: {'email': 'owner@example.com', 'display_name': 'Owner'}
    )
    monkeypatch.setattr(share_email.httpx, 'post', fake_post)

    share_email.send_summary_email(
        uid='user-1',
        conversation={
            'id': 'conv-1',
            'structured': {'title': 'Meeting', 'overview': 'Edited overview', 'sections': []},
            'apps_results': [{'app_id': None, 'content': 'Imported app result'}],
        },
        recipient_emails=['guest@example.com'],
    )

    assert 'Imported app result' in captured['json']['html']
    assert 'Edited overview' not in captured['json']['html']
