"""The independent probe-cap setting retains its own bound after the upload hook retires."""

import pytest

from config.batch_pipeline_shadow import language_probe_limit


@pytest.mark.parametrize('value,expected', [('-1', 0), ('0', 0), ('100', 100), ('501', 500), ('bad', 0)])
def test_independent_language_probe_cap_remains_bounded(monkeypatch, value, expected):
    monkeypatch.setenv('BATCH_PIPELINE_SHADOW_LANGUAGE_PROBES_PER_HOUR', value)
    assert language_probe_limit() == expected
