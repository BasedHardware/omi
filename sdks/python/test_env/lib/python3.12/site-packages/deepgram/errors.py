from typing import Union, Optional
import websockets.exceptions
import urllib.error
import aiohttp
import uuid


class DeepgramError(Exception):
    pass


class DeepgramSetupError(DeepgramError, ValueError):
    pass


class DeepgramApiError(DeepgramError):
    """An error returned by the Deepgram API.

    If the error was raised by an http client, the client's error message
    is accessible via the `http_library_error` field. This may be useful
    for handling different error codes, such as 429s or 503s.

    The `error` field is set to the API's error message (dict), if avilable.
    Otherwise the `error` field is set to the parent exception's message (str).
    
    The `warning` field is set to the API's warning messages (list[str]), if available.

    The `request_id` field is set to the API's request ID, if available.
    """
    def __init__(
        self,
        *args: object,
        http_library_error: Optional[
            Union[
                urllib.error.HTTPError,
                urllib.error.URLError,
                websockets.exceptions.InvalidHandshake,
                aiohttp.ClientResponseError,
                aiohttp.ClientError,
            ]
        ] = None,
    ):
        super().__init__(*args)
        self.http_library_error = http_library_error
        self.error: Union[str, dict]  # If you change the type, change it in the docstring as well!
        self.warnings: Optional[list[str]] = None  # If you change the type, change it in the docstring as well!
        self.request_id: Optional[uuid.UUID] = None
        self.http_error_status: Optional[int] = None

        # Set the `error`, `warning`, and `request_id` fields from the incoming data object
        if isinstance(args[0], dict) and "err_msg" in args[0]:
            error_or_warning_data = args[0]
            self.error = error_or_warning_data["err_msg"]
            if "metadata" in error_or_warning_data and "warnings" in error_or_warning_data["metadata"]:
                self.warnings = error_or_warning_data["metadata"]["warnings"]
            elif "warnings" in error_or_warning_data:  # Occurs when `raise_warnings_as_errors` is enabled
                self.warnings = error_or_warning_data["warnings"]
            if "metadata" in error_or_warning_data and "request_id" in error_or_warning_data["metadata"]:  # Occurs when Deepgram returns a success response (for warnings)
                self.request_id = uuid.UUID(error_or_warning_data["request_id"])
            elif "request_id" in error_or_warning_data:  # Occurs when Deepgram returns a failed response
                self.request_id = uuid.UUID(error_or_warning_data["request_id"])
        elif isinstance(args[0], str):
            self.error = args[0]
        else:
            self.error = str(args[0])

        # Set the error code from the underlying exception, if possible
        if http_library_error is not None:
            # Note: The following Exceptions do not have HTTP error codes:
            #   - urllib.error.URLError
            #   - websockets.exceptions.InvalidHandshake
            #   - aiohttp.ClientError
            if isinstance(http_library_error, urllib.error.HTTPError):
                self.http_error_status = http_library_error.code
            elif isinstance(http_library_error, aiohttp.ClientResponseError):
                self.http_error_status = http_library_error.status

    def __str__(self) -> str:
        if self.request_id:
            if self.warnings:
                warning_string = f"\n\n{self.warnings}"
            else:
                warning_string = ""
            if self.http_error_status:
                return f"Request `{self.request_id}` returned {self.http_error_status}: {self.error}" + warning_string
            else:
                return f"Request `{self.request_id}` returned {self.error}" + warning_string
        return super().__str__()
