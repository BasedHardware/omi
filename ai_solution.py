```python
# backend/routers/action_items.py

from typing import List, Optional, Dict, Any
from ..models.models import TaskRelationshipConflictError

logger = logging.getLogger(__name__)


def _sanitize_task_relationship_error(exc: Exception, fallback: str) -> str:
    logger.warning(f"Task relationship error: {exc.__class__.__name__}")
    return fallback


# ... rest of the file ...


# In create_action_item, update_action_item, and create_action_items_batch:

try:
    # ... existing code ...
except TaskRelationshipConflictError as exc:
    return JSONResponse(
        status_code=409,
        content={"message": _sanitize_task_relationship_error(exc, "Task relationship conflict")},
    )
except Exception as exc:
    logger.error(f"Unexpected error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"message": "Internal server error"},
    )



# backend/tests/unit/test_action_items_error_sanitization.py

from unittest.mock import patch, mock
from fastapi import HTTPException
from ..action_items import _sanitize_task_relationship_error

def test_sanitize_task_relationship_error():
    with patch.object(logger, "warning") as mock_logger:
        error = TaskRelationshipConflictError("some error message")
        result = _sanitize_task_relationship_error(error, "Task relationship conflict")
        assert result == "Task relationship conflict"
        mock_logger.assert_called_once_with("Task relationship error: TaskRelationshipConflictError")

def test_unexpected_error_handling():
    with patch.object(logger, "error") as mock_logger:
        error = ValueError("some value error")
        result = _sanitize_task_relationship_error(error, "Task relationship conflict")
        assert result == "Task relationship conflict"
        mock_logger.assert_called_once_with("Unexpected error: ValueError")
```