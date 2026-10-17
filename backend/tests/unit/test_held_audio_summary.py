from datetime import datetime, timezone
from types import SimpleNamespace

from models.users import HeldAudioSummary
from utils.sync import cap_hold
from utils.sync import held_audio_summary as summary


def test_manifest_records_recording_start():
    body = cap_hold.hold_manifest({'audio_path': 'chunks/u/cap-held/a.wav.enc'}, 12.4, 100.0, 1_700_000_000)
    assert body['started_at'] == 1_700_000_000
    assert body['listed_at'] == 1_700_000_000
    assert body['state'] == 'held'
    assert body['seconds'] == 12.4
    assert cap_hold.hold_started_at({'timestamp': 12.9}) == 12
    assert cap_hold.hold_started_at({'timestamp': True}) is None
    assert cap_hold.hold_started_at({}) is None


def test_flag_off_does_not_read_holds(monkeypatch):
    monkeypatch.setattr(summary, 'enabled', lambda: False)

    def explode(uid):
        raise AssertionError('holds were read while dispatch enforcement is off')

    monkeypatch.setattr(summary, '_load_rows', explode)
    monkeypatch.setattr(summary, '_load_summary', explode)
    monkeypatch.setattr(summary, 'funded_allowance', explode)
    assert summary.client_held_audio('synthetic') is None


def test_exhausted_account_lists_holds_and_asks_the_client_to_retain_live(monkeypatch):
    monkeypatch.setattr(summary, 'enabled', lambda: True)
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
    assert result.count == 2
    assert [row.id for row in result.recordings] == ['newer', 'older']
    assert result.reset_at == int(datetime(2026, 11, 1, tzinfo=timezone.utc).timestamp())


def test_funded_account_with_nothing_held_omits_the_field(monkeypatch):
    monkeypatch.setattr(summary, 'enabled', lambda: True)
    assert summary.client_held_audio('synthetic', allowance=SimpleNamespace(managed=True), rows=[]) is None


def test_funded_account_still_reports_audio_already_held(monkeypatch):
    monkeypatch.setattr(summary, 'enabled', lambda: True)
    result = summary.client_held_audio(
        'synthetic',
        allowance=SimpleNamespace(managed=True),
        rows=[{'id': 'held', 'started_at': 50, 'seconds': 15}],
        now=datetime(2026, 10, 17, tzinfo=timezone.utc),
    )
    assert result is not None
    assert result.retain_live is False
    assert result.seconds == 15
    assert result.count == 1


def test_summary_total_is_exact_when_the_page_is_truncated(monkeypatch):
    monkeypatch.setattr(summary, 'enabled', lambda: True)
    result = summary.client_held_audio(
        'synthetic',
        allowance=SimpleNamespace(managed=False),
        summary={'seconds': 9000, 'count': 40},
        rows=[{'id': 'newest', 'started_at': 500, 'seconds': 30}],
        now=datetime(2026, 10, 17, tzinfo=timezone.utc),
    )
    assert result is not None
    assert result.seconds == 9000
    assert result.count == 40
    assert [row.id for row in result.recordings] == ['newest']


def test_positive_count_reads_the_summary_then_one_page(monkeypatch):
    monkeypatch.setattr(summary, 'enabled', lambda: True)
    reads = {'summary': 0, 'rows': 0}

    def load_summary(uid):
        reads['summary'] += 1
        return {'seconds': 40, 'count': 2}

    def load_rows(uid):
        reads['rows'] += 1
        return [{'id': 'a', 'started_at': 2, 'seconds': 10}, {'id': 'b', 'started_at': 1, 'seconds': 30}]

    def explode(*args, **kwargs):
        raise AssertionError('funded_allowance was resolved again')

    monkeypatch.setattr(summary, '_load_summary', load_summary)
    monkeypatch.setattr(summary, '_load_rows', load_rows)
    monkeypatch.setattr(summary, 'funded_allowance', explode)
    result = summary.client_held_audio('synthetic', allowance=SimpleNamespace(managed=False))
    assert reads == {'summary': 1, 'rows': 1}
    assert result is not None and result.seconds == 40 and result.count == 2


def test_empty_summary_does_not_query_holds(monkeypatch):
    monkeypatch.setattr(summary, 'enabled', lambda: True)
    monkeypatch.setattr(summary, '_load_summary', lambda uid: {'seconds': 0, 'count': 0})
    monkeypatch.setattr(summary, '_load_rows', lambda uid: (_ for _ in ()).throw(AssertionError('page was read')))
    assert summary.client_held_audio('synthetic', allowance=SimpleNamespace(managed=True)) is None


def test_plus_anniversary_is_not_the_minute_counter_reset():
    """Legacy Plus billing can end mid-month. The counter still rolls at 00:00 UTC on the 1st."""
    plus = SimpleNamespace(plan='plus', current_period_end=int(datetime(2026, 10, 17, tzinfo=timezone.utc).timestamp()))
    now = datetime(2026, 10, 16, tzinfo=timezone.utc)
    assert summary.plan_reset_at(plus, now) == int(datetime(2026, 11, 1, tzinfo=timezone.utc).timestamp())


def test_subscription_open_kicks_recovery_only_when_dispatch_is_on(monkeypatch):
    kicked = []
    monkeypatch.setattr(summary, 'enabled', lambda: False)

    def kick(uid):
        kicked.append(uid)

    monkeypatch.setattr(summary, '_kick_held_recovery', kick)
    response = SimpleNamespace()
    summary.attach_subscription_held_audio(response, 'synthetic', SimpleNamespace(managed=False))
    assert kicked == []
    assert not hasattr(response, 'held_audio') or response.held_audio is None

    monkeypatch.setattr(summary, 'enabled', lambda: True)
    monkeypatch.setattr(summary, '_load_summary', lambda uid: {'seconds': 5, 'count': 1})
    monkeypatch.setattr(summary, '_load_rows', lambda uid: [{'id': 'a', 'started_at': 9, 'seconds': 5}])
    summary.attach_subscription_held_audio(response, 'synthetic', SimpleNamespace(managed=False))
    assert kicked == ['synthetic']
    assert response.held_audio.seconds == 5


def test_partial_receipts_and_retries_adjust_summary_under_lease(monkeypatch):
    from contextlib import nullcontext
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

    key = ('users', 'synthetic', 'stt_cap_holds', 'a')
    total_key = ('users', 'synthetic', 'stt_cap_hold_summary', 'current')
    client = StrictFirestore(
        {
            key: {'state': 'held', 'lease_until': 1000, 'lease_token': 'owner', 'seconds': 80},
            total_key: {'version': 2, 'seconds': 80, 'count': 1},
        }
    )
    monkeypatch.setattr(cap_hold, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(cap_hold, 'external_write_fence', lambda uid: nullcontext())
    monkeypatch.setattr(cap_hold.time, 'time', lambda: 100)
    ref = client.document('/'.join(key))
    # VAD planned only 60s; discarded silence ceases to be waiting.
    assert cap_hold.checkpoint('synthetic', ref, 'owner', {'piece_plan': {'a': {'seconds': 20}, 'b': {'seconds': 40}}})
    assert client.rows[total_key]['seconds'] == 60
    for _ in range(2):
        assert cap_hold.checkpoint('synthetic', ref, 'owner', {'piece_receipts': {'a': {'state': 'transcribed'}}})
        assert client.rows[total_key]['seconds'] == 40
    assert not cap_hold.checkpoint('synthetic', ref, 'stale', {'state': 'completed'})
    assert cap_hold.checkpoint(
        'synthetic',
        ref,
        'owner',
        {
            'piece_receipts': {'a': {'state': 'transcribed'}, 'b': {'state': 'failed_reconciliation'}},
            'failed_reconciliation': True,
            'state': 'completed',
        },
    )
    assert client.rows[total_key] == {'version': 2, 'seconds': 40, 'count': 1}
    assert cap_hold.checkpoint('synthetic', ref, 'owner', {'state': 'retained'})
    assert client.rows[total_key]['seconds'] == 40


def test_fractional_pieces_do_not_accumulate_rounding_drift(monkeypatch):
    assert cap_hold.summary_after({'seconds': 0.4, 'count': 1}, 0.4, 1)['seconds'] == 0.8
    assert cap_hold.remaining_seconds({'state': 'held', 'piece_plan': {}, 'seconds': 80}) == 0
