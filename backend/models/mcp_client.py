"""Pure contracts shared by external MCP credential storage and transport."""

from dataclasses import dataclass
from typing import Any, Literal


class McpCredentialError(RuntimeError):
    """Safe-to-display credential lifecycle failure; never includes provider data."""


@dataclass(frozen=True)
class RefreshClaim:
    state: Literal['current', 'busy', 'claimed']
    tokens: dict[str, Any]
