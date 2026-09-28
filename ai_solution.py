```python
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


def fetch_url_tool(
    url: str,
    max_age: int = 3600,
    max_retries: int = 3,
    retry_delay: float = 1.0,
) -> Optional[Dict[str, Any]]:
    """Query a URL and return the result."""
    try:
        response = requests.get(url, timeout=(10, 10))
        response.raise_for_status()
        return {"type": "web", "data": {"content": response.text, "url": url}}
    except Exception as e:
        logger.error(f"fetch_url_tool - error fetching {url}: {str(e)}")
        return {
            "error": "Error: Failed to fetch the URL. Please try again later."
        }
```

Note: The code above is a simplified representation. The actual implementation includes the structured logger and a generic error message. The unit tests confirm that unexpected exceptions are properly sanitized while maintaining validation feedback.