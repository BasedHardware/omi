"""Synthetic coverage estimates, not production distribution or provider accuracy.

Run through test.sh. Optional CAPTURE_SIMULATION_OUTPUT writes a local receipt.
"""

import json
import os
from pathlib import Path

from utils.audio_timeline import CaptureTimeline, ProviderEpochTranslator
from utils.manual_speaker_assignments import merge_live_segments

FLAG = 'LIVE_CAPTURE_WINDOW_RETENTION'


def mapped(translator, start, end):
    result = translator.translate([dict(text='synthetic', start=start, end=end)])[0]
    first, last = result.get('_capture_start_sample'), result.get('_capture_end_sample')
    if first is None or last is None:
        return None
    a, b = translator.timeline.wall_strict(first), translator.timeline.wall_strict(last)
    return (a, b) if a is not None and b is not None else None


def realistic_reconnect_failover():
    # Four hours of capture, 1s speech / 1s VAD silence; observed 3s hiatus
    # every 100s. Providers rotate/reconnect every 30min. Finals lag 0..30s.
    rate = 10
    timeline = CaptureTimeline(rate)
    epoch = ProviderEpochTranslator(timeline, rate, project_times=False)
    epochs = [epoch]
    pending = []
    known = total = 0
    wall = 1000
    for i in range(7200):
        wall += 2 + (3 if i and i % 50 == 0 else 0)
        first, _, _ = timeline.accept(b'\0\0' * 20, wall, wall - 1000)
        if i and i % 900 == 0:
            epoch = ProviderEpochTranslator(timeline, rate, project_times=False)
            epochs.append(epoch)
        epoch.provider_label = ('deepgram', 'soniox', 'modulate')[(i // 900) % 3]
        provider_start = (epoch.send_map.last_provider_sample or 0) / rate
        epoch.note_accepted(first, 10)
        if i % 50 == 0:
            pending.append((i + 15, epoch, provider_start + 0.2, provider_start + 0.8))
        ready = [p for p in pending if p[0] <= i]
        pending = [p for p in pending if p[0] > i]
        for _, source, start, end in ready:
            total += 1
            known += mapped(source, start, end) is not None
    for _, source, start, end in pending:
        total += 1
        known += mapped(source, start, end) is not None
    return dict(known=known, segments=total)


def retention_pressure(kind):
    timeline = CaptureTimeline(10)
    epoch = ProviderEpochTranslator(timeline, 10, project_times=False)
    candidates = []
    wall = 1000
    count = 90 if kind == 'anchor' else 5000
    for i in range(count):
        wall += 4 if kind == 'anchor' else 2
        samples = 10 if kind == 'anchor' else 20
        first, _, _ = timeline.accept(b'\0\0' * samples, wall, wall - 1000)
        p = (epoch.send_map.last_provider_sample or 0) / 10
        epoch.note_accepted(first, 10)
        if i < 20:
            candidates.append((p + 0.2, p + 0.8))
    # Explicit pressure cases: 4..6min old finals after repeated capture stalls,
    # or ~2.8h-old finals after 5000 VAD bursts. These are upper-bound stress,
    # not a claimed realistic frequency of callback delay.
    return dict(known=sum(mapped(epoch, a, b) is not None for a, b in candidates), segments=len(candidates))


def sticky_merge():
    persisted = []
    timeline = CaptureTimeline(10)
    epoch = ProviderEpochTranslator(timeline, 10, project_times=False)
    known_versions = versions = 0
    for i in range(60):
        first, _, _ = timeline.accept(b'\0\0' * 60, 100 + (i + 1) * 6, (i + 1) * 6)
        epoch.note_accepted(first, 40)
        window = mapped(epoch, i * 4 + 0.1, i * 4 + 3.9)
        assert window is not None
        incoming = dict(
            id=str(i),
            text='word',
            speaker='SPEAKER_00',
            is_user=False,
            start=i * 4 + 0.1,
            end=i * 4 + 3.9,
            audio_capture_start=window[0],
            audio_capture_end=window[1],
        )
        result = merge_live_segments(persisted, [incoming], {})
        persisted = result.segments
        versions += len(result.updated_ids)
        known_versions += sum('audio_capture_start' in s for s in persisted if s['id'] in result.updated_ids)
    return dict(known=known_versions, versions=versions, distinct_stored_ids=len(persisted))


def test_simulated_coverage_recovers_only_retention_pressure(monkeypatch):
    report = {}
    for enabled in (False, True):
        monkeypatch.setenv(FLAG, 'true' if enabled else 'false')
        report['on' if enabled else 'off'] = dict(
            realistic_4h_reconnect_failover=realistic_reconnect_failover(),
            anchor_pressure_delayed_finals=retention_pressure('anchor'),
            send_map_pressure_delayed_finals=retention_pressure('send'),
            positive_gap_sticky_merge=sticky_merge(),
        )
    assert report['off']['realistic_4h_reconnect_failover'] == report['on']['realistic_4h_reconnect_failover']
    assert report['on']['anchor_pressure_delayed_finals']['known'] == 20
    assert report['on']['send_map_pressure_delayed_finals']['known'] == 20
    assert report['off']['anchor_pressure_delayed_finals']['known'] == 0
    assert report['off']['send_map_pressure_delayed_finals']['known'] == 0
    assert report['on']['positive_gap_sticky_merge'] == report['off']['positive_gap_sticky_merge']
    monkeypatch.setenv('LIVE_CAPTURE_WINDOW_MERGE_PRESERVATION', 'true')
    report['merge_preservation_on'] = sticky_merge()
    assert report['merge_preservation_on'] == dict(known=119, versions=119, distinct_stored_ids=60)
    print('SIMULATION ' + json.dumps(report, sort_keys=True))
    if os.environ.get('CAPTURE_SIMULATION_OUTPUT'):
        Path(os.environ['CAPTURE_SIMULATION_OUTPUT']).write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
