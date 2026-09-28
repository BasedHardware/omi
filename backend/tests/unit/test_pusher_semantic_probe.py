from __future__ import annotations
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'pusher_semantic_probe.py'


def test_alignment_probe_rejects_repeated_live_fixture(probe):
    fixture = probe.load_fixture()
    phrase = fixture.expected_phrase
    observed, expected = probe._alignment_word_counts(
        [{'text': phrase}, {'text': phrase}], phrase, probe.ALIGNMENT_AUDIO_PASSES
    )
    assert (observed, expected) == (34, 34)
    assert probe._alignment_word_count_ok(observed, expected)
    for repeats in (4, 8):
        observed, expected = probe._alignment_word_counts(
            [{'text': phrase}] * repeats, phrase, probe.ALIGNMENT_AUDIO_PASSES
        )
        assert not probe._alignment_word_count_ok(observed, expected)
    receipt = probe._alignment_receipt(
        status='FAIL',
        started_at='2026-09-26T00:00:00Z',
        failure_stage='transcript_word_count',
        live_word_count=137,
        expected_word_count=34,
    )
    assert receipt['word_counts'] == {'live': 137, 'expected': 34}
    assert phrase not in str(receipt)


def test_qualification_probe_bounds_one_conversation_with_eight_fixture_sends(probe):
    phrase = probe.load_fixture().expected_phrase
    fixture_words = len(phrase.split())
    for passes, passed in ((1, False), (4, True), (6, True), (8, True)):
        observed, expected = probe._alignment_word_counts(
            [{'text': phrase}] * passes, phrase, probe.DISCARD_KEEP_AUDIO_PASSES
        )
        assert expected == 136
        assert probe._base_word_count_ok(observed, expected, fixture_words) is passed
    # The readback's phrase check proves one pass; the word-count floor
    # requires four. The upper bound rejects duplicate transcripts.
    assert not probe._base_word_count_ok(0, expected, fixture_words)
    assert not probe._base_word_count_ok(272, expected, fixture_words)


@pytest.mark.asyncio
@pytest.mark.parametrize(('passes', 'passed'), [(1, False), (4, True), (6, True), (10, False)])
async def test_base_probe_records_counts_when_rollover_or_duplication_changes_the_readback(
    monkeypatch, probe, tmp_path, passes, passed
):
    phrase = probe.load_fixture().expected_phrase
    monkeypatch.setattr(probe, '_read_token', lambda *_: 'token')

    async def held_listen(*_args, hold_open, **_kwargs):
        await hold_open.wait()
        return True, ''

    monkeypatch.setattr(probe, '_listen_sample', held_listen)
    monkeypatch.setattr(
        probe,
        '_terminal_readback',
        lambda *_a, **_k: asyncio.sleep(0, result={'transcript_segments': [{'text': phrase}] * passes}),
    )
    monkeypatch.setattr(probe, '_observe_candidate_pusher', lambda *_a, **_k: asyncio.sleep(0, result=1))
    deployment_receipt = tmp_path / 'deployment.json'
    deployment_receipt.write_text(json.dumps({'image': {'digest': 'sha256:synthetic'}}))
    args = SimpleNamespace(
        run_id='123',
        bearer_token_file=tmp_path / 'token',
        deployment_receipt=deployment_receipt,
        api_url='https://example.invalid',
        allow_local_http=False,
        finalization_timeout_seconds=1,
        project='synthetic',
        namespace='synthetic',
    )

    receipt, actual_passed = await probe.run_probe(args)

    assert actual_passed is passed
    assert receipt['word_counts'] == {'live': 17 * passes, 'expected': 136}
    assert receipt['consumer_readback'] == {'status': 'PASS'}
    assert receipt.get('failure_stage') == (None if passed else 'transcript_word_count')


@pytest.mark.asyncio
async def test_base_probe_reports_terminal_stt_socket_death_before_readback_timeout(monkeypatch, probe, tmp_path):
    """A 1011 listen failure cannot masquerade as a finalization timeout."""
    from websockets.frames import Close

    monkeypatch.setattr(probe, '_read_token', lambda *_: 'token')

    async def failed_listen(*_args, **_kwargs):
        await asyncio.sleep(0)
        raise probe.websockets.exceptions.ConnectionClosedError(Close(1011, 'provider details'), None)

    async def waiting_readback(*_args, **_kwargs):
        await asyncio.sleep(3600)
        pytest.fail('readback unexpectedly finished')

    monkeypatch.setattr(probe, '_listen_sample', failed_listen)
    monkeypatch.setattr(probe, '_terminal_readback', waiting_readback)
    deployment_receipt = tmp_path / 'deployment.json'
    deployment_receipt.write_text(json.dumps({'image': {'digest': 'sha256:synthetic'}}))
    args = SimpleNamespace(
        run_id='123',
        bearer_token_file=tmp_path / 'token',
        deployment_receipt=deployment_receipt,
        api_url='https://example.invalid',
        allow_local_http=False,
        finalization_timeout_seconds=180,
        project='synthetic',
        namespace='synthetic',
    )

    receipt, passed = await asyncio.wait_for(probe.run_probe(args), timeout=1)

    assert not passed
    assert receipt['failure_stage'] == 'stt_unavailable'
    assert receipt['consumer_readback'] == {'status': 'FAIL'}
    assert 'provider details' not in json.dumps(receipt)


def test_base_probe_status_line_exposes_only_bounded_diagnostics(monkeypatch, probe, tmp_path, capsys):
    receipt = probe._receipt(
        status='FAIL',
        evidence_id='pusher-dev-123-synthetic',
        deployment_receipt={},
        deployment_receipt_sha256='',
        started_at='2026-09-27T00:00:00Z',
        ended_at='2026-09-27T00:00:01Z',
        candidate_pod_count=0,
        failure_stage='transcript_word_count',
        live_word_count=17,
        expected_word_count=136,
        consumer_readback_passed=True,
    )
    receipt['private_extra'] = 'secret transcript token endpoint uid'
    monkeypatch.setattr(
        probe, 'parse_args', lambda *_: SimpleNamespace(output=tmp_path / 'receipt.json', alignment_scenario=False)
    )
    monkeypatch.setattr(probe, 'run_probe', lambda *_: asyncio.sleep(0, result=(receipt, False)))

    assert probe.main([]) == 1
    line = capsys.readouterr().out.strip()
    assert 'failure_stage=transcript_word_count' in line
    assert 'word_counts_live=17 word_counts_expected=136' in line
    assert 'consumer_readback=PASS candidate_pod_count=0' in line
    assert 'secret' not in line
    assert 'transcript token endpoint uid' not in line


@pytest.fixture
def probe(monkeypatch):
    spec = importlib.util.spec_from_file_location('pusher_semantic_probe_test_target', SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_terminal_readback_requires_completed_successful_fanout(monkeypatch, probe):
    responses = iter(
        [
            (
                200,
                {
                    'status': 'completed',
                    'terminal': True,
                    'terminal_outcome': 'success',
                    'fanout_status': 'completed',
                },
            ),
            (200, {'id': 'conversation-1', 'status': 'completed', 'transcript_segments': [{'text': 'hello'}]}),
        ]
    )
    monkeypatch.setattr(probe, '_http_json', lambda *_args: next(responses))

    await probe._terminal_readback('https://api.example.invalid', 'token', 'conversation-1', 1)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('terminal_outcome', 'fanout_status'),
    [('stale', 'fenced'), ('failure', 'fenced'), ('success', 'leased'), ('unknown', 'unknown')],
)
async def test_terminal_readback_rejects_completed_without_successful_fanout(
    monkeypatch, probe, terminal_outcome: str, fanout_status: str
):
    monkeypatch.setattr(
        probe,
        '_http_json',
        lambda *_args: (
            200,
            {
                'status': 'completed',
                'terminal': True,
                'terminal_outcome': terminal_outcome,
                'fanout_status': fanout_status,
            },
        ),
    )
    with pytest.raises(probe.ProbeError, match='terminal_failure'):
        await probe._terminal_readback('https://api.example.invalid', 'token', 'conversation-1', 1)


class _FailoverListenSocket:
    """A /v4/listen socket whose final segment lands late, after one failover.

    Early segments are available immediately; the final segment becomes
    available only once the (fake) clock passes stream_end + late_after,
    mimicking the successor provider's end-of-speech flush timer that fired
    seconds after the probe's old 5s tail closed (dev runs 35513163118,
    35517257170, and the 14:41 cancelled-run probe: transcript_mismatch 3/3).
    """

    def __init__(self, conversation_id: str, late_after: float, clock: list[float]) -> None:
        self._clock = clock
        self._late_after = late_after
        self._stream_ended_at: float | None = None
        self._early = [
            {'type': 'conversation_session', 'conversation_id': conversation_id},
            {'type': 'service_status', 'status': 'ready'},
            {'segments': [{'text': 'He began a confused'}]},
        ]
        self._late = {'segments': [{'text': 'complaint against the wizard'}]}
        self.closed = False

    async def recv(self) -> str:
        if self._early:
            return json.dumps(self._early.pop(0))
        if (
            self._late is not None
            and self._stream_ended_at is not None
            and self._clock[0] >= self._stream_ended_at + self._late_after
        ):
            payload, self._late = self._late, None
            return json.dumps(payload)
        # Yield so the timeline (and cancellation) can advance while idle.
        await asyncio.sleep(0)
        raise asyncio.TimeoutError

    async def send(self, _chunk: bytes) -> None:
        self._stream_ended_at = self._clock[0]

    async def close(self, code: int = 1000, reason: str = '') -> None:
        self.closed = True


class _FakeConnect:
    def __init__(self, socket: _FailoverListenSocket) -> None:
        self._socket = socket

    async def __aenter__(self) -> _FailoverListenSocket:
        return self._socket

    async def __aexit__(self, *_exc: object) -> bool:
        return False


def _install_fake_timeline(monkeypatch: pytest.MonkeyPatch, probe, clock: list[float]) -> None:
    real_sleep = probe.asyncio.sleep

    async def fake_sleep(delay: float) -> None:
        clock[0] += delay
        await real_sleep(0)

    async def fake_wait_for(awaitable, timeout: float | None = None):
        return await awaitable

    monkeypatch.setattr(probe.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(probe.asyncio, 'sleep', fake_sleep)
    monkeypatch.setattr(probe.asyncio, 'wait_for', fake_wait_for)


@pytest.mark.asyncio
@pytest.mark.parametrize('late_after', [12.0])
async def test_listen_sample_collects_a_final_segment_that_lands_after_one_failover(
    monkeypatch, probe, late_after: float
):
    """The final segment of a failover-recovered session lands seconds past the
    old 5s tail (12s here) but inside the failover-tolerant collection window;
    the probe must still accept it."""
    clock = [0.0]
    socket = _FailoverListenSocket('conversation-1', late_after, clock)
    _install_fake_timeline(monkeypatch, probe, clock)
    monkeypatch.setattr(probe.websockets, 'connect', lambda *_a, **_k: _FakeConnect(socket))
    fixture = probe.Fixture(
        pcm=b'\x00' * (16000 * 2 * 3),  # three full 100ms chunks
        sample_rate=16000,
        expected_phrase='he began a confused complaint against the wizard',
    )

    await probe._listen_sample('https://api.example.invalid', 'token', fixture, 'conversation-1')

    assert socket.closed


@pytest.mark.asyncio
async def test_listen_sample_still_fails_closed_when_the_phrase_never_lands(monkeypatch, probe):
    """A provider that never delivers the phrase must keep failing the probe:
    the live window reports no match, and the durable readback rejects a
    completed conversation whose transcript lacks the fixture phrase."""
    clock = [0.0]
    socket = _FailoverListenSocket('conversation-1', 90.0, clock)
    _install_fake_timeline(monkeypatch, probe, clock)
    monkeypatch.setattr(probe.websockets, 'connect', lambda *_a, **_k: _FakeConnect(socket))
    fixture = probe.Fixture(
        pcm=b'\x00' * (16000 * 2 * 3),
        sample_rate=16000,
        expected_phrase='he began a confused complaint against the wizard',
    )

    matched, transcript = await probe._listen_sample('https://api.example.invalid', 'token', fixture, 'conversation-1')

    assert matched is False
    # The failover socket delivered a partial early segment only; the phrase
    # as a whole never landed inside the live window.
    assert 'complaint against the wizard' not in transcript
    # The socket closes gracefully; acceptance is decided by the durable
    # readback below, not by the live window.
    assert socket.closed

    responses = iter(
        [
            (
                200,
                {
                    'status': 'completed',
                    'terminal': True,
                    'terminal_outcome': 'success',
                    'fanout_status': 'completed',
                },
            ),
            (
                200,
                {'id': 'conversation-1', 'status': 'completed', 'transcript_segments': [{'text': 'unrelated words'}]},
            ),
        ]
    )
    monkeypatch.setattr(probe, '_http_json', lambda *_args: next(responses))
    with pytest.raises(probe.ProbeError, match='transcript_mismatch'):
        await probe._terminal_readback(
            'https://api.example.invalid', 'token', 'conversation-1', 1, expected_phrase=fixture.expected_phrase
        )


@pytest.mark.asyncio
async def test_listen_sample_reports_bounded_stt_failure_event(monkeypatch, probe):
    clock = [0.0]
    socket = _FailoverListenSocket('conversation-1', 90.0, clock)
    socket._early.append({'type': 'service_status', 'status': 'stt_failed', 'status_text': 'provider details'})
    _install_fake_timeline(monkeypatch, probe, clock)
    monkeypatch.setattr(probe.websockets, 'connect', lambda *_a, **_k: _FakeConnect(socket))
    fixture = probe.Fixture(pcm=b'\x00' * (16000 * 2), sample_rate=16000, expected_phrase='hello')

    with pytest.raises(probe.ProbeError, match='^stt_unavailable$'):
        await probe._listen_sample('https://api.example.invalid', 'token', fixture, 'conversation-1')


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('durable_segments', 'should_pass'),
    [
        ([{'text': 'He began a confused complaint against the wizard who had vanished.'}], True),
        ([{'text': 'partial audio only'}], False),
    ],
)
async def test_terminal_readback_enforces_the_fixture_phrase_in_the_durable_transcript(
    monkeypatch, probe, durable_segments, should_pass
):
    """The durable completed conversation is the release contract: the fixture
    phrase must appear in its transcript segments regardless of whether the
    live streaming window or the batch finalization path produced it."""
    responses = iter(
        [
            (
                200,
                {
                    'status': 'completed',
                    'terminal': True,
                    'terminal_outcome': 'success',
                    'fanout_status': 'completed',
                },
            ),
            (
                200,
                {
                    'id': 'conversation-1',
                    'status': 'completed',
                    'transcript_segments': durable_segments,
                },
            ),
        ]
    )
    monkeypatch.setattr(probe, '_http_json', lambda *_args: next(responses))

    if should_pass:
        await probe._terminal_readback(
            'https://api.example.invalid',
            'token',
            'conversation-1',
            1,
            expected_phrase='he began a confused complaint against the wizard',
        )
    else:
        with pytest.raises(probe.ProbeError, match='transcript_mismatch'):
            await probe._terminal_readback(
                'https://api.example.invalid',
                'token',
                'conversation-1',
                1,
                expected_phrase='he began a confused complaint against the wizard',
            )


def test_alignment_coverage_compares_segments_and_spans_on_one_axis(probe):
    origin = probe._epoch_seconds('2026-09-26T07:08:30.000000Z')
    assert origin == probe._epoch_seconds('2026-09-26T07:08:30')  # naive ISO is UTC
    spans = [{'start': origin, 'end': origin + 9.9}, {'start': origin + 14.086, 'end': origin + 18.986}]
    # Segment times are seconds from started_at; spans are wall-epoch seconds.
    assert probe._alignment_covered(spans, origin + 0.28, origin + 4.66)
    assert probe._alignment_covered(spans, origin + 14.186, origin + 18.746)
    assert not probe._alignment_covered(spans, origin + 10.0, origin + 12.0)
    # The relative segment offsets alone never overlap wall-epoch spans.
    assert not probe._alignment_covered(spans, 0.28, 4.66)


def test_alignment_receipt_exposes_only_the_probe_conversation_id(probe):
    conversation_id = '5df117e1-3b4b-41b2-94c6-54f3c690e811'
    receipt = probe._alignment_receipt(
        status='PASS',
        started_at='2026-09-26T00:00:00Z',
        failure_stage=None,
        conversation_id=conversation_id,
        coverage_ok=True,
        candidate_pusher_observed=True,
    )
    assert receipt['conversation_id'] == conversation_id
    assert receipt['checks']['span_coverage'] is True
    assert receipt['checks']['candidate_pusher_observed'] is True
    assert 'omi-release-probe' not in json.dumps(receipt)
    assert 'transcript' not in json.dumps(receipt)


@pytest.mark.asyncio
async def test_alignment_probe_requires_private_cloud_flag_on_finalized_conversation(monkeypatch, probe, tmp_path):
    deployment_receipt = tmp_path / 'deployment.json'
    deployment_receipt.write_text('{"source_sha":"synthetic"}', encoding='utf-8')
    monkeypatch.setattr(probe, '_read_token', lambda _path: 'synthetic-token')
    monkeypatch.setattr(probe, 'load_fixture', lambda: SimpleNamespace(expected_phrase='synthetic'))
    monkeypatch.setattr(
        probe,
        '_http_json_method',
        lambda url, _token: (
            (200, {'private_cloud_sync_enabled': True})
            if url.endswith('/v1/users/private-cloud-sync')
            else (200, {'id': conversation_id, 'private_cloud_sync_enabled': False})
        ),
    )

    async def no_op(*_args, **_kwargs):
        return []

    async def observe(*_args, **_kwargs):
        return 1

    monkeypatch.setattr(probe, '_alignment_listen', no_op)
    monkeypatch.setattr(probe, '_terminal_readback', no_op)
    monkeypatch.setattr(probe, '_observe_candidate_pusher', observe)
    conversation_id = '5df117e1-3b4b-41b2-94c6-54f3c690e811'
    monkeypatch.setattr(probe.uuid, 'uuid4', lambda: conversation_id)
    args = SimpleNamespace(
        bearer_token_file=tmp_path / 'token',
        deployment_receipt=deployment_receipt,
        api_url='https://api.omiapi.com',
        allow_local_http=False,
        finalization_timeout_seconds=1,
        project='based-hardware-dev',
        namespace='dev-omi-backend',
    )
    receipt, passed = await probe.run_alignment_scenario(args)
    assert not passed
    assert receipt['failure_stage'] == 'private_cloud_conversation_flag'
    assert receipt['checks']['candidate_pusher_observed'] is True
    assert receipt['conversation_id'] == conversation_id


@pytest.mark.asyncio
async def test_alignment_probe_rejects_non_dev_endpoint_before_any_account_write(monkeypatch, probe, tmp_path):
    deployment_receipt = tmp_path / 'deployment.json'
    deployment_receipt.write_text('{"source_sha":"synthetic"}', encoding='utf-8')
    monkeypatch.setattr(probe, '_read_token', lambda _path: 'synthetic-token')
    monkeypatch.setattr(probe, 'load_fixture', lambda: SimpleNamespace(expected_phrase='synthetic'))
    monkeypatch.setattr(probe, '_http_json_method', lambda *_args: pytest.fail('unexpected account request'))
    args = SimpleNamespace(
        bearer_token_file=tmp_path / 'token',
        deployment_receipt=deployment_receipt,
        api_url='https://api.omi.me',
        allow_local_http=False,
    )
    receipt, passed = await probe.run_alignment_scenario(args)
    assert not passed
    assert receipt['failure_stage'] == 'dev_api_url'
