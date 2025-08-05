from ._types import Options, Scope, UpdateResponse
from ._utils import _request


class Scopes:
    _root = "/projects"

    def __init__(self, options: Options) -> None:
        self.options = options


    async def get_scope(self, project_id: str, member_id: str) -> Scope:
        """Returns the specified project scopes assigned 
        to the specified member."""
        
        return await _request(f'{self._root}/{project_id}/members/{member_id}/scopes', self.options)

    
    async def update_scope(self, project_id: str, member_id: str, scope: str) -> UpdateResponse:
        """Updates the specified project scopes assigned to the 
        specified member."""
        
        payload = {}
        
        if scope:
            payload['scope'] = scope

        return await _request(
            f'{self._root}/{project_id}/members/{member_id}/scopes', self.options,
            method='PUT', payload=payload,
            headers={'Content-Type': 'application/json'}
        )

    
