from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar, cast

from fastapi import HTTPException, Request
from fastapi.routing import APIRoute
from starlette.datastructures import FormData
from starlette.formparsers import FormParser, MultiPartException, MultiPartParser

MULTIPART_MAX_PART_SIZE_ATTR = '_multipart_max_part_size'
MULTIPART_LIMITS_ATTR = '_multipart_limits'
_Endpoint = TypeVar('_Endpoint', bound=Callable[..., Any])

MB = 1024 * 1024

APP_IMAGE_MAX_PART_SIZE = 10 * MB
CHAT_FILE_MAX_PART_SIZE = 50 * MB
IMPORT_MAX_PART_SIZE = 100 * MB
PHONE_CALL_MAX_PART_SIZE = 5 * MB
SPEECH_PROFILE_MAX_PART_SIZE = 50 * MB
SYNC_AUDIO_MAX_PART_SIZE = 200 * MB
VOICE_MESSAGE_MAX_PART_SIZE = 200 * MB

# Boundaries and part headers on top of the parts' own bytes.
MULTIPART_OVERHEAD_BYTES = 64 * 1024


@dataclass(frozen=True)
class MultipartLimits:
    """Whole-request limits for a multipart route, enforced while the body is parsed.

    A route that declares them accepts only a multipart body (415 otherwise).

    The route parses the form before its dependencies (auth, rate limits) run, and the
    per-part cap bounds each part alone, so these bound what any request, signed in or
    not, can make the server read and spool: file parts, other fields, and total bytes.
    """

    max_files: int
    max_fields: int
    max_body_size: int


def single_file_limits(part_size: int) -> MultipartLimits:
    """One file part, no other fields, and a body no larger than that file allows."""
    return MultipartLimits(max_files=1, max_fields=0, max_body_size=part_size + MULTIPART_OVERHEAD_BYTES)


def max_part_size(bytes_size: int):
    def decorator(endpoint: Callable):
        setattr(endpoint, MULTIPART_MAX_PART_SIZE_ATTR, bytes_size)
        return endpoint

    return decorator


def multipart_limits(limits: MultipartLimits) -> Callable[[_Endpoint], _Endpoint]:
    """Whole-request limits for a route that also declares ``max_part_size``."""

    def decorator(endpoint: _Endpoint) -> _Endpoint:
        setattr(endpoint, MULTIPART_LIMITS_ATTR, limits)
        return endpoint

    return decorator


class MultipartMaxPartSizeRoute(APIRoute):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.multipart_max_part_size = getattr(self.endpoint, MULTIPART_MAX_PART_SIZE_ATTR, None)
        self.multipart_limits: MultipartLimits | None = getattr(self.endpoint, MULTIPART_LIMITS_ATTR, None)
        if self.multipart_limits is not None and self.multipart_max_part_size is None:
            raise ValueError(f'{self.path}: multipart_limits needs max_part_size as well')

    def get_route_handler(self) -> Callable:
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request):
            if self.path == '/v1/import/transcripts':
                scheme, _, token = request.headers.get('authorization', '').partition(' ')
                if scheme.lower() != 'bearer' or not token.strip():
                    raise HTTPException(status_code=401, detail='Bearer token required')
            if self.multipart_limits is not None and not _is_multipart(request):
                # The limits bound a multipart body; any other body would be read unbounded,
                # and before auth, by the route's own form handling.
                raise HTTPException(status_code=415, detail='Upload the file as multipart/form-data.')
            if self.multipart_max_part_size is not None and _is_multipart(request):
                await parse_multipart_form(
                    request, max_part_size=self.multipart_max_part_size, limits=self.multipart_limits
                )
            return await original_route_handler(request)

        return custom_route_handler


class FileSizeLimitedMultiPartParser(MultiPartParser):
    def on_part_begin(self) -> None:
        super().on_part_begin()
        self._current_file_part_size = 0

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        if self._current_part.file is not None:
            self._current_file_part_size += end - start
            if self._current_file_part_size > self.max_part_size:
                raise MultiPartException(f"Part exceeded maximum size of {int(self.max_part_size / 1024)}KB.")
        super().on_part_data(data, start, end)


async def parse_multipart_form(
    request: Request, *, max_part_size: int, limits: MultipartLimits | None = None
) -> FormData:
    cached_form = _get_cached_form(request)
    if cached_form is not None:
        return cached_form
    if _is_urlencoded(request):
        form = await FormParser(
            request.headers,
            _size_limited_stream(request, max_size=max_part_size),
        ).parse()
        _set_cached_form(request, form)
        return form
    if not _is_multipart(request):
        return await request.form()

    if limits is None:
        parser = FileSizeLimitedMultiPartParser(request.headers, request.stream(), max_part_size=max_part_size)
    else:
        # Raised as MultiPartException inside the parse, so the parser closes the files it opened.
        stream = _size_limited_stream(request, max_size=limits.max_body_size, error=MultiPartException)
        parser = FileSizeLimitedMultiPartParser(
            request.headers,
            stream,
            max_files=limits.max_files,
            max_fields=limits.max_fields,
            max_part_size=max_part_size,
        )
    try:
        form = await parser.parse()
    except MultiPartException as exc:
        raise HTTPException(status_code=400, detail=exc.message)
    _set_cached_form(request, form)
    return form


def _get_cached_form(request: Request) -> FormData | None:
    return cast(FormData | None, getattr(request, '_form', None))


def _set_cached_form(request: Request, form: FormData) -> None:
    setattr(request, '_form', form)


def _is_multipart(request: Request) -> bool:
    return request.headers.get('content-type', '').lower().startswith('multipart/form-data')


def _is_urlencoded(request: Request) -> bool:
    return request.headers.get('content-type', '').lower().startswith('application/x-www-form-urlencoded')


def _bad_form_request(detail: str) -> Exception:
    return HTTPException(status_code=400, detail=detail)


async def _size_limited_stream(
    request: Request, *, max_size: int, error: Callable[[str], Exception] = _bad_form_request
):
    """The request body, refused with ``error(detail)`` once it is, or declares it will be, over ``max_size``."""
    too_large = f'Form body exceeded maximum size of {max_size} bytes.'
    content_length = request.headers.get('content-length')
    if content_length:
        try:
            declared = int(content_length)
        except ValueError:
            raise error('Invalid Content-Length header.')
        if declared > max_size:
            raise error(too_large)

    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > max_size:
            raise error(too_large)
        yield chunk
