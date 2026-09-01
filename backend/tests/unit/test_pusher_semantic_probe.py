from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'pusher_semantic_probe.py'


@pytest.fixture
def probe(monkeypatch):
    spec = importlib.util.spec_from_file_location('pusher_semantic_probe_test_target', SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_terminal_readback_requires_completed_successful_fanout(monkeypatch, probe):
    responses = iter(
        [
            (
                200,
                {
                    'status': 'completed',
                    'terminal': True,
                    'terminal_outcome': 'success',
                    'fanout_status': 'completed',
                },
            ),
            (200, {'id': 'conversation-1', 'status': 'completed', 'transcript_segments': [{'text': 'hello'}]}),
        ]
    )
    monkeypatch.setattr(probe, '_http_json', lambda *_args: next(responses))

    await probe._terminal_readback('https://api.example.invalid', 'token', 'conversation-1', 1)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('terminal_outcome', 'fanout_status'),
    [('stale', 'fenced'), ('failure', 'fenced'), ('success', 'leased'), ('unknown', 'unknown')],
)
async def test_terminal_readback_rejects_completed_without_successful_fanout(
    monkeypatch, probe, terminal_outcome: str, fanout_status: str
):
    monkeypatch.setattr(
        probe,
        '_http_json',
        lambda *_args: (
            200,
            {
                'status': 'completed',
                'terminal': True,
                'terminal_outcome': terminal_outcome,
                'fanout_status': fanout_status,
            },
        ),
    )

    with pytest.raises(probe.ProbeError, match='terminal_failure'):
        await probe._terminal_readback('https://api.example.invalid', 'token', 'conversation-1', 1)
