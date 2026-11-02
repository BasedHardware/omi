"""Real local HTTP admission preserves original pendant bytes before 202.

The existing E2E fixtures replace cloud services and block non-local sockets.
Provider processing is held at its existing background boundary: this proves
acceptance/retention, not transcription-provider quality.
"""

import socket
import struct
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn

from testing.e2e.sync_helpers import patch_fresh_sync_lane


@pytest.mark.parametrize('archive_fails', [False, True])
def test_local_http_batch_archive_acceptance(client, auth_headers, monkeypatch, fake_storage, archive_fails):
    patch_fresh_sync_lane(monkeypatch)
    router = sys.modules['routers.sync']
    storage = sys.modules['utils.other.storage']
    scheduled = []

    def hold_pipeline(coro, *, name):
        scheduled.append(coro)

    def unavailable(uid, paths):
        raise OSError('synthetic archive failure')

    monkeypatch.setattr(storage.users_db, 'get_data_protection_level', lambda uid: 'standard')
    monkeypatch.setattr(router, 'start_background_task', hold_pipeline)
    monkeypatch.setattr(router, 'get_hard_restriction_status', lambda uid: (False, None))
    monkeypatch.setattr(router, 'has_transcription_credits', lambda uid: True)
    monkeypatch.setattr(router, 'is_cloud_tasks_dispatch_enabled', lambda: False)
    monkeypatch.setattr(router, 'has_byok_keys', lambda: False)
    if archive_fails:
        monkeypatch.setattr(router, 'archive_mobile_batch_raw_files', unavailable)

    # Serve the real mounted FastAPI routes; skip unrelated application cron
    # startup, exactly as the harness's existing TestClient fixture does.
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(client.app, lifespan='off', log_level='error'))
    worker = threading.Thread(target=lambda: server.run(sockets=[sock]))
    worker.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started
        # 100 unchanged libopus 10ms silence frames (one audio-second).
        raw = (struct.pack('<I', 3) + bytes([176, 255, 254])) * 100
        name = f'audio_omimobilebatch001_opus_16000_1_fs160_{time.time():.6f}.bin'
        with httpx.Client(base_url=f'http://127.0.0.1:{port}', trust_env=False, timeout=10) as http:
            response = http.post(
                '/v2/sync-local-files', headers=auth_headers, files={'files': (name, raw, 'application/octet-stream')}
            )
        archived = [
            path
            for path in (Path(fake_storage) / storage.private_cloud_sync_bucket / 'raw-mobile-batch').rglob('*.bin')
            if path.is_file()
        ]
        if archive_fails:
            assert response.status_code == 500, response.text
            assert not scheduled
            assert not archived
        else:
            assert response.status_code == 202, response.text
            assert len(scheduled) == 1
            assert len(archived) == 1, str(list(Path(fake_storage).rglob("*")))
            assert archived[0].read_bytes() == raw
    finally:
        server.should_exit = True
        worker.join(timeout=10)
        sock.close()
        for coro in scheduled:
            coro.close()
        assert not worker.is_alive()
