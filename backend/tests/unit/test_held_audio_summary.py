from datetime import datetime, timezone
from types import SimpleNamespace

from models.users import HeldAudioSummary
from utils.sync import cap_hold
from utils.sync import held_audio_summary as summary


def test_manifest_records_recording_start():
    body = cap_hold.hold_manifest({'audio_path': 'chunks/u/cap-held/a.wav.enc'}, 12.4, 100.0, 1_700_000_000)
    assert body['started_at'] == 1_700_000_000
    assert body['state'] == 'held'
    assert body['seconds'] == 12.4
    assert cap_hold.hold_started_at({'timestamp': 12.9}) == 12
    assert cap_hold.hold_started_at({'timestamp': True}) is None
    assert cap_hold.hold_started_at({}) is None


def test_flag_off_does_not_read_holds(monkeypatch):
    monkeypatch.setattr(summary, 'execution_admission_enabled', lambda: False)

    def explode(uid):
        raise AssertionError('holds were read while admission is off')

    monkeypatch.setattr(summary, '_load_rows', explode)
    assert summary.client_held_audio('synthetic') is None


def test_exhausted_account_lists_holds_and_asks_the_client_to_retain_live(monkeypatch):
    monkeypatch.setattr(summary, 'execution_admission_enabled', lambda: True)
    now = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)
    result = summary.client_held_audio(
        'synthetic',
        allowance=SimpleNamespace(managed=False),
        rows=[
            {'id': 'older', 'started_at': 100, 'seconds': 30},
            {'id': 'newer', 'started_at': 200, 'seconds': 90},
            {'id': 'empty', 'started_at': 300, 'seconds': 0},
        ],
        now=now,
    )
    assert isinstance(result, HeldAudioSummary)
    assert result.retain_live is True
    assert result.seconds == 120
    assert [row.id for row in result.recordings] == ['newer', 'older']
    assert result.reset_at == int(datetime(2026, 11, 1, tzinfo=timezone.utc).timestamp())


def test_funded_account_with_nothing_held_omits_the_field(monkeypatch):
    monkeypatch.setattr(summary, 'execution_admission_enabled', lambda: True)
    assert summary.client_held_audio('synthetic', allowance=SimpleNamespace(managed=True), rows=[]) is None


def test_funded_account_still_reports_audio_already_held(monkeypatch):
    monkeypatch.setattr(summary, 'execution_admission_enabled', lambda: True)
    result = summary.client_held_audio(
        'synthetic',
        allowance=SimpleNamespace(managed=True),
        rows=[{'id': 'held', 'started_at': 50, 'seconds': 15}],
        now=datetime(2026, 10, 17, tzinfo=timezone.utc),
    )
    assert result is not None
    assert result.retain_live is False
    assert result.seconds == 15
