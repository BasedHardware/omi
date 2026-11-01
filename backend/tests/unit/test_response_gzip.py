"""Hermetic tests for GatedGZipMiddleware (utils/other/response_gzip.py)."""

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from utils.other.response_gzip import GatedGZipMiddleware, _is_exempt

BIG_BODY = {'blob': 'x' * 8000}


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(GatedGZipMiddleware)

    @app.get('/v1/big')
    async def big():
        return BIG_BODY

    @app.get('/v1/small')
    async def small():
        return {'ok': True}

    @app.post('/v1/tts/synthesize')
    async def tts():
        return StreamingResponse(iter([b'A' * 8000]), media_type='audio/mpeg')

    @app.get('/v1/sync/audio/cid/afid')
    async def audio():
        return StreamingResponse(iter([b'B' * 8000]), media_type='audio/ogg')

    @app.post('/v2/chat/completions')
    async def completions():
        return StreamingResponse(iter([b'{"tok": "' + b'x' * 8000 + b'"}']), media_type='application/json')

    return app


client = TestClient(_build_app())


def test_large_json_is_gzipped_when_client_accepts():
    r = client.get('/v1/big', headers={'Accept-Encoding': 'gzip'})
    assert r.status_code == 200
    assert r.headers.get('content-encoding') == 'gzip'
    assert r.headers.get('vary') == 'Accept-Encoding'
    # httpx transparently decompresses, proving the body is valid gzip.
    assert r.json() == BIG_BODY


def test_large_json_identity_without_accept_encoding():
    r = client.get('/v1/big', headers={'Accept-Encoding': 'identity'})
    assert r.status_code == 200
    assert 'content-encoding' not in r.headers
    assert r.json() == BIG_BODY


def test_gzip_qvalue_zero_is_not_compressed():
    r = client.get('/v1/big', headers={'Accept-Encoding': 'gzip;q=0, identity;q=1'})
    assert r.status_code == 200
    assert 'content-encoding' not in r.headers
    assert r.json() == BIG_BODY


def test_deflate_only_is_not_compressed():
    r = client.get('/v1/big', headers={'Accept-Encoding': 'deflate'})
    assert r.status_code == 200
    assert 'content-encoding' not in r.headers


def test_small_response_skipped_below_minimum_size():
    r = client.get('/v1/small', headers={'Accept-Encoding': 'gzip'})
    assert r.status_code == 200
    assert 'content-encoding' not in r.headers
    assert r.json() == {'ok': True}


def test_streaming_tts_route_not_compressed():
    r = client.post('/v1/tts/synthesize', headers={'Accept-Encoding': 'gzip'})
    assert r.status_code == 200
    assert 'content-encoding' not in r.headers
    assert r.content == b'A' * 8000


def test_streaming_audio_prefix_not_compressed():
    r = client.get('/v1/sync/audio/cid/afid', headers={'Accept-Encoding': 'gzip'})
    assert r.status_code == 200
    assert 'content-encoding' not in r.headers
    assert r.content == b'B' * 8000


def test_conditional_stream_route_not_compressed():
    r = client.post('/v2/chat/completions', headers={'Accept-Encoding': 'gzip'})
    assert r.status_code == 200
    assert 'content-encoding' not in r.headers


def test_all_streaming_response_routes_are_exempt():
    """Every router route declared response_class=StreamingResponse must be
    exempted in response_gzip, so no future streaming route silently gets
    buffered by the compressor. Scans router source with ast instead of
    importing the routers (import cost would trip the fast-unit CPU guard)."""
    import ast
    from pathlib import Path

    routers_dir = Path(__file__).resolve().parents[2] / 'routers'
    scanned = 0
    streaming_paths = set()
    for source_path in routers_dir.glob('*.py'):
        source = source_path.read_text()
        if 'StreamingResponse' not in source:
            # Cheap pre-filter: a router that never names StreamingResponse
            # cannot declare a response_class=StreamingResponse route, and
            # ast.parse over the whole routers/ dir trips the fast-unit CPU
            # guard (1.07s > 1.00s on CI as routers grow).
            continue
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for deco in node.decorator_list:
                if not isinstance(deco, ast.Call) or not isinstance(deco.func, ast.Attribute):
                    continue
                if deco.func.attr not in {'get', 'post', 'put', 'patch', 'delete'}:
                    continue
                has_streaming_class = any(
                    kw.arg == 'response_class' and isinstance(kw.value, ast.Name) and kw.value.id == 'StreamingResponse'
                    for kw in deco.keywords
                )
                if not has_streaming_class:
                    continue
                scanned += 1
                if deco.args and isinstance(deco.args[0], ast.Constant):
                    streaming_paths.add(deco.args[0].value)
    assert scanned >= 4, f'route scan found {scanned} streaming routes; the drift pin is broken'
    missing = {p for p in streaming_paths if not _is_exempt(p)}
    assert not missing, f'streaming routes not exempt from gzip: {sorted(missing)}'
