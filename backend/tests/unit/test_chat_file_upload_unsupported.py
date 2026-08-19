"""POST /v1|/v2/files answers 400 for a file type the pipeline cannot process, never 500.

Live prod signature (backend image c5b0b5d, api.omi.me):
  * ``PIL.UnidentifiedImageError: cannot identify image file '/tmp/<uuid>_<name>.heic'``
    - mimetypes maps .heic to image/heic, so File.is_image() is true and generate_thumbnail()
      runs, but Pillow ships no HEIF decoder. An iPhone camera-roll photo 500'd.
  * ``openai.BadRequestError: Invalid extension ogg`` from openai.files.create - the provider's
    accepted-extension list has no audio formats. An .ogg voice note 500'd.

Both are ordinary user input arriving over a public route, so both belong on the 4xx side of the
request boundary. The route is driven over HTTP here (real routers.chat, real utils.other.chat_file)
so the assertion is the status code the client actually receives.
"""

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import openai
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.unit import _chat_router_test_harness as harness
from tests.unit._chat_router_test_harness import BACKEND_DIR

# A one-byte payload with a .heic name: mimetypes keys off the extension, and Pillow fails to
# identify the bytes exactly as it does for real HEIC input.
HEIC_BYTES = b'\x00\x00\x00\x18ftypheic\x00\x00\x00\x00heicmif1'
OGG_BYTES = b'OggS\x00\x02' + b'\x00' * 20


def _make_chat_client():
    saved = {k: v for k, v in sys.modules.items()}

    harness.install_package('models', BACKEND_DIR / 'models')
    harness.install_package('database', BACKEND_DIR / 'database')
    harness.install_package('utils', BACKEND_DIR / 'utils')
    harness.install_package('utils.other', BACKEND_DIR / 'utils' / 'other')
    harness.install_package('utils.sync', BACKEND_DIR / 'utils' / 'sync')
    harness.install_package('utils.stt', BACKEND_DIR / 'utils' / 'stt')
    harness.install_package('utils.llm', BACKEND_DIR / 'utils' / 'llm')
    harness.install_package('utils.retrieval', BACKEND_DIR / 'utils' / 'retrieval')

    harness.wire_common_stubs(harness.install_module)
    harness.install_module('models.app')

    # The gateway telemetry chat_file imports is out of scope here (and pulls the real gateway
    # client stack in); keep it inert so the upload path itself is what runs.
    gateway_client = harness.install_module('utils.llm.gateway_client', ModuleType('utils.llm.gateway_client'))
    gateway_client.should_route_features_through_gateway = MagicMock(return_value=False)
    gateway_obs = harness.install_module(
        'utils.llm.gateway_observability', ModuleType('utils.llm.gateway_observability')
    )
    gateway_obs.record_direct_exception_surface = MagicMock()

    # wire_common_stubs replaces chat_file with a MagicMock; this suite needs the real module,
    # because the defect lives in its PIL and provider error handling.
    harness.load_real_module('utils.other.chat_file', BACKEND_DIR / 'utils' / 'other' / 'chat_file.py')

    chat_utils = harness.install_module('utils.chat', ModuleType('utils.chat'))
    for name in (
        'acquire_chat_session',
        'emit_stream_error_fallback',
        'initial_message_util',
        'process_voice_message_segment_stream',
        'resolve_voice_message_language',
        'transcribe_voice_message_segment',
        'transcribe_pcm_bytes',
    ):
        setattr(chat_utils, name, MagicMock())

    graph = harness.install_module('utils.retrieval.graph', ModuleType('utils.retrieval.graph'))
    graph.execute_chat_stream = MagicMock()
    graph.execute_graph_chat = MagicMock()
    graph.execute_persona_chat_stream = MagicMock()

    sys.modules.pop('routers.chat', None)
    module = harness.load_real_module('routers.chat', BACKEND_DIR / 'routers' / 'chat.py')

    app = FastAPI()
    app.include_router(module.router)
    return TestClient(app), module, saved


@pytest.fixture
def chat_client():
    client, module, saved = _make_chat_client()
    try:
        yield client, module
    finally:
        harness.cleanup(saved)


def _bad_request(**_kwargs):
    raise openai.BadRequestError(
        message="Error code: 400 - Invalid extension ogg.",
        response=SimpleNamespace(request=None, status_code=400, headers={}),
        body=None,
    )


@pytest.mark.parametrize('route', ['/v2/files', '/v1/files'])
def test_heic_photo_is_rejected_as_bad_request(chat_client, route, monkeypatch):
    client, module = chat_client
    chat_file = sys.modules['utils.other.chat_file']
    # Nothing should reach the provider: the failure is local, in thumbnail generation.
    monkeypatch.setattr(chat_file.openai, 'files', SimpleNamespace(create=_unreachable))

    response = client.post(route, files={'files': ('photo.heic', HEIC_BYTES, 'image/heic')})

    assert response.status_code == 400
    assert 'heic' in response.json()['detail']
    module.chat_db.add_multi_files.assert_not_called()


@pytest.mark.parametrize('route', ['/v2/files', '/v1/files'])
def test_provider_rejected_extension_is_bad_request(chat_client, route, monkeypatch):
    client, module = chat_client
    chat_file = sys.modules['utils.other.chat_file']
    monkeypatch.setattr(chat_file.openai, 'files', SimpleNamespace(create=_bad_request))

    response = client.post(route, files={'files': ('note.ogg', OGG_BYTES, 'audio/ogg')})

    assert response.status_code == 400
    assert 'ogg' in response.json()['detail']
    module.chat_db.add_multi_files.assert_not_called()


def test_supported_file_still_uploads(chat_client, monkeypatch):
    """The guard must not swallow the happy path."""
    client, module = chat_client
    chat_file = sys.modules['utils.other.chat_file']
    monkeypatch.setattr(
        chat_file.openai,
        'files',
        SimpleNamespace(create=lambda **_kwargs: SimpleNamespace(id='file-1', filename='note.txt')),
    )

    response = client.post('/v2/files', files={'files': ('note.txt', b'hello', 'text/plain')})

    assert response.status_code == 200
    assert response.json()[0]['openai_file_id'] == 'file-1'
    module.chat_db.add_multi_files.assert_called_once()


def _unreachable(**_kwargs):
    raise AssertionError('provider upload must not be attempted for an undecodable image')
