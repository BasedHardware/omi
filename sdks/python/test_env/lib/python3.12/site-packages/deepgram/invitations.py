from ._types import Options, Invitation, InvitationResponse
from ._utils import _request


class Invitations:
    _root = "/projects"

    def __init__(self, options: Options) -> None:
        self.options = options

    async def list_invitations(self, project_id: str) -> Invitation:
        """Returns all active invitations on a given project."""
        
        return await _request(f'{self._root}/{project_id}/invites', self.options)


    async def send_invitation(self, project_id: str, option: Invitation) -> InvitationResponse:
        """Sends an invitation to a given email address to join a given project"""

        return await _request(f'{self._root}/{project_id}/invites', 
                                self.options,
                                method='POST',
                                payload=option,
                                headers={'Content-Type': 'application/json'})


    async def remove_invitation(self, project_id: str, email: str) -> None:
        """Removes the invitation of the specified email from the 
        specified project."""

        await _request(
            f'{self._root}/{project_id}/invites/{email}', 
            self.options,
            method='DELETE'
        )

    async def leave_project(self, project_id: str) -> None:
        """Removes the authenticated account from the specified project."""

        await _request(
            f'{self._root}/{project_id}/leave', 
            self.options,
            method='DELETE'
        )


    
