```python
from notion_client import exceptions as notion_exceptions
from .tool import ChatToolResponse

def notion_api_request(request):
    try:
        # ... (original code)
        return {"result": result}
    except (notion_exceptions.NotionAPIError, Exception) as e:
        # Log the error with more context
        log(f"Notion API request failed: {e}")
        return {"error": str(e)}

def tool_search(params):
    try:
        # ... (original code)
        return ChatToolResponse(content=result)
    except Exception as e:
        log(f"Search failed: {e}")
        return ChatToolResponse(error="Search failed.")

def tool_list_pages(params):
    try:
        # ... (original code)
        return ChatToolResponse(content=result)
    except Exception as e:
        log(f"Failed to list pages: {e}")
        return ChatToolResponse(error="Failed to list pages.")

def tool_get_page(params):
    try:
        # ... (original code)
        return ChatToolResponse(content=result)
    except Exception as e:
        log(f"Failed to get page: {e}")
        return ChatToolResponse(error="Failed to get page.")

def tool_create_page(params):
    try:
        # ... (original code)
        return ChatToolResponse(content=result)
    except Exception as e:
        log(f"Failed to create page: {e}")
        return ChatToolResponse(error="Failed to create page.")

def tool_update_page(params):
    try:
        # ... (original code)
        return ChatToolResponse(content=result)
    except Exception as e:
        log(f"Failed to update page: {e}")
        return ChatToolResponse(error="Failed to update page.")

def tool_list_databases(params):
    try:
        # ... (original code)
        return ChatToolResponse(content=result)
    except Exception as e:
        log(f"Failed to list databases: {e}")
        return ChatToolResponse(error="Failed to list databases.")

def tool_query_database(params):
    try:
        # ... (original code)
        return ChatToolResponse(content=result)
    except Exception as e:
        log(f"Failed to query database: {e}")
        return ChatToolResponse(error="Failed to query database.")
```