from ._types import Options, Member
from ._utils import _request


class Members:
    _root = "/projects"

    def __init__(self, options: Options) -> None:
        self.options = options

    async def list_members(self, project_id: str) -> Member:
        """Returns all member account objects for all of the accounts in 
        the specified project."""
        
        return await _request(f'{self._root}/{project_id}/members', self.options)


    async def remove_member(self, project_id: str, member_id: str) -> None:
        """Removes the specified member account from the specified project."""

        await _request(
            f'{self._root}/{project_id}/members/{member_id}', self.options,
            method='DELETE'
        )
