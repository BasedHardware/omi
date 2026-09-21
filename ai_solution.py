To fix the issue, we'll update the three endpoints to handle exceptions more gracefully, providing user-friendly messages and preserving status codes. Here's the updated code:

```python
# plugins/omi-wikipedia-app/search_articles.py

from typing import Dict, Any
from httpx import HTTPError
from omniwizard.shortcuts import get_wikipedia_search

async def search_articles(query: str, limit: int = 5) -> Dict[str, Any]:
    try:
        results = await get_wikipedia_search(query, limit=limit)
        return {
            "status": "ok",
            "results": results
        }
    except HTTPError as exc:
        return {
            "status": str(exc.response.status_code),
            "error": "An error occurred while processing your request."
        }

```

```python
# plugins/omi-wikipedia-app/get_article_summary.py

from typing import Dict, Any
from httpx import HTTPError
from omniwizard.shortcuts import get_wikipedia_summary

async def get_article_summary(title: str) -> Dict[str, Any]:
    try:
        summary = await get_wikipedia_summary(title)
        return {
            "status": "ok",
            "summary": summary
        }
    except HTTPError as exc:
        return {
            "status": str(exc.response.status_code),
            "error": "An error occurred while processing your request."
        }

```

```python
# plugins/omi-wikipedia-app/get_random_article.py

from typing import Dict, Any
from httpx import HTTPError
from omniwizard.shortcuts import get_random_wikipedia_article

async def get_random_article() -> Dict[str, Any]:
    try:
        article = await get_random_wikipedia_article()
        return {
            "status": "ok",
            "article": article
        }
    except HTTPError as exc:
        return {
            "status": str(exc.response.status_code),
            "error": "An error occurred while processing your request."
        }
```