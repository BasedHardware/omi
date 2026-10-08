"""Regression test for the desktop backend's BYOK header plumbing (issue #20602).

desktop_backend.py builds a separate FastAPI app from main.py and must install
BYOKMiddleware itself for the contextvar BYOK readers (get_byok_key, etc.) to
see the X-BYOK-* headers desktop chat sends. Without it, validated BYOK keys
are silently ignored on every desktop chat request.
"""

import desktop_backend
from tests.unit.test_desktop_backend_cors import _test_client
from utils.byok import get_byok_key


def test_desktop_backend_installs_byok_middleware(monkeypatch):
    monkeypatch.delenv('CORS_ALLOWED_ORIGINS', raising=False)
    app = desktop_backend._build_app()

    captured = {}

    @app.get('/__test_byok_probe')
    def _probe():
        captured['openai'] = get_byok_key('openai')
        return {'ok': True}

    client = _test_client(monkeypatch, app)
    with client:
        with_header = client.get('/__test_byok_probe', headers={'X-BYOK-OpenAI': 'probe-key'})
        captured_with_header = dict(captured)
        without_header = client.get('/__test_byok_probe')
        captured_without_header = dict(captured)

    assert with_header.status_code == 200
    assert captured_with_header['openai'] == 'probe-key'
    assert without_header.status_code == 200
    assert captured_without_header['openai'] is None
