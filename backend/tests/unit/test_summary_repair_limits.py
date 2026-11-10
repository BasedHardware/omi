"""Repair spend and owner-share controls have safe, bounded startup defaults."""

from pathlib import Path
import runpy

import pytest


@pytest.mark.parametrize(
    'key,attribute,default,maximum',
    [
        ('SUMMARY_DEBT_REPAIR_ADMISSION_LIMIT', 'REPAIR_ADMISSION_LIMIT', 10, 60),
        ('SUMMARY_DEBT_REPAIR_PER_OWNER_LIMIT', 'REPAIR_PER_OWNER_TICK_LIMIT', 3, 10),
    ],
)
@pytest.mark.parametrize('value', [None, '', 'invalid', '1.5', '-1', '0', '1', '3', '10', '60', '61'])
def test_repair_limits_parse_startup_settings(monkeypatch, key, attribute, default, maximum, value):
    if value is None:
        monkeypatch.delenv(key, raising=False)
    else:
        monkeypatch.setenv(key, value)
    # Execute the actual config without reloading the application's shared
    # ContextVars or changing constants already imported by another test.
    config = runpy.run_path(str(Path(__file__).resolve().parents[2] / 'config/summary_guarantee.py'))
    expected = {
        None: default,
        '': default,
        'invalid': default,
        '1.5': default,
        '-1': 1,
        '0': 1,
        '1': 1,
        '3': 3,
        '10': 10,
        '60': maximum,
        '61': maximum,
    }[value]
    assert config[attribute] == expected
    assert config['REPAIR_INTERVAL_SECONDS'] == 120
    assert config['REPAIR_SCAN_LIMIT'] == 100
