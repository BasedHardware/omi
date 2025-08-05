from typing import List
from ._types import Options, Key, KeyResponse
from ._utils import _request
import datetime

class Keys:
    _root = "/projects"

    def __init__(self, options: Options) -> None:
        self.options = options

    async def list(self, project_id: str) -> KeyResponse:
        """Retrieves all keys associated with the provided projectId."""
        return await _request(
            f'{self._root}/{project_id}/keys', self.options
        )

    async def get(self, project_id: str, key: str) -> Key:
        """Retrieves a specific key associated with the provided projectId."""
        return await _request(
            f'{self._root}/{project_id}/keys/{key}', self.options
        )

    async def create(
        self, project_id: str, comment: str, scopes: List[str], tags: List[str], expiration_date: datetime, time_to_live_in_seconds: int
    ) -> Key:
        """Creates an API key with the provided scopes."""
        return await _request(
            f'{self._root}/{project_id}/keys', self.options,
            method='POST', payload={'comment': comment, 'scopes': scopes, 'tags': tags, 'expiration_date': expiration_date, 'time_to_live_in_seconds': time_to_live_in_seconds},
            headers={'Content-Type': 'application/json'}
        )

    async def delete(self, project_id: str, key: str) -> None:
        """Deletes an API key."""
        await _request(
            f'{self._root}/{project_id}/keys/{key}', self.options,
            method='DELETE'
        )
