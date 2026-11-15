"""Explicit all-provider configuration for routing mechanism/incident replays."""

import json
from dataclasses import asdict, replace

from config.live_stt_registry import DEFAULT_TARGETS

ENABLED_TARGETS = tuple(replace(target, ramp_percent=100) for target in DEFAULT_TARGETS)


def enabled_live_targets(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_TARGETS_JSON', json.dumps([asdict(target) for target in ENABLED_TARGETS]))
