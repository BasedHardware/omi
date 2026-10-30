"""Diagnostics faults preserve real managed wire and persisted transcript behavior."""

import asyncio
from itertools import product
from uuid import UUID

import pytest
from prometheus_client import generate_latest, metrics as prometheus_metrics

from tests.unit.test_soniox_capture_axis_r10 import managed, close, final, Wire, values
from tests.unit.test_capture_window_merge_union_r5 import tick
from tests.unit.test_audio_timeline_round3 import RATE, T0
from utils.stt import live_session, soniox, soniox_capture_axis as diagnostics
from utils.stt.soniox_idle import IdleSonioxSocket


def fail(*args, **kwargs):
    raise RuntimeError('injected diagnostic failure')


async def written(wire):
    return await asyncio.wait_for(wire.writes.get(), 0.1)


async def receipt(monkeypatch):
    ids = iter(range(1, 100))
    monkeypatch.setattr('uuid.uuid4', lambda: UUID(int=next(ids)))
    before = values()
    receiver, epoch, processor, store, leg, wire, _ = await managed(monkeypatch, True)
    try:
        pcm = b'\1\0' * RATE
        start, _, _ = receiver.capture_timeline.accept(pcm, T0 + 1, 1)
        assert leg.send(pcm, start_sample=start)
        await written(wire)  # config
        assert await written(wire) == pcm
        await final(wire, leg.raw, 200, 800)
        rows = await tick(receiver, processor, store)
        # Exercise a second frame/response after disablement too.
        start, _, _ = receiver.capture_timeline.accept(pcm, T0 + 2, 2)
        assert leg.send(pcm, start_sample=start)
        assert await written(wire) == pcm
        await final(wire, leg.raw, 1200, 1800)
        rows = await tick(receiver, processor, store)
        leg.raw.finalize()
        assert await written(wire) == '{"type": "finalize"}'
        leg.finish()
        assert await written(wire) == ''
        assert not leg.is_connection_dead and not leg.raw.is_connection_dead
        after = values()
        deltas = {key: value - before.get(key, 0) for key, value in after.items() if value != before.get(key, 0)}
        return rows, wire.sent, deltas, leg.raw._capture_axis
    finally:
        await close(leg)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'hook',
    [
        'constructor',
        'bind',
        'socket_bind',
        'binding_lookup',
        'enabled',
        'live_enabled',
        'queued',
        'inflight',
        'inflight_reset',
        'sent',
        'response',
        'ledger',
        'histogram',
        'comparison',
        'events',
        'logger',
        'all',
    ],
)
async def test_every_socket_diagnostic_fault_preserves_exact_managed_receipt(monkeypatch, hook):
    baseline = await receipt(monkeypatch)
    errors = diagnostics.AXIS_EVENTS.labels(event='diagnostic_error')._value.get()
    kind = diagnostics.CaptureAxisDiagnostics
    if hook in ('constructor', 'all'):
        monkeypatch.setattr(soniox, 'CaptureAxisDiagnostics', fail)
    if hook in ('bind', 'all'):
        monkeypatch.setattr(kind, 'bind', fail)
    if hook == 'socket_bind':
        monkeypatch.setattr(soniox.SafeSonioxSocket, 'set_capture_axis_ledger', fail)
    if hook == 'binding_lookup':
        original = soniox.SafeSonioxSocket.__getattribute__

        def lookup(self, name):
            if name == 'set_capture_axis_ledger':
                fail()
            return original(self, name)

        monkeypatch.setattr(soniox.SafeSonioxSocket, '__getattribute__', lookup)
    if hook == 'enabled':
        monkeypatch.setattr(soniox, 'capture_axis_diagnostics_enabled', fail)
    if hook == 'live_enabled':
        monkeypatch.setattr(live_session, 'capture_axis_diagnostics_enabled', fail)
    if hook in ('queued', 'inflight', 'inflight_reset'):
        original = kind.__setattr__

        def assign(self, name, value):
            if name == hook and name in self.__dict__:
                fail()
            if hook == 'inflight_reset' and name == 'inflight' and name in self.__dict__ and value is False:
                fail()
            original(self, name, value)

        monkeypatch.setattr(kind, '__setattr__', assign)
    if hook in ('sent', 'response', 'all'):
        for method in ('sent', 'response') if hook == 'all' else (hook,):
            monkeypatch.setattr(kind, method, fail)
    if hook == 'ledger':
        monkeypatch.setattr(kind, 'bind', lambda self, *args: setattr(self, 'ledger', fail))
    if hook in ('histogram', 'comparison', 'events'):
        metric = {
            'histogram': diagnostics.AXIS_DELTA,
            'comparison': diagnostics.AXIS_COMPARISON,
            'events': diagnostics.AXIS_EVENTS,
        }[hook]
        monkeypatch.setattr(metric, 'labels', fail)
    if hook == 'logger':
        # Force a compact final into the sampled-overshoot logging branch without
        # changing provider timestamps, PCM, ledger or persistence.
        original = kind.response

        monkeypatch.setattr(kind, 'response', lambda self, msg: logged_response(self, msg, original))
        monkeypatch.setattr(diagnostics, '_last_sample_log', float('-inf'))
        monkeypatch.setattr(diagnostics.logger, 'info', fail)
    candidate = await receipt(monkeypatch)
    assert candidate[:3] == baseline[:3]
    assert candidate[3] is None
    if hook != 'events':  # a failed error collector cannot report its own failure
        assert diagnostics.AXIS_EVENTS.labels(event='diagnostic_error')._value.get() == errors + 1


def logged_response(self, msg, original):
    self.written = 1
    self.sample_logs = 0
    return original(self, msg)


@pytest.mark.asyncio
@pytest.mark.parametrize('stage', ['initial', 'reopened'])
async def test_idle_binding_fault_never_becomes_transport_failure(monkeypatch, stage):
    monkeypatch.setenv('SONIOX_CAPTURE_AXIS_DIAGNOSTICS', 'true')
    peers, seen = [], []

    async def connect(callback):
        raw = soniox.SafeSonioxSocket(Wire(), callback, asyncio.get_running_loop())
        peers.append(raw)
        if stage == 'reopened':
            monkeypatch.setattr(raw, 'set_capture_axis_ledger', fail)
        return raw

    first = soniox.SafeSonioxSocket(Wire(), lambda _: None, asyncio.get_running_loop())
    peers.append(first)
    idle = IdleSonioxSocket(first, connect, seen.extend, RATE, 20)
    ledger = [RATE]
    errors = diagnostics.AXIS_EVENTS.labels(event='diagnostic_error')._value.get()
    failures = idle._metrics.failures._value.get()
    if stage == 'initial':
        monkeypatch.setattr(first, 'set_capture_axis_ledger', fail)
    idle.set_capture_axis_ledger(lambda: ledger[0])
    try:
        assert idle.send(b'\1\0' * RATE)
        assert await written(first._ws) == b'\1\0' * RATE
        await final(first._ws, first, 200, 800)
        assert seen[0]['start'] == 0.2 and seen[0]['end'] == 0.8
        idle._idle_since = 1
        assert idle.send(b'\1\0' * RATE)
        ledger[0] = 2 * RATE
        idle.set_resume_provider_offset(RATE)
        assert await idle.complete_send()
        current = idle._transport
        assert await written(current._ws) == b'\1\0' * RATE
        await final(current._ws, current, 200, 800)
        assert seen[1]['start'] == 1.2 and seen[1]['end'] == 1.8
        assert not idle.is_connection_dead and not idle.idle_reopen_failed
        assert idle._metrics.failures._value.get() == failures
        assert (first if stage == 'initial' else current)._capture_axis is None
        assert diagnostics.AXIS_EVENTS.labels(event='diagnostic_error')._value.get() == errors + 1
    finally:
        for peer in peers:
            peer._send_task.cancel()
            peer._recv_task.cancel()
        await asyncio.gather(
            *(task for peer in peers for task in (peer._send_task, peer._recv_task)), return_exceptions=True
        )


@pytest.mark.parametrize(
    'queue,written,inflight', [('backlogged', RATE, False), ('drained', 10 * RATE, False), ('drained', 10 * RATE, True)]
)
def test_same_response_queue_label_distinguishes_settled_backlog(monkeypatch, queue, written, inflight):
    monkeypatch.setenv('SONIOX_CAPTURE_AXIS_DIAGNOSTICS', 'true')
    diag = diagnostics.CaptureAxisDiagnostics(RATE)
    diag.queued, diag.written, diag.inflight = 10 * RATE, written, inflight
    diag.bind(lambda: 10 * RATE)
    diag.first_write_at = diag.connected_at
    state = 'inflight' if inflight else 'settled'
    labels = dict(
        wire='past' if written == RATE else 'within', ledger='equal', phase='initial', write_state=state, queue=queue
    )
    before = diagnostics.AXIS_COMPARISON.labels(**labels)._value.get()
    references = (
        'token_minus_written',
        'token_minus_queued',
        'token_minus_connected_elapsed',
        'token_minus_first_write_elapsed',
        'queued_minus_ledger',
        'total_audio_proc_ms_minus_written',
        'final_audio_proc_ms_minus_written',
    )
    histograms = [
        diagnostics.AXIS_DELTA.labels(reference=r, phase='initial', write_state=state, queue=queue) for r in references
    ]
    counts = [sum(b.get() for b in h._buckets) for h in histograms]
    diag.response(
        {
            'tokens': [{'text': 'word', 'is_final': True, 'end_ms': 9000}],
            'total_audio_proc_ms': 9000,
            'final_audio_proc_ms': 8000,
        }
    )
    assert diagnostics.AXIS_COMPARISON.labels(**labels)._value.get() == before + 1
    assert [sum(b.get() for b in h._buckets) for h in histograms] == [c + 1 for c in counts]


def test_off_scrape_has_no_new_metadata_or_samples_even_after_on(monkeypatch):
    prefixes = (b'omi_soniox_capture_axis_', b'omi_audio_timeline_elapsed_validation_detail_')
    monkeypatch.setenv('SONIOX_CAPTURE_AXIS_DIAGNOSTICS', 'true')
    diagnostics.AXIS_EVENTS.labels(event='audio').inc()
    enabled_scrape = generate_latest()
    for prefix in prefixes:
        assert b'# HELP ' + prefix in enabled_scrape and b'# TYPE ' + prefix in enabled_scrape
    for setting in ('false', None):
        if setting is None:
            monkeypatch.delenv('SONIOX_CAPTURE_AXIS_DIAGNOSTICS')
        else:
            monkeypatch.setenv('SONIOX_CAPTURE_AXIS_DIAGNOSTICS', setting)
        scrape = generate_latest()
        assert all(prefix not in scrape for prefix in prefixes)


def test_metric_series_upper_bound_including_created(monkeypatch):
    monkeypatch.setattr(prometheus_metrics, '_use_created', True)
    monkeypatch.setenv('SONIOX_CAPTURE_AXIS_DIAGNOSTICS', 'true')
    references = (
        'token_minus_written',
        'token_minus_queued',
        'token_minus_connected_elapsed',
        'token_minus_first_write_elapsed',
        'queued_minus_ledger',
        'total_audio_proc_ms_minus_written',
        'final_audio_proc_ms_minus_written',
    )
    for labels in product(references, ('initial', 'reopened'), ('settled', 'inflight'), ('drained', 'backlogged')):
        diagnostics.AXIS_DELTA.labels(*labels)
    for labels in product(
        ('no_audio', 'within', 'past'),
        ('equal', 'queue_ahead', 'ledger_ahead', 'unavailable'),
        ('initial', 'reopened'),
        ('settled', 'inflight'),
        ('drained', 'backlogged'),
    ):
        diagnostics.AXIS_COMPARISON.labels(*labels)
    for event in ('audio', 'end', 'keepalive', 'finalize', 'ledger_unavailable', 'diagnostic_error'):
        diagnostics.AXIS_EVENTS.labels(event)
    for labels in product(
        ('soniox', 'modulate', 'deepgram', 'parakeet', 'unknown'),
        ('map_refused', 'no_gate', 'invalid_interval', 'vad_uncovered', 'classified'),
    ):
        diagnostics.VALIDATION_DETAIL.labels(*labels)
    assert [sum(len(f.samples) for f in metric.collect()) for metric in diagnostics._EnabledCollectors.metrics] == [
        896,
        12,
        192,
        50,
    ]
