"""Preserve legacy cache bytes while round-tripping optional speaker evidence."""

import json
import struct

import numpy as np
import pytest

from tests.unit.test_conversation_speaker_resolution_stage import stage
from utils.speakers import processing


@pytest.mark.parametrize('mode', ['off', 'shadow', 'serve'])
def test_empty_evidence_preserves_legacy_cache_bytes(monkeypatch, mode):
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE', mode)
    token = processing.begin()
    try:
        entries = {'s0': (1.2, np.ones(64))}
        header = json.dumps({'v': 1, 'ids': ['s0'], 'durations': [1.2], 'dim': 64}).encode()
        expected = struct.pack('>I', len(header)) + header + np.ones(64).astype('<f2').tobytes()
        assert stage.encode_cache(entries) == expected
    finally:
        processing._current.reset(token)


def test_energy_evidence_survives_cache_reload(monkeypatch):
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE', 'shadow')
    token = processing.begin()
    try:
        processing.capture_energy('s0', np.full(16000, 3276, dtype='<i2').tobytes())
        expected = processing.energy_metadata()
        assert expected['s0'] == pytest.approx(-20, abs=0.01)
        encoded = stage.encode_cache({'s0': (1.2, np.ones(64))})
    finally:
        processing._current.reset(token)
    token = processing.begin()
    try:
        decoded = stage.decode_cache(encoded)
        assert np.array_equal(decoded['s0'][1], np.ones(64))
        assert processing.energy_metadata() == expected
    finally:
        processing._current.reset(token)
