from ._types import Options, BalanceResponse, Balance
from ._utils import _request


class Billing:
    _root = "/projects"

    def __init__(self, options: Options) -> None:
        self.options = options

    async def list_balance(self, project_id: str) -> BalanceResponse:
        """Returns a list of outstanding balances for the 
        specified project."""
        
        return await _request(f'{self._root}/{project_id}/balances', self.options)


    async def get_balance(self, project_id: str, balance_id: str) -> Balance:
        """Returns a specific project based on the provided projectId."""

        return await _request(f'{self._root}/{project_id}/balances/{balance_id}', self.options)