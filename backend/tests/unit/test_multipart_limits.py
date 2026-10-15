import ast
import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.datastructures import Headers
from starlette.formparsers import MultiPartException, MultiPartParser
from starlette.requests import Request

from utils.multipart import FileSizeLimitedMultiPartParser, MultipartLimits, parse_multipart_form

BACKEND_DIR = Path(__file__).resolve().parents[2]

EXPECTED_ROUTE_LIMITS = {
    'routers/apps.py': {
        ('POST', '/v1/apps'): 'APP_IMAGE_MAX_PART_SIZE',
        ('POST', '/v1/personas'): 'APP_IMAGE_MAX_PART_SIZE',
        ('PATCH', '/v1/personas/{persona_id}'): 'APP_IMAGE_MAX_PART_SIZE',
        ('PATCH', '/v1/apps/{app_id}'): 'APP_IMAGE_MAX_PART_SIZE',
        ('POST', '/v1/app/thumbnails'): 'APP_IMAGE_MAX_PART_SIZE',
    },
    'routers/chat.py': {
        ('POST', '/v2/voice-messages'): 'VOICE_MESSAGE_MAX_PART_SIZE',
        ('POST', '/v2/voice-message/transcribe'): 'VOICE_MESSAGE_MAX_PART_SIZE',
        ('POST', '/v2/files'): 'CHAT_FILE_MAX_PART_SIZE',
        ('POST', '/v1/files'): 'CHAT_FILE_MAX_PART_SIZE',
    },
    'routers/imports.py': {
        ('POST', '/v1/import/limitless'): 'IMPORT_MAX_PART_SIZE',
        ('POST', '/v1/import/transcripts'): 'IMPORT_MAX_PART_SIZE',
    },
    'routers/phone_calls.py': {
        ('POST', '/v1/phone/twiml'): 'PHONE_CALL_MAX_PART_SIZE',
    },
    'routers/speech_profile.py': {
        ('POST', '/v3/upload-audio'): 'SPEECH_PROFILE_MAX_PART_SIZE',
    },
    'routers/sync.py': {
        ('POST', '/v1/sync-local-files'): 'SYNC_AUDIO_MAX_PART_SIZE',
        ('POST', '/v2/sync-local-files'): 'SYNC_AUDIO_MAX_PART_SIZE',
    },
}


def _route_limits_for_file(relative_path: str) -> dict[tuple[str, str], str]:
    tree = ast.parse((BACKEND_DIR / relative_path).read_text())
    route_limits = {}

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        route_keys = []
        limit_name = None
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            if isinstance(decorator.func, ast.Attribute) and isinstance(decorator.func.value, ast.Name):
                if (
                    decorator.func.value.id == 'router'
                    and decorator.args
                    and isinstance(decorator.args[0], ast.Constant)
                ):
                    route_keys.append((decorator.func.attr.upper(), decorator.args[0].value))
            if isinstance(decorator.func, ast.Name) and decorator.func.id == 'max_part_size':
                if decorator.args and isinstance(decorator.args[0], ast.Name):
                    limit_name = decorator.args[0].id

        if limit_name:
            for route_key in route_keys:
                route_limits[route_key] = limit_name
            continue

        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            if not isinstance(child.func, ast.Name) or child.func.id != 'parse_multipart_form':
                continue
            for keyword in child.keywords:
                if keyword.arg == 'max_part_size' and isinstance(keyword.value, ast.Name):
                    for route_key in route_keys:
                        route_limits[route_key] = keyword.value.id

    return route_limits


async def _body_stream(body: bytes):
    yield body
    yield b''


async def _chunked_body_stream(chunks: list[bytes]):
    for chunk in chunks:
        yield chunk
    yield b''


def _multipart_body(name: str, value: bytes, filename: str | None = None) -> tuple[Headers, bytes]:
    boundary = 'test-boundary'
    disposition = f'Content-Disposition: form-data; name="{name}"'
    content_type = ''
    if filename is not None:
        disposition += f'; filename="{filename}"'
        content_type = 'Content-Type: audio/wav\r\n'

    body = (
        (f'--{boundary}\r\n' f'{disposition}\r\n' f'{content_type}' '\r\n').encode()
        + value
        + f'\r\n--{boundary}--\r\n'.encode()
    )
    headers = Headers({'Content-Type': f'multipart/form-data; boundary={boundary}'})
    return headers, body


async def _parse_body(headers: Headers, body: bytes, max_part_size: int):
    parser = FileSizeLimitedMultiPartParser(headers, _body_stream(body), max_part_size=max_part_size)
    return await parser.parse()


def _request_with_body(content_type: str, body: bytes) -> Request:
    async def receive():
        return {'type': 'http.request', 'body': body, 'more_body': False}

    scope = {
        'type': 'http',
        'method': 'POST',
        'path': '/',
        'headers': [(b'content-type', content_type.encode())],
        'query_string': b'',
    }
    return Request(scope, receive)


def _chunked_request(headers: Headers, chunks: list[bytes], *, content_length: int | None = None):
    """A request whose body arrives chunk by chunk; ``received`` counts the chunks the server pulled."""
    pending = list(chunks)
    received = []

    async def receive():
        chunk = pending.pop(0)
        received.append(chunk)
        return {'type': 'http.request', 'body': chunk, 'more_body': bool(pending)}

    raw_headers = [(b'content-type', headers['content-type'].encode())]
    if content_length is not None:
        raw_headers.append((b'content-length', str(content_length).encode()))
    scope = {'type': 'http', 'method': 'POST', 'path': '/', 'headers': raw_headers, 'query_string': b''}
    return Request(scope, receive), received


def _multipart_files(*parts: tuple[str, bytes]) -> tuple[Headers, bytes]:
    boundary = 'test-boundary'
    body = b''.join(
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{name}.srt"\r\n'
            'Content-Type: text/plain\r\n\r\n'
        ).encode()
        + value
        + b'\r\n'
        for name, value in parts
    )
    body += f'--{boundary}--\r\n'.encode()
    return Headers({'Content-Type': f'multipart/form-data; boundary={boundary}'}), body


SINGLE_FILE = MultipartLimits(max_files=1, max_fields=0, max_body_size=10_000)


def test_multipart_parser_rejects_file_part_over_limit():
    headers, body = _multipart_body('file', b'123456789', filename='sample.wav')

    with pytest.raises(MultiPartException, match='Part exceeded maximum size'):
        asyncio.run(_parse_body(headers, body, max_part_size=8))


def test_multipart_parser_counts_file_bytes_across_request_chunks():
    headers, body = _multipart_body('file', b'123456789', filename='sample.wav')
    payload_start = body.index(b'123456789')
    chunks = [body[: payload_start + 5], body[payload_start + 5 :]]
    parser = FileSizeLimitedMultiPartParser(headers, _chunked_body_stream(chunks), max_part_size=8)

    with pytest.raises(MultiPartException, match='Part exceeded maximum size'):
        asyncio.run(parser.parse())


def test_multipart_parser_allows_file_part_at_limit():
    headers, body = _multipart_body('file', b'12345678', filename='sample.wav')

    form = asyncio.run(_parse_body(headers, body, max_part_size=8))

    assert form['file'].size == 8


def test_multipart_parser_rejects_form_field_over_limit():
    headers, body = _multipart_body('payload', b'123456789')

    with pytest.raises(MultiPartException, match='Part exceeded maximum size'):
        asyncio.run(_parse_body(headers, body, max_part_size=8))


def test_parse_multipart_form_preserves_urlencoded_forms():
    request = _request_with_body('application/x-www-form-urlencoded', b'From=user-1&To=%2B15555550123')

    form = asyncio.run(parse_multipart_form(request, max_part_size=64))

    assert form['From'] == 'user-1'
    assert form['To'] == '+15555550123'


def test_parse_multipart_form_rejects_oversized_urlencoded_body():
    request = _request_with_body('application/x-www-form-urlencoded', b'From=user-1&To=%2B15555550123')

    with pytest.raises(HTTPException, match='Form body exceeded maximum size'):
        asyncio.run(parse_multipart_form(request, max_part_size=8))


def test_starlette_global_multipart_limit_is_not_mutated():
    assert MultiPartParser.max_part_size == 1024 * 1024


def test_production_multipart_routes_have_declared_limits():
    for relative_path, expected_limits in EXPECTED_ROUTE_LIMITS.items():
        route_limits = _route_limits_for_file(relative_path)
        for route_key, expected_limit in expected_limits.items():
            assert route_limits.get(route_key) == expected_limit


def test_a_second_file_part_is_refused_before_its_bytes_are_read():
    headers, body = _multipart_files(('file', b'a' * 100), ('unused', b'b' * 5000))
    split = body.index(b'b' * 5000) + 10
    request, received = _chunked_request(headers, [body[:split], body[split:]])

    with pytest.raises(HTTPException, match='Too many files') as error:
        asyncio.run(parse_multipart_form(request, max_part_size=8000, limits=SINGLE_FILE))

    assert error.value.status_code == 400
    assert len(received) == 1, 'the rest of the extra part is never pulled'


def test_form_fields_are_refused_when_the_route_takes_none():
    headers, body = _multipart_body('payload', b'value')
    request, _ = _chunked_request(headers, [body])

    with pytest.raises(HTTPException, match='Too many fields'):
        asyncio.run(parse_multipart_form(request, max_part_size=8000, limits=SINGLE_FILE))


def test_the_whole_body_is_bounded_while_it_streams_without_a_content_length():
    """Parts each under the per-part cap can still add up past the request limit."""
    headers, body = _multipart_files(('file', b'a' * 6000))
    chunks = [body[i : i + 4000] for i in range(0, len(body), 4000)] + [b'tail' * 2000]
    request, received = _chunked_request(headers, chunks)
    limits = MultipartLimits(max_files=1, max_fields=0, max_body_size=len(body) - 1)

    with pytest.raises(HTTPException, match='Form body exceeded maximum size') as error:
        asyncio.run(parse_multipart_form(request, max_part_size=8000, limits=limits))

    assert error.value.status_code == 400
    assert len(received) < len(chunks), 'reading stopped at the limit'


def test_a_declared_content_length_over_the_limit_is_refused_before_reading():
    headers, body = _multipart_files(('file', b'a' * 100))
    request, received = _chunked_request(headers, [body], content_length=SINGLE_FILE.max_body_size + 1)

    with pytest.raises(HTTPException, match='Form body exceeded maximum size'):
        asyncio.run(parse_multipart_form(request, max_part_size=8000, limits=SINGLE_FILE))

    assert received == []


def test_one_file_within_the_limits_parses():
    headers, body = _multipart_files(('file', b'a' * 100))
    request, _ = _chunked_request(headers, [body], content_length=len(body))

    form = asyncio.run(parse_multipart_form(request, max_part_size=8000, limits=SINGLE_FILE))

    assert form['file'].size == 100
    form['file'].file.close()


def test_routes_without_request_limits_keep_starlettes_part_counts():
    headers, body = _multipart_files(('file', b'a'), ('other', b'b'))
    request, _ = _chunked_request(headers, [body])

    form = asyncio.run(parse_multipart_form(request, max_part_size=8000))

    assert sorted(form.keys()) == ['file', 'other']
    for value in form.values():
        value.file.close()
