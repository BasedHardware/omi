"""Exact HEAD/candidate OFF receipt through the approved offline harness."""

import json
import os
from pathlib import Path

from tests.unit.test_capture_window_resolution_r2 import (
    env,
    verified_audio,
    live_window,
    stage,
    STARTED,
    AudioTimelineProvenance,
)
from utils.metrics import OMI_CONVERSATION_SPEAKER_RESOLUTION_TOTAL, OMI_AUDIO_PLACEMENT_TOTAL


def old_counters():
    return {
        (s.name, tuple(sorted(s.labels.items()))): s.value
        for counter in (OMI_CONVERSATION_SPEAKER_RESOLUTION_TOTAL, OMI_AUDIO_PLACEMENT_TOTAL)
        for family in counter.collect()
        for s in family.samples
        if s.name.endswith('_total')
    }


def test_off_resolution_receipt(env, verified_audio, monkeypatch):
    monkeypatch.setenv('LIVE_SPEAKER_SPAN_RESOLUTION', 'false')
    monkeypatch.setenv('LIVE_CAPTURE_WINDOW_STRICT_PROJECTION', 'false')
    monkeypatch.setenv('LIVE_CAPTURE_WINDOW_RETENTION', 'false')
    monkeypatch.setenv('LIVE_CAPTURE_WINDOW_MERGE_PRESERVATION', 'false')
    rows = []
    before = old_counters()
    for scope in ('sync', 'v2'):
        for extents in ([(0, 1.2)], [(0, 0.6), (0.6, 1.2)]):
            env[0].clear()
            conversation = live_window()
            segment = conversation.transcript_segments[0]
            segment.speaker_id_scope = 'sync:offline'
            if scope == 'v2':
                conversation.audio_timeline = AudioTimelineProvenance(version=2)
                segment.speaker_id_scope = 'conversation:c1'
                segment.audio_source = dict(type='sync', start=STARTED.timestamp(), end=STARTED.timestamp() + 1.2)
            verified_audio(conversation, extents)
            calls = env[1].calls
            stage.resolve_speakers_for_processing('offline', conversation)
            rows.append(
                dict(
                    payload=conversation.model_dump(mode='json'),
                    embeddings=env[1].calls - calls,
                    cache={k: v.hex() for k, v in env[0].items()},
                )
            )
    after = old_counters()
    delta = [
        dict(name=name, labels=dict(labels), value=after.get((name, labels), 0) - before.get((name, labels), 0))
        for name, labels in sorted(set(before) | set(after))
        if after.get((name, labels), 0) != before.get((name, labels), 0)
    ]
    if os.environ.get('RESOLUTION_PARITY_OUTPUT'):
        Path(os.environ['RESOLUTION_PARITY_OUTPUT']).write_text(
            json.dumps(dict(rows=rows, metrics=delta), sort_keys=True, indent=2) + '\n'
        )
    assert len(rows) == 4
