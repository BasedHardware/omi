from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/read_transcription_shadow_result.py'


@pytest.fixture
def reader():
    spec = importlib.util.spec_from_file_location('read_transcription_shadow_result', SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeDocument:
    def __init__(self, result):
        self.result = result
        self.path = []
        self.field_paths = None

    def collection(self, name):
        self.path.append(name)
        return self

    def document(self, name):
        self.path.append(name)
        return self

    def get(self, *, field_paths):
        self.field_paths = field_paths
        return self

    @property
    def exists(self):
        return self.result is not None

    def to_dict(self):
        return self.result


def test_scalar_readout_masks_fields_and_discards_unexpected_content(reader):
    fake = FakeDocument(
        {
            'outcome': 'ok',
            'word_distance': 0.125,
            'remap_safe': True,
            'audio_origin_offset_seconds': -14.98,
            'audio_timeline_v2': True,
            'measured_at': datetime(2026, 9, 26, tzinfo=timezone.utc),
            'transcript_text': 'must never print',
        }
    )
    result = reader.read_result(fake, 'omi-release-probe', 'abc')
    assert fake.path == ['users', 'omi-release-probe', 'conversations', 'abc', 'transcription_shadow_results', 'v1']
    assert fake.field_paths == list(reader.SCALAR_FIELDS)
    assert result['outcome'] == 'ok'
    assert result['word_distance'] == 0.125
    assert result['remap_safe'] is True
    assert result['audio_origin_offset_seconds'] == -14.98
    assert result['audio_timeline_v2'] is True
    assert result['measured_at'] == '2026-09-26T00:00:00+00:00'
    assert 'transcript_text' not in result


def test_readout_rejects_any_other_uid_before_read(reader):
    fake = FakeDocument({'outcome': 'ok'})
    with pytest.raises(ValueError, match='release-probe'):
        reader.read_result(fake, 'real-user', 'abc')
    assert fake.path == []


def test_missing_result_is_distinct_from_failure(reader):
    assert reader.read_result(FakeDocument(None), 'omi-release-probe', 'abc') is None
