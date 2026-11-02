"""Transition replay and terminal audit evidence; all boundaries are hermetic."""

from contextlib import nullcontext
from datetime import datetime, timezone
import hashlib
import json
from unittest.mock import AsyncMock, Mock

import pytest

from tests.unit.test_cap_hold_durability import fragment_sink  # noqa: F401
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.observability import held_content
from utils.sync import cap_hold, live_cap_hold as live, live_cap_tail
from utils.sync.cap_hold_erasure import terminal_receipts


async def test_interleaved_transition_spans_share_a_bounded_tail(fragment_sink, monkeypatch):
    sink, staged, sealed = fragment_sink
    clock = [100.0]
    monkeypatch.setattr(live_cap_tail.time, 'monotonic', lambda: clock[0])
    encoded = []
    encode = live.live_cap_codec.encode

    def capture_pcm(path, pcm, rate, **kwargs):
        encoded.append(pcm)
        return encode(path, pcm, rate, **kwargs)

    monkeypatch.setattr(live.live_cap_codec, 'encode', capture_pcm)
    metric = Mock()
    monkeypatch.setattr(live_cap_tail, 'record_transition_tail', metric)
    # A normal denied suffix, then repeated denied observer callbacks interleaved
    # with the allowed-send/resume flush. The latter used to make five holds.
    await sink.append_async(b'\1\0' * 4000, 100, 1000, 'conversation')
    await sink.flush(force=True)
    start = 1040.0
    for frames in (1, 2, 4, 1, 3):
        await sink.append_async(bytes([frames, 0]) * frames, 100, start, 'conversation')
        await sink.flush(force=True)
        await sink.notice(paused=False)
        start += frames / 100
        clock[0] += 0.1
    assert len(sealed) == 1 and sink.buffered_seconds() == pytest.approx(0.11)
    await sink.close()
    assert len(staged) == len(sealed) == 2
    assert sink.seconds == pytest.approx(40.11)
    expected = b'\1\0' * 4000 + b''.join(bytes([n, 0]) * n for n in (1, 2, 4, 1, 3))
    assert b''.join(encoded) == expected
    assert sum(meta['source_frames'] for _, parts in sealed for meta, _ in parts) == 4011
    assert [call.args[0] for call in metric.call_args_list].count('coalesced') == 4
    assert metric.call_args.args == ('sealed',)


async def test_idle_tail_seals_after_grace_without_more_audio(fragment_sink, monkeypatch):
    sink, staged, sealed = fragment_sink
    clock = [100.0]
    monkeypatch.setattr(live_cap_tail.time, 'monotonic', lambda: clock[0])
    sink.append(b'\1\0' * 160, 16000, 1000, 'conversation')
    await sink.flush(force=True)
    assert not staged and not sealed
    clock[0] += live_cap_tail.GRACE_SECONDS
    await sink.flush()
    assert len(sealed) == 1 and sink.seconds == 0.01
    await sink.close()
    assert len(sealed) == 1


@pytest.mark.parametrize('boundary', ['owner', 'rate', 'month', 'year', 'gap', 'channel'])
async def test_grace_never_joins_incompatible_capture(fragment_sink, boundary):
    sink, staged, sealed = fragment_sink
    month_end = (
        datetime(2027, 1, 1, tzinfo=timezone.utc).timestamp()
        if boundary == 'year'
        else (datetime(2026, 11, 1, tzinfo=timezone.utc).timestamp())
    )
    start = month_end - 0.01 if boundary in {'month', 'year'} else 1000.0
    sealed_count = held_content.TRANSITION_TAIL.labels(outcome='sealed')._value.get()
    coalesced_count = held_content.TRANSITION_TAIL.labels(outcome='coalesced')._value.get()
    sink.append(b'\1\0' * 160, 16000, start, 'a')
    await sink.flush(force=True)
    sink.append(
        b'\2\0' * 160,
        8000 if boundary == 'rate' else 16000,
        start + (0.5 if boundary == 'gap' else 0.01),
        'b' if boundary == 'owner' else 'a',
        1 if boundary == 'channel' else 0,
    )
    await sink.close()
    assert len(sealed) == 2
    assert sum(meta['source_frames'] for _, parts in sealed for meta, _ in parts) == 320
    assert held_content.TRANSITION_TAIL.labels(outcome='sealed')._value.get() == sealed_count + 1
    assert held_content.TRANSITION_TAIL.labels(outcome='coalesced')._value.get() == coalesced_count
    if boundary == 'year':
        assert [meta['live_storage_month'] for _, parts in sealed for meta, _ in parts] == ['2026-12', '2027-01']


async def test_custody_pressure_drains_deferred_tail_before_accepting_more_pcm(fragment_sink, monkeypatch):
    sink, staged, sealed = fragment_sink
    clock = [100.0]
    monkeypatch.setattr(live_cap_tail.time, 'monotonic', lambda: clock[0])
    sink.append(b'\1\0', 100, 1000, 'a', 0)
    await sink.flush(force=True)
    assert sink._tails.deferred == {(0, 100, 'a')}
    sink.append(b'\2\0' * 1499, 100, 1000, 'a', 1)
    assert sink.buffered_seconds() == sink.bound
    flush = AsyncMock(wraps=sink.flush)
    monkeypatch.setattr(sink, 'flush', flush)

    # Aggregate custody is full while one channel still has a deferred 10 ms
    # tail. _packet_parts must bypass grace before accepting this next sample.
    await sink.append_async(b'\3\0', 100, 1014.99, 'a', 1)
    flush.assert_awaited_once_with(force=True, seal=False, final=True)
    assert not sink._tails.deferred
    assert sink.buffered_seconds() == 0.01
    assert any(
        meta['channel'] == 0 and meta['source_frames'] == 1 for parts in staged.values() for meta, _ in parts.values()
    )
    await sink.close()
    assert sum(meta['source_frames'] for _, parts in sealed for meta, _ in parts) == 1501
    assert sink.seconds == pytest.approx(15.01)


def test_final_checkpoint_zeroes_roundoff_in_the_same_transaction(monkeypatch):
    hold_key = ('users', 'synthetic', 'stt_cap_holds', 'hold')
    summary_key = ('users', 'synthetic', 'stt_cap_hold_summary', 'current')
    client = StrictFirestore(
        {
            hold_key: {'state': 'held', 'seconds': 0.1, 'lease_token': 'owner', 'lease_until': 1000},
            summary_key: {'version': 2, 'seconds': 0.100000000000001, 'count': 1},
        }
    )
    monkeypatch.setattr(cap_hold, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(cap_hold, 'ensure_summary', Mock())
    monkeypatch.setattr(cap_hold, 'external_write_fence', lambda uid: nullcontext())
    monkeypatch.setattr(cap_hold.time, 'time', lambda: 100)
    ref = client.document('/'.join(hold_key))
    assert not cap_hold.checkpoint('synthetic', ref, 'stale', {'state': 'completed'})
    assert client.rows[summary_key]['count'] == 1
    assert cap_hold.checkpoint('synthetic', ref, 'owner', {'state': 'completed'})
    assert client.rows[summary_key] == {'version': 2, 'count': 0, 'seconds': 0.0}
    tx = client.transactions[-1]
    assert tx.updates and tx.sets
    assert cap_hold.summary_after({'seconds': 1.1, 'count': 2}, -0.1, -1)['seconds'] == 1.0


def test_terminal_audit_allowlists_outcomes_and_all_destination_evidence():
    secret = 'content-must-not-survive'
    row = {
        'metadata': secret,
        'audio_path': secret,
        'piece_plan': {secret: {'seconds': 20.5, 'audio_path': secret}, 'empty': {'seconds': 0.25}},
        'piece_receipts': {
            secret: {
                'state': 'transcribed',
                'has_content': True,
                'seconds': 20,
                'attempt': 2,
                'provider': 'modulate',
                'provider_result': secret,
                'response': {'new_memories': ['c1']},
            },
            'empty': {
                'state': 'transcribed',
                'has_content': False,
                'seconds': 0,
                'attempt': 1,
                'provider': 'modulate',
                'provider_empty': True,
            },
            'failed': {'state': 'failed_reconciliation', 'seconds': 2, 'attempt': 2, 'provider': 'modulate'},
        },
        'piece_ingests': {
            secret: {
                'conversation_id': 'c2',
                'lineage_anchor': secret,
                'response': {'_merged': {'c3': 'en'}, '_fenced_conversation_ids': ['c4']},
            }
        },
    }
    audit = terminal_receipts(row)
    assert secret not in json.dumps(audit)
    assert audit['conversation_ids'] == ['c1', 'c2', 'c3', 'c4']
    pieces = {piece['piece_id']: piece for piece in audit['pieces']}
    assert pieces[hashlib.sha256(secret.encode()).hexdigest()] == {
        'piece_id': hashlib.sha256(secret.encode()).hexdigest(),
        'outcome': 'transcribed',
        'seconds': 20.5,
        'attempt': 2,
        'provider': 'modulate',
        'conversation_ids': ['c1', 'c2', 'c3', 'c4'],
    }
    assert {piece['outcome'] for piece in audit['pieces']} == {'transcribed', 'settled_empty', 'failed'}
    assert pieces[hashlib.sha256(b'empty').hexdigest()]['seconds'] == 0.25
    assert terminal_receipts({'state': 'purged', 'terminal_receipts': audit}) == audit


def test_empty_vad_plan_retains_source_duration_without_inventing_a_dispatch():
    assert terminal_receipts({'piece_plan': {}, 'seconds': 0.01})['pieces'] == [
        {
            'piece_id': 'source',
            'outcome': 'empty_plan',
            'seconds': 0.01,
            'attempt': 0,
            'provider': None,
            'conversation_ids': [],
        }
    ]
