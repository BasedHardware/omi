"""Replay harness port reservations must be exclusive and distinct.

The harness reserves its role ports by binding probes. A probe that waives the
exclusive bind (SO_REUSEADDR) does not actually hold the port, so a racing
binder can take it and the child then fails with EADDRINUSE — the failure the
reservation exists to prevent (#20933).
"""

from __future__ import annotations

import socket
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNNER_SOURCE = REPO_ROOT / 'backend' / 'testing' / 'replay_harness_phase0a' / 'runner.py'


def test_replay_runner_does_not_waive_its_exclusive_bind() -> None:
    source = RUNNER_SOURCE.read_text(encoding='utf-8')

    assert 'def _free_ports(self, count: int) -> list[int]:' in source
    assert 'self._free_ports(' in source
    assert 'SO_REUSEADDR' not in source


def test_replay_runner_reserves_distinct_bindable_ports(tmp_path: Path) -> None:
    from testing.replay_harness_phase0a import runner

    topology = tmp_path / 'topology.json'
    topology.write_text('{}', encoding='utf-8')
    harness = runner.Harness(topology, tmp_path / 'state')
    try:
        ports = harness._free_ports(3)

        assert len(ports) == 3
        assert len(set(ports)) == 3
        assert all(isinstance(port, int) and port > 1024 for port in ports)

        # The probes released the ports, so this process can rebind each one.
        for port in ports:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.bind(('127.0.0.1', port))
    finally:
        harness.http.close()
