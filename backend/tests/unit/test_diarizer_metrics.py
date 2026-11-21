import pytest
from prometheus_client import REGISTRY, Counter, Gauge, Histogram
import diarizer.metrics

def test_metrics_registration():
    """Test that all metrics are properly registered with prometheus."""

    names = [m.name for m in REGISTRY.collect()]

    # Check that all metrics are registered with the expected names
    # Note: Prometheus client sometimes strips _total suffix
    assert 'omi_diarization_v2' in names or 'omi_diarization_v2_total' in names
    assert 'omi_diarization_v2_audio_seconds' in names or 'omi_diarization_v2_audio_seconds_total' in names
    assert 'omi_diarization_v2_rtf' in names
    assert 'omi_diarization_v2_queue_depth' in names
    assert 'omi_diarization_v2_gpu_memory_bytes' in names

def test_metrics_types():
    """Test that metrics have the correct type."""

    assert isinstance(diarizer.metrics.REQUESTS, Counter)
    assert isinstance(diarizer.metrics.AUDIO, Counter)
    assert isinstance(diarizer.metrics.RTF, Histogram)
    assert isinstance(diarizer.metrics.DEPTH, Gauge)
    assert isinstance(diarizer.metrics.GPU_MEMORY, Gauge)

def test_metrics_labels():
    """Test that metrics have the correct labels."""

    # Check REQUESTS metric labels
    assert diarizer.metrics.REQUESTS._labelnames == ('outcome',)

    # Check RTF metric buckets
    assert diarizer.metrics.RTF._kwargs['buckets'] == (0.01, 0.05, 0.1, 0.2, 0.5, 1, 2)
