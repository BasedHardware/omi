"""Media consumer filtering invokes the real recap producer and public helpers."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest

from utils.other import notifications as notif
from utils.llm import external_integrations as recap
from tests.unit.test_daily_summary_generation import _install_generation_fakes, _FakeConvo


@pytest.mark.parametrize('mode,expected', [('off', 1), ('shadow', 1), ('serve', 0)])
def test_daily_generation_filters_media_before_paid_work(monkeypatch, mode, expected):
    monkeypatch.setenv('MEDIA_NOISE_MODE', mode)
    monkeypatch.setenv('MEDIA_NOISE_MODE_SERVE_PERCENT', '0')
    monkeypatch.delenv('MEDIA_NOISE_MODE_SERVE_UID_SHA256S', raising=False)
    monkeypatch.setenv('NOTES_PACKET_V2_MODE', 'off')
    generated, created, _, released, _ = _install_generation_fakes(monkeypatch)
    media = _FakeConvo()
    media.content_kind = 'media'
    monkeypatch.setattr(notif, 'deserialize_conversations', lambda _: [media])
    monkeypatch.setattr(notif.daily_summaries_db, 'set_daily_summary_generation_status', MagicMock())
    start = datetime(2026, 10, 20, tzinfo=timezone.utc)
    notif.generate_and_store_daily_summary('synthetic', '2026-10-20', start, start + timedelta(days=1))
    assert len(generated) == len(created) == expected
    if not expected:
        assert released == ['2026-10-20']


def test_standalone_recap_entrypoints_skip_all_excluded_before_compute(monkeypatch):
    monkeypatch.setenv('MEDIA_NOISE_MODE', 'serve')
    compute = MagicMock(side_effect=AssertionError('paid generation escaped'))
    monkeypatch.setattr(recap, 'require_generated_compute', compute)
    rows = [SimpleNamespace(content_kind='noise'), SimpleNamespace(content_kind='media')]
    assert recap.get_conversation_summary('synthetic', rows) == ''
    assert recap.generate_comprehensive_daily_summary('synthetic', rows, '2026-10-20', None, None) == {}
    compute.assert_not_called()
