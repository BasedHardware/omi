"""Run on base and candidate: compare stored payloads and existing metric deltas.

CAPTURE_PARITY_OUTPUT names a local JSON receipt; no clients or remote replay.
"""

import json
import os
from pathlib import Path

from prometheus_client import REGISTRY

from tests.unit.test_live_capture_retention import setup, drain
from tests.unit.test_audio_timeline_round3 import RATE, T0


def counters():
    return {
        (sample.name, tuple(sorted(sample.labels.items()))): sample.value
        for family in REGISTRY.collect()
        for sample in family.samples
        if sample.name.endswith('_total')
        and sample.name.startswith(('omi_audio_timeline_', 'omi_live_audio_capture_windows_'))
    }


async def test_off_payload_and_existing_metric_parity(monkeypatch):
    monkeypatch.setenv('LIVE_CAPTURE_WINDOW_MERGE_PRESERVATION', 'false')
    monkeypatch.setenv('LIVE_CAPTURE_WINDOW_STRICT_PROJECTION', 'false')
    output = []
    before = counters()
    for provider in ('deepgram', 'soniox', 'modulate'):
        receiver, callback, epoch, sender = setup(monkeypatch, False, provider)
        receiver.speaker_provider_epoch._connection_scope = 'fixed-scope'
        pcm = b'\0\0' * RATE
        for i in range(70):
            start, _, _ = receiver.capture_timeline.accept(pcm, T0 + i * 4 + 1, i * 4 + 1)
            assert sender.send(pcm, start_sample=start)
        # Known, unknown merge, gapped known merge, partial redistribution and early-final compaction.
        callback(
            [
                dict(id='a', text='Hello', speaker='SPEAKER_00', is_user=False, start=67, end=68),
                dict(id='b', text='world', speaker='SPEAKER_00', is_user=False, start=68, end=69),
                dict(id='c', text='A long unfinished phrase', speaker='SPEAKER_01', is_user=False, start=69, end=69.4),
                dict(id='d', text='yes. Another sentence.', speaker='SPEAKER_02', is_user=False, start=69.4, end=69.9),
                dict(id='e', text='Delayed final.', speaker='SPEAKER_03', is_user=False, start=0.1, end=0.9),
                dict(id='f', text='Outside sends.', speaker='SPEAKER_04', is_user=False, start=99, end=100),
                dict(id='g', text='Crossing hiatus.', speaker='SPEAKER_05', is_user=False, start=67.9, end=68.1),
            ]
        )
        output.append(await drain(monkeypatch, receiver))
    after = counters()
    delta = [
        dict(name=name, labels=dict(labels), value=after.get((name, labels), 0) - before.get((name, labels), 0))
        for name, labels in sorted(set(before) | set(after))
        if after.get((name, labels), 0) != before.get((name, labels), 0)
    ]
    receipt = dict(payloads=output, existing_metrics=delta)
    if os.environ.get('CAPTURE_PARITY_OUTPUT'):
        Path(os.environ['CAPTURE_PARITY_OUTPUT']).write_text(json.dumps(receipt, sort_keys=True, indent=2) + '\n')
    assert len(output) == 3
