```python
from chattools import ChatToolResponse
from plugins.omi_pubmed_app import pubmed
import logging

# For /tools/search_pubmed endpoint
def search_pubmed(text):
    try:
        return pubmed.search_pubmed(text)
    except Exception as e:
        logging.error(f"Error in search_pubmed: {e}")
        return ChatToolResponse(
            message=f"Sorry, there was an issue reaching the network. Please check your connection and try again.",
            error=True,
        )

# For /tools/get_pubmed_article endpoint
def get_pubmed_article(text):
    try:
        return pubmed.get_pubmed_article(text)
    except Exception as e:
        logging.error(f"Error in get_pubmed_article: {e}")
        return ChatToolResponse(
            message=f"Sorry, there was an issue reaching the network. Please check your connection and try again.",
            error=True,
        )

# For /tools/get_related_pubmed endpoint
def get_related_pubmed(text):
    try:
        return pubmed.get_related_pubmed(text)
    except Exception as e:
        logging.error(f"Error in get_related_pubmed: {e}")
        return ChatToolResponse(
            message=f"Sorry, there was an issue reaching the network. Please check your connection and try again.",
            error=True,
        )
```