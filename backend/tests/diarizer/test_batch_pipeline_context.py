import numpy as np
import pytest
from types import SimpleNamespace

from diarizer.batch_pipeline_context import (
    capture_stream,
    select_context,
    LeftContextIndex,
    starts_in_speech,
    empty_retry_audio,
    SAMPLE_RATE,
)

def test_capture_stream_conversation():
    item = SimpleNamespace(unit_kind='conversation', conversation_id='c123')
    assert capture_stream(item) == 'conversation:c123'

    item_no_id = SimpleNamespace(unit_kind='conversation', conversation_id=None)
    assert capture_stream(item_no_id) is None

def test_capture_stream_intake_context():
    item = SimpleNamespace(unit_kind='other')

    # Missing source
    assert capture_stream(item, intake_context={'other': 'stuff'}) is None

    # With source
    intake_context = {'source': 'ios', 'client_device_id': 'dev1', 'should_lock': True}
    res = capture_stream(item, intake_context)
    assert res is not None
    assert res.startswith('capture:')

def test_select_context():
    # Empty samples
    assert select_context([], [], 5.0) is None

    # No max_seconds
    assert select_context([0]*10, [], 0.0) is None

    # Silent tail (no crossing spans)
    # samples = 2 seconds
    total = SAMPLE_RATE * 2
    samples = np.zeros(total, dtype=np.int16)
    # seam is at 2.0s
    # max_seconds = 5.0, floor = 0.0
    # crossing = [] -> start = max(0, 2.0 - 1.0) = 1.0
    # first = 1.0 * 16000 = 16000
    res = select_context(samples, [], 5.0)
    assert res == (16000, 32000)

    # Crossing spans
    # seam = 2.0s
    # crossing spans: ends at >= 1.7s
    spans = [(1.5, 1.8), (1.9, 2.1)]
    # min crossing = 1.5
    # start = max(0.0, 1.5 - 0.5) = 1.0
    res = select_context(samples, spans, 5.0)
    assert res == (16000, 32000)

def test_left_context_index():
    index = LeftContextIndex(max_seconds=5.0, max_units=2, ttl_seconds=600, clock=lambda: 100.0)
    item = SimpleNamespace(owner_id='u1', privacy_generation='g1', capture_at=10.0)

    # Remember empty
    index.remember(item, None, [], 'str1')

    # Remember valid
    total = SAMPLE_RATE * 2
    samples = np.zeros(total, dtype=np.float32)
    spans = [(1.5, 2.0)]

    index.remember(item, samples, spans, 'str1')

    # Lookup contiguous
    next_item = SimpleNamespace(owner_id='u1', privacy_generation='g1', capture_at=12.0)
    lookup_res = index.lookup(next_item, duration=2.0, stream='str1')
    assert lookup_res is not None
    assert len(lookup_res) == SAMPLE_RATE * 1 # 1 second retained (start=1.0)

    # Lookup wrong stream
    assert index.lookup(next_item, duration=2.0, stream='str2') is None

def test_starts_in_speech():
    assert not starts_in_speech([])
    assert starts_in_speech([(0.2, 1.0)])
    assert not starts_in_speech([(0.6, 1.0)])

def test_empty_retry_audio():
    index = LeftContextIndex(max_seconds=5.0, max_units=2, ttl_seconds=600, clock=lambda: 100.0)
    item = SimpleNamespace(owner_id='u1', privacy_generation='g1', capture_at=10.0)
    total = SAMPLE_RATE * 2
    samples = np.zeros(total, dtype=np.float32)

    # remember predecessor
    index.remember(item, samples, [(1.5, 2.0)], 'str1')

    next_item = SimpleNamespace(owner_id='u1', privacy_generation='g1', capture_at=12.0)
    next_samples = np.zeros(SAMPLE_RATE * 1, dtype=np.float32)
    state = {
        'item': next_item,
        'samples': next_samples,
        'stream': 'str1',
        'speech_spans': []
    }

    new_samples, offset = empty_retry_audio(state, index, 120.0)
    assert len(new_samples) == SAMPLE_RATE * 2 # 1s context + 1s new samples
    assert offset == -1.0

    # Without context
    state['stream'] = 'str2'
    new_samples, offset = empty_retry_audio(state, index, 120.0)
    assert len(new_samples) == SAMPLE_RATE * 1
    assert offset == 0.0
