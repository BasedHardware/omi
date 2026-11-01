"""app_build is populated on the listen-accepted metric from the client's X-App-Version (lane 14, plan B O2)."""

import ast
from pathlib import Path

from utils.client_device import resolve_client_device
from utils.metrics import OMI_LISTEN_ACCEPTED_TOTAL
from utils.observability.transcription import record_listen_session_accepted
from utils.product_metrics import sanitize_app_build

RUNTIME = Path(__file__).resolve().parents[2] / 'routers' / 'listen' / 'runtime.py'


def _runtime_accept_call() -> ast.Call:
    calls = [
        node
        for node in ast.walk(ast.parse(RUNTIME.read_text(encoding='utf-8')))
        if isinstance(node, ast.Call)
        and getattr(node.func, 'id', None) == 'record_listen_session_accepted'
        and node.keywords
    ]
    assert len(calls) == 1
    return calls[0]


def test_runtime_passes_the_sanitized_client_version():
    keywords = {keyword.arg: keyword.value for keyword in _runtime_accept_call().keywords}
    assert 'app_build' in keywords
    assert (
        ast.unparse(keywords['app_build'])
        == "sanitize_app_build(getattr(self.client_device_context, 'app_version', None))"
    )


def test_flutter_version_header_becomes_the_build_number_label():
    device = resolve_client_device(x_app_platform='ios', x_app_version='1.0.522+98765')
    build = sanitize_app_build(device.app_version)
    assert build == '98765'
    labels = dict(transcription_source='omi', client_platform='ios', app_build=build)
    before = OMI_LISTEN_ACCEPTED_TOTAL.labels(**labels)._value.get()
    record_listen_session_accepted(source='omi', platform='ios', app_build=build)
    assert OMI_LISTEN_ACCEPTED_TOTAL.labels(**labels)._value.get() == before + 1


def test_missing_or_hostile_versions_stay_unknown():
    for raw in (None, '', 'Mozilla/5.0 (X11)', 'x' * 100):
        assert sanitize_app_build(resolve_client_device(x_app_version=raw).app_version) == 'unknown'
