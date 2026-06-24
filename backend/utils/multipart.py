from collections.abc import Callable

from fastapi import HTTPException, Request
from fastapi.routing import APIRoute
from starlette.datastructures import FormData
from starlette.formparsers import MultiPartException, MultiPartParser

MULTIPART_MAX_PART_SIZE_ATTR = '_multipart_max_part_size'

MB = 1024 * 1024

APP_IMAGE_MAX_PART_SIZE = 10 * MB
CHAT_FILE_MAX_PART_SIZE = 50 * MB
IMPORT_MAX_PART_SIZE = 100 * MB
PHONE_CALL_MAX_PART_SIZE = 5 * MB
SPEECH_PROFILE_MAX_PART_SIZE = 25 * MB
SYNC_AUDIO_MAX_PART_SIZE = 50 * MB
VOICE_MESSAGE_MAX_PART_SIZE = 200 * MB


def max_part_size(bytes_size: int):
    def decorator(endpoint: Callable):
        setattr(endpoint, MULTIPART_MAX_PART_SIZE_ATTR, bytes_size)
        return endpoint

    return decorator


class MultipartMaxPartSizeRoute(APIRoute):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.multipart_max_part_size = getattr(self.endpoint, MULTIPART_MAX_PART_SIZE_ATTR, None)

    def get_route_handler(self) -> Callable:
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request):
            if self.multipart_max_part_size is not None and _is_multipart(request):
                await parse_multipart_form(request, max_part_size=self.multipart_max_part_size)
            return await original_route_handler(request)

        return custom_route_handler


class FileSizeLimitedMultiPartParser(MultiPartParser):
    def on_part_begin(self) -> None:
        super().on_part_begin()
        self._current_file_part_size = 0

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        message_bytes = data[start:end]
        if self._current_part.file is not None:
            self._current_file_part_size += len(message_bytes)
            if self._current_file_part_size > self.max_part_size:
                raise MultiPartException(f"Part exceeded maximum size of {int(self.max_part_size / 1024)}KB.")
        super().on_part_data(data, start, end)


async def parse_multipart_form(request: Request, *, max_part_size: int) -> FormData:
    if request._form is not None:
        return request._form
    if not _is_multipart(request):
        return await request.form()

    parser = FileSizeLimitedMultiPartParser(request.headers, request.stream(), max_part_size=max_part_size)
    try:
        request._form = await parser.parse()
    except MultiPartException as exc:
        raise HTTPException(status_code=400, detail=exc.message)
    return request._form


def _is_multipart(request: Request) -> bool:
    return request.headers.get('content-type', '').lower().startswith('multipart/form-data')
