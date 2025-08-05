from typing import cast
from ._types import (Options, UsageField, UsageFieldOptions,
                     UsageOptions, UsageRequest, UsageRequestList,
                     UsageRequestListOptions, UsageResponse)
from ._utils import _request, _make_query_string


class Usage:
    _root = "/projects"

    def __init__(self, options: Options) -> None:
        self.options = options

    async def list_requests(
        self, project_id: str, options: UsageRequestListOptions = None
    ) -> UsageRequestList:
        """Retrieves a range of requests sent to a given project."""
        if options is None:
            options = cast(UsageRequestListOptions, {})
        return await _request(
            f'{self._root}/{project_id}/requests{_make_query_string(options)}',
            self.options
        )

    async def get_request(
        self, project_id: str, request_id: str
    ) -> UsageRequest:
        """Retrieves a single request sent to a given project."""
        return await _request(
            f'{self._root}/{project_id}/requests/{request_id}',
            self.options
        )

    async def get_usage(
        self, project_id: str, options: UsageOptions = None
    ) -> UsageResponse:
        """Summarizes the usage for a given project."""
        if options is None:
            options = cast(UsageOptions, {})
        return await _request(
            f'{self._root}/{project_id}/usage{_make_query_string(options)}',
            self.options
        )

    async def get_fields(
        self, project_id: str, options: UsageFieldOptions = None
    ) -> UsageField:
        """Summarizes the options used in transcription for a given project."""
        if options is None:
            options = cast(UsageFieldOptions, {})
        return await _request(
            f'{self._root}/{project_id}/fields{_make_query_string(options)}',
            self.options
        )
