from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ChatToolResponse:
    """
    Simple container for tool responses used by the public‑holidays plugin.
    """
    result: Optional[Any] = None
    error: Optional[str] = None
