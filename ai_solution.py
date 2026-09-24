To solve the problem, we added a function to sanitize error details and updated the imports and updates endpoints to use this function. Here's the code:

```python
def sanitize_error_details(e):
    """Sanitize error details for user-facing responses."""
    error_type = type(e).__name__
    error_msg = f"{error_type}: {str(e)}"
    return f"An error occurred while processing your request: {error_type}. Please try again or contact support if the issue persists."
```

In `backend/routers/imports.py` and `backend/routers/updates.py`, the imports and updates endpoints were updated to use `format_imports_updates_error(e)`.

```python
# Example from imports.py:
from .utils import format_imports_updates_error

...

    if not data or not data.get("file"):
        return {"status": "error", "error": format_imports_updates_error(e), ...}
```

The unit tests were added in `backend/tests/unit/test_imports_updates_error_sanitization.py` to ensure the error messages are formatted correctly.

```python
def test_sanitize_error_details():
    """Test that error details are sanitized correctly."""
    test_error = ValueError("Test error message.")
    expected = f"ValueError: {test_error}"
    assert sanitize_error_details(test_error) == f"An error occurred while processing your request: {type(test_error).__name__}. Please try again or contact support if the issue persists."
    assert isinstance(format_imports_updates_error(test_error), str)
```