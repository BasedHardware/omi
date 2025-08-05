from typing import Any, Union, Optional, IO, Mapping, Tuple, List, cast
import aiohttp
import urllib.parse
import urllib.request
import urllib.error
import io
import json
import re
import platform
import websockets
import websockets.client
import websockets.exceptions
import warnings
from ._constants import DEFAULT_ENDPOINT
from ._types import Options
from ._version import __version__
from .errors import DeepgramApiError

Payload = Optional[Union[dict, str, bytes, IO]]

RETRY_COUNT = 4


def _prepare_headers(
    options: Options, headers: Mapping[str, str] = None
) -> dict:
    if headers is None:
        headers = {}
    auth = (
        None if 'api_key' not in options
        else cast(str, options.get('auth_method', 'Token'))
        + ' ' + options['api_key']
    )
    return {
        **headers,
        'Authorization': auth,
        'User-Agent': (
            f'deepgram/{__version__} python/{platform.python_version()}'
        )
    }


def _normalize_payload(payload: Payload) -> Optional[Union[bytes, IO]]:
    if payload is None:
        return None
    if isinstance(payload, dict):
        return json.dumps(payload).encode('utf-8')
    if isinstance(payload, str):
        return payload.encode('utf-8')
    return payload


def _make_query_string(params: Mapping[str, Any] = None) -> str:
    if params is None:
        params = {}

    def elem_decomposer(key: str, value: Any) -> List[Tuple[str, str]]:
        if value in [None, ""]:
            return []
        if isinstance(value, list):
            # break into multiple parameters
            return [elem_decomposer(key, item)[0] for item in value]
            # just take the first element in the sublist,
            # rather than trying to flatten recursively
            # passing nested lists as query parameters
            # isn't really well-defined, nor does anything
            # in our API currently take things like that as of 2021-08-10
            # so everything coming through this second pass
            # should be a 1-item list
        if isinstance(value, bool):
            # make sure False and True stay lowercased
            # in accordance with DG convention
            return [(key, str(value).lower())]
        return [(key, str(value))]

    # sublist for each original parameter
    unflattened = [elem_decomposer(k, v) for k, v in params.items()]
    # flatten
    flattened: List[Tuple[str, str]] = sum(unflattened, [])
    return ('?' if flattened else '') + urllib.parse.urlencode(flattened)


async def _request(
    path: str, options: Options,
    method: str = 'GET', payload: Payload = None,
    headers: Optional[Mapping[str, str]] = None,
    timeout: float = None,
) -> Any:
    if headers is None:
        headers = {}
    destination = cast(str, options.get('api_url', DEFAULT_ENDPOINT)) + path
    updated_headers = _prepare_headers(options, headers)

    if timeout is None:
        timeout = aiohttp.client.DEFAULT_TIMEOUT
    else:
        timeout = aiohttp.ClientTimeout(total=timeout)

    async def attempt():
        # Define `content` outside the try block so we can differentiate between errors
        # thrown by `aiohttp.request` and `resp.raise_for_status()`. This can be removed
        # after the aiohttp issue mentioned below is fixed.
        content = None
        try:
            async with aiohttp.request(
                method, destination, data=_normalize_payload(payload),
                headers=updated_headers, timeout=timeout
            ) as resp:
                # The error handling for this async code is more difficult than normal
                # because aiohttp does not include the response body in the exception
                # object. We therefore need to read the response body before throwing
                # an error, and attach the response body to the error. This should
                # be fixed by aiohttp in v4.x. See the github issue here for info:
                # https://github.com/aio-libs/aiohttp/issues/4600
                # Once that work is complete, we can use `raise_for_status=True` as a
                # parameter in the `aiohttp.request` call.
                content = (await resp.text()).strip()
                resp.raise_for_status()
                if not content:
                    return None
                body = json.loads(content)
                if body.get('error') or body.get('err_msg'):
                    raise DeepgramApiError(body, http_library_error=None)
                if options.get("raise_warnings_as_errors") and "metadata" in body and "warnings" in body["metadata"]:
                    raise DeepgramApiError({"warnings": body["metadata"]["warnings"]}, http_library_error=None)
                if (not options.get("suppress_warnings")) and "metadata" in body and "warnings" in body["metadata"]:
                    for warning in body["metadata"]["warnings"]:
                        warnings.warn(warning["message"])
                return body
        except aiohttp.ClientResponseError as exc:
            # If the request returned a response body and errored, return the response body.
            # Otherwise return the request's error message.
            if content is not None:
                try:
                    body = json.loads(content)
                    raise DeepgramApiError(body, http_library_error=exc) from exc if exc.status < 500 else exc
                except:
                    pass
            else:
                raise DeepgramApiError(exc.message, http_library_error=exc) from exc if exc.status < 500 else exc
        except aiohttp.ClientError as exc:
            raise DeepgramApiError(exc, http_library_error=exc) from exc

    tries = RETRY_COUNT
    while tries > 0:
        try:
            return await attempt()
        except aiohttp.ClientError as exc:
            if isinstance(payload, io.IOBase):
                # stream is now invalid as payload
                # the way aiohttp handles streaming form data
                # means that just seeking this back still runs into issues
                raise DeepgramApiError(exc, http_library_error=exc) from exc 
            tries -= 1
            continue
    return await attempt()


def _sync_request(
    path: str, options: Options,
    method: str = 'GET', payload: Payload = None,
    headers: Optional[Mapping[str, str]] = None,
    timeout: float = None
) -> Any:
    if headers is None:
        headers = {}
    destination = cast(str, options.get('api_url', DEFAULT_ENDPOINT)) + path
    updated_headers = _prepare_headers(options, headers)

    def attempt():
        req = urllib.request.Request(
            destination, 
            data=_normalize_payload(payload), 
            headers=updated_headers, 
            method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                content = resp.read().strip()
                if not content:
                    return None
                body = json.loads(content)
                if body.get('error') or body.get('err_msg'):
                    raise DeepgramApiError(body, http_library_error=None)
                if options.get("raise_warnings_as_errors") and "metadata" in body and "warnings" in body["metadata"]:
                    raise DeepgramApiError({"warnings": body["metadata"]["warnings"]}, http_library_error=None)
                if (not options.get("suppress_warnings")) and "metadata" in body and "warnings" in body["metadata"]:
                    for warning in body["metadata"]["warnings"]:
                        warnings.warn(warning["message"])
                return body
        except urllib.error.HTTPError as exc:
            # Try to get the HTTP error's request body. Deepgram returns a JSON response
            # body for error messages. We want to return that as the error message if
            # it exists.
            try:
                error_body = json.loads(exc.read().decode("utf-8"))
            except Exception:
                error_body = str(exc)
            raise DeepgramApiError(error_body, http_library_error=exc) from exc

    tries = RETRY_COUNT
    while tries > 0:
        try:
            return attempt()
        except urllib.error.URLError as exc:
            if isinstance(payload, io.IOBase):
                # stream is now invalid as payload
                # the way aiohttp handles streaming form data
                # means that just seeking this back still runs into issues
                raise DeepgramApiError(exc, http_library_error=exc) from exc
            tries -= 1
            continue
    return attempt()


async def _socket_connect(
    path: str, options: Options, headers: Optional[Mapping[str, str]] = None
) -> websockets.client.WebSocketClientProtocol:
    if headers is None:
        headers = {}
    destination = re.sub(
        r'^http', 'ws', cast(str, options.get('api_url', DEFAULT_ENDPOINT))
    ) + path
    updated_headers = _prepare_headers(options, headers)

    async def attempt():
        try:
            # If we're streaming too much faster than realtime,
            # connection might close without an aggressive ping interval
            return await websockets.connect(
                destination, extra_headers=updated_headers, ping_interval=5
            )
        except websockets.exceptions.InvalidHandshake as exc:
            raise DeepgramApiError(exc, http_library_error=exc) from exc

    tries = RETRY_COUNT
    while tries > 0:
        try:
            return await attempt()
        except Exception as exc:
            tries -= 1
            continue
    return await attempt()
