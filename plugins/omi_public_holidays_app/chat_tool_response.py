from dataclasses import dataclass
from typing import Any, Optional

@dataclass
class ChatToolResponse:
    """
    Simple response wrapper for chat tool handlers.
    """
    result: Optional[Any] = None
    error: Optional[str] = None
