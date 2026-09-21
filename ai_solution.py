To fix the issue where exception text was leaking into the chat tool responses, we replaced the `{{exc}}` with a generic error message in each of the three functions. The server-side logging was preserved for debugging purposes.

```python
# File: plugins/omi-semantic-scholar-app/search_semantic_scholar.py

from semantic_scholar import SemanticScholar
from typing import List, Optional, Dict
import json
import logging

logger = logging.getLogger(__name__)

def search_semantic_scholar_papers(query: str, max_results: int = 10) -> Dict:
    try:
        results = SemanticScholar().search_papers(query=query, max_results=max_results)
        return {"results": results}
    except Exception as e:
        logger.error(f"Error in search_semantic_scholar_papers: {e}")
        return {"error": "An error occurred while processing your request. Please try again."}

# File: plugins/omi-semantic-scholar-app/get_semantic_scholar_paper.py

from semantic_scholar import SemanticScholar
from typing import Dict, Optional

def get_semantic_scholar_paper(doi: str) -> Dict:
    try:
        result = SemanticScholar().get_paper(doi=doi)
        return {"result": result}
    except Exception as e:
        logger.error(f"Error in get_semantic_scholar_paper: {e}")
        return {"error": "An error occurred while processing your request. Please try again."}

# File: plugins/omi-semantic-scholar-app/get_semantic_scholar_author_papers.py

from semantic_scholar import SemanticScholar
from typing import Dict, Optional

def get_semantic_scholar_author_papers(author: str, max_results: int = 10) -> Dict:
    try:
        results = SemanticScholar().get_author_papers(author=author, max_results=max_results)
        return {"results": results}
    except Exception as e:
        logger.error(f"Error in get_semantic_scholar_author_papers: {e}")
        return {"error": "An error occurred while processing your request. Please try again."}
```