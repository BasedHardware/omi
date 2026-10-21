"""Notifications entrypoint keeps local runs unchanged and drains job metrics."""

import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from testing.import_isolation import stub_modules


@pytest.mark.parametrize('enabled,fail_init', [(False, False), (True, False), (True, True)])
def test_listener_and_completion_handshake(monkeypatch, tmp_path, enabled, fail_init):
    jobs = ModuleType('utils.other.jobs')
    calls = []

    async def start_job():
        calls.append('job')

    jobs.start_job = start_job
    with stub_modules({'utils.other.jobs': jobs}):
        spec = importlib.util.spec_from_file_location(
            '_recap_job_listener_test', Path(__file__).resolve().parents[2] / 'modal/job.py'
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    monkeypatch.delenv('SERVICE_ACCOUNT_JSON', raising=False)
    monkeypatch.delenv('PROMETHEUS_SIDECAR_PORT', raising=False)
    marker = tmp_path / 'done'
    monkeypatch.setenv('PROMETHEUS_SIDECAR_DONE_FILE', str(marker))
    if enabled:
        monkeypatch.setenv('PROMETHEUS_SIDECAR_PORT', '9090')

    def initialize(*_args, **_kwargs):
        calls.append('init')
        if fail_init:
            raise RuntimeError('init failed')

    monkeypatch.setattr(module.firebase_admin, 'initialize_app', initialize)
    monkeypatch.setattr(module, 'firebase_admin_options', lambda: {})
    server = SimpleNamespace(shutdown=lambda: calls.append('shutdown'), server_close=lambda: calls.append('close'))

    def listener(port, addr):
        assert port == 9090 and addr == '127.0.0.1'
        calls.append('listener')
        return server, None

    def sleep(seconds):
        assert seconds == 45 and marker.exists()
        calls.append('drain')

    monkeypatch.setattr(module, 'start_http_server', listener)
    monkeypatch.setattr(module.time, 'sleep', sleep)
    if fail_init:
        with pytest.raises(RuntimeError, match='init failed'):
            module.main()
    else:
        module.main()
    expected = (['listener'] if enabled else []) + ['init'] + ([] if fail_init else ['job'])
    if enabled:
        expected += ['drain', 'shutdown', 'close']
    assert calls == expected
    assert marker.exists() == enabled
