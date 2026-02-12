"""
Notion Integration App for Omi

This app provides Notion integration through OAuth2 authentication
and chat tools for managing pages, databases, and content.
"""
import os
import sys
import secrets
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

from db import (
    store_notion_tokens,
    get_notion_tokens,
    update_notion_tokens,
    delete_notion_tokens,
    store_oauth_state,
    get_oauth_state,
    delete_oauth_state,
    store_user_setting,
    get_user_setting,
)
from models import ChatToolResponse

load_dotenv()


def log(msg: str):
    """Print and flush immediately for Railway logging."""
    print(msg)
    sys.stdout.flush()


# Notion OAuth2 Configuration
NOTION_CLIENT_ID = os.getenv("NOTION_CLIENT_ID", "")
NOTION_CLIENT_SECRET = os.getenv("NOTION_CLIENT_SECRET", "")
NOTION_REDIRECT_URI = os.getenv("NOTION_REDIRECT_URI", "http://localhost:8080/auth/notion/callback")

# Notion API endpoints
NOTION_AUTH_URL = "https://api.notion.com/v1/oauth/authorize"
NOTION_TOKEN_URL = "https://api.notion.com/v1/oauth/token"
NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_API_VERSION = "2022-06-28"

app = FastAPI(
    title="Notion Omi Integration",
    description="Notion integration for Omi - Manage your workspace with chat",
    version="1.0.0"
)


# ============================================
# Helper Functions
# ============================================

def get_valid_access_token(uid: str) -> Optional[str]:
    """
    Get a valid access token for Notion.
    Notion tokens don't expire, so we just return the stored token.
    """
    tokens = get_notion_tokens(uid)
    if not tokens:
        return None
    return tokens.get("access_token")


def notion_api_request(uid: str, method: str, endpoint: str, params: dict = None, json_data: dict = None) -> Optional[dict]:
    """Make an authenticated request to the Notion API."""
    access_token = get_valid_access_token(uid)
    if not access_token:
        return None

    url = f"{NOTION_API_BASE}{endpoint}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_API_VERSION
    }

    try:
        if method == "GET":
            response = requests.get(url, headers=headers, params=params)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=json_data or {})
        elif method == "PATCH":
            response = requests.patch(url, headers=headers, json=json_data)
        elif method == "DELETE":
            response = requests.delete(url, headers=headers)
        else:
            return None

        if response.status_code in [200, 201]:
            return response.json()
        else:
            log(f"Notion API error: {response.status_code} - {response.text}")
            return {"error": response.text, "status_code": response.status_code}

    except Exception as e:
        log(f"Notion API request error: {e}")
        return {"error": str(e)}


def extract_title(page: dict) -> str:
    """Extract the title from a Notion page object."""
    properties = page.get("properties", {})

    # Try common title property names
    for prop_name in ["title", "Title", "Name", "name"]:
        if prop_name in properties:
            prop = properties[prop_name]
            if prop.get("type") == "title":
                title_arr = prop.get("title", [])
                if title_arr:
                    return "".join([t.get("plain_text", "") for t in title_arr])

    # Fallback: try to find any title property
    for prop_name, prop in properties.items():
        if prop.get("type") == "title":
            title_arr = prop.get("title", [])
            if title_arr:
                return "".join([t.get("plain_text", "") for t in title_arr])

    return "Untitled"


def extract_text_content(blocks: List[dict]) -> str:
    """Extract plain text from Notion blocks."""
    text_parts = []

    for block in blocks:
        block_type = block.get("type", "")
        block_content = block.get(block_type, {})

        # Handle rich text blocks
        rich_text = block_content.get("rich_text", [])
        if rich_text:
            text = "".join([t.get("plain_text", "") for t in rich_text])
            if text:
                text_parts.append(text)

    return "\n".join(text_parts)


def format_page_info(page: dict, include_content: bool = False) -> str:
    """Format a page for display."""
    title = extract_title(page)
    page_id = page.get("id", "")
    url = page.get("url", "")
    created = page.get("created_time", "")[:10]
    last_edited = page.get("last_edited_time", "")[:10]

    parts = [
        f"**{title}**",
        f"  Created: {created} | Edited: {last_edited}",
        f"  ID: `{page_id[:20]}...`"
    ]

    if url:
        parts.append(f"  URL: {url}")

    return "\n".join(parts)


def format_database_info(db: dict) -> str:
    """Format a database for display."""
    title_arr = db.get("title", [])
    title = "".join([t.get("plain_text", "") for t in title_arr]) if title_arr else "Untitled Database"
    db_id = db.get("id", "")
    url = db.get("url", "")

    # Get property names
    properties = db.get("properties", {})
    prop_names = list(properties.keys())[:5]

    parts = [
        f"**{title}**",
        f"  ID: `{db_id[:20]}...`",
        f"  Properties: {', '.join(prop_names)}"
    ]

    if url:
        parts.append(f"  URL: {url}")

    return "\n".join(parts)


# ============================================
# Chat Tools Manifest
# ============================================

@app.get("/.well-known/omi-tools.json")
async def get_omi_tools_manifest():
    """
    Omi Chat Tools Manifest endpoint.
    """
    return {
        "tools": [
            {
                "name": "search_notion",
                "description": "Search for pages and databases in Notion. Use this when the user wants to find something in their workspace, search for notes, or locate a page.",
                "endpoint": "/tools/search",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query text"
                        },
                        "filter": {
                            "type": "string",
                            "enum": ["page", "database"],
                            "description": "Filter results by type (page or database)"
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of results (default: 10, max: 20)"
                        }
                    },
                    "required": []
                },
                "auth_required": True,
                "status_message": "Searching Notion..."
            },
            {
                "name": "list_pages",
                "description": "List recently edited pages in Notion. Use this when the user wants to see their recent pages, view their workspace, or check what they've been working on.",
                "endpoint": "/tools/list_pages",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of pages to return (default: 10, max: 20)"
                        }
                    },
                    "required": []
                },
                "auth_required": True,
                "status_message": "Getting your Notion pages..."
            },
            {
                "name": "get_page",
                "description": "Get details of a specific Notion page. Use this when the user wants to view a page's content, read notes, or see page details.",
                "endpoint": "/tools/get_page",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "page_id": {
                            "type": "string",
                            "description": "The page ID to get details for. Required."
                        }
                    },
                    "required": ["page_id"]
                },
                "auth_required": True,
                "status_message": "Getting page details..."
            },
            {
                "name": "create_page",
                "description": "Create a new page in Notion. Use this when the user wants to add a new note, create a page, or add content to their workspace.",
                "endpoint": "/tools/create_page",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Page title. Required."
                        },
                        "content": {
                            "type": "string",
                            "description": "Page content as plain text. Will be added as paragraph blocks."
                        },
                        "parent_page_id": {
                            "type": "string",
                            "description": "Parent page ID to create this page under. If not provided, creates in workspace root."
                        },
                        "database_id": {
                            "type": "string",
                            "description": "Database ID to create this page in (for database entries)."
                        }
                    },
                    "required": ["title"]
                },
                "auth_required": True,
                "status_message": "Creating page..."
            },
            {
                "name": "update_page",
                "description": "Update a Notion page's properties or archive it. Use this when the user wants to edit, rename, or archive a page.",
                "endpoint": "/tools/update_page",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "page_id": {
                            "type": "string",
                            "description": "The page ID to update. Required."
                        },
                        "title": {
                            "type": "string",
                            "description": "New page title."
                        },
                        "archived": {
                            "type": "boolean",
                            "description": "Set to true to archive the page."
                        }
                    },
                    "required": ["page_id"]
                },
                "auth_required": True,
                "status_message": "Updating page..."
            },
            {
                "name": "append_content",
                "description": "Append content to an existing Notion page. Use this when the user wants to add text, notes, or content to a page.",
                "endpoint": "/tools/append_content",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "page_id": {
                            "type": "string",
                            "description": "The page ID to append content to. Required."
                        },
                        "content": {
                            "type": "string",
                            "description": "Content to append as plain text. Required."
                        }
                    },
                    "required": ["page_id", "content"]
                },
                "auth_required": True,
                "status_message": "Adding content to page..."
            },
            {
                "name": "list_databases",
                "description": "List databases in Notion workspace. Use this when the user wants to see their databases, tables, or structured data.",
                "endpoint": "/tools/list_databases",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of databases to return (default: 10, max: 20)"
                        }
                    },
                    "required": []
                },
                "auth_required": True,
                "status_message": "Getting your databases..."
            },
            {
                "name": "query_database",
                "description": "Query a Notion database to get its entries. Use this when the user wants to see items in a database, filter records, or view table data.",
                "endpoint": "/tools/query_database",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "database_id": {
                            "type": "string",
                            "description": "The database ID to query. Required."
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of results (default: 10, max: 50)"
                        }
                    },
                    "required": ["database_id"]
                },
                "auth_required": True,
                "status_message": "Querying database..."
            }
        ]
    }


# ============================================
# Chat Tool Endpoints
# ============================================

@app.post("/tools/search", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_search(request: Request):
    """Search Notion workspace."""
    try:
        body = await request.json()
        log(f"=== SEARCH ===")

        uid = body.get("uid")
        query = body.get("query", "")
        filter_type = body.get("filter")
        max_results = min(body.get("max_results", 10), 20)

        if not uid:
            return ChatToolResponse(error="User ID is required")

        access_token = get_valid_access_token(uid)
        if not access_token:
            return ChatToolResponse(error="Please connect your Notion workspace first in the app settings.")

        search_params = {
            "page_size": max_results
        }

        if query:
            search_params["query"] = query

        if filter_type in ["page", "database"]:
            search_params["filter"] = {"property": "object", "value": filter_type}

        result = notion_api_request(uid, "POST", "/search", json_data=search_params)

        if not result or "error" in result:
            return ChatToolResponse(error=f"Search failed: {result.get('error', 'Unknown error')}")

        results = result.get("results", [])

        if not results:
            if query:
                return ChatToolResponse(result=f"No results found for '{query}'.")
            return ChatToolResponse(result="No pages or databases found in your workspace.")

        result_parts = [f"**Search Results ({len(results)})**", ""]

        for item in results:
            obj_type = item.get("object", "")
            if obj_type == "page":
                result_parts.append(format_page_info(item))
            elif obj_type == "database":
                result_parts.append(format_database_info(item))
            result_parts.append("")

        return ChatToolResponse(result="\n".join(result_parts))

    except Exception as e:
        log(f"Error searching: {e}")
        import traceback
        traceback.print_exc()
        return ChatToolResponse(error=f"Search failed: {str(e)}")


@app.post("/tools/list_pages", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_list_pages(request: Request):
    """List recently edited pages."""
    try:
        body = await request.json()
        log(f"=== LIST_PAGES ===")

        uid = body.get("uid")
        max_results = min(body.get("max_results", 10), 20)

        if not uid:
            return ChatToolResponse(error="User ID is required")

        access_token = get_valid_access_token(uid)
        if not access_token:
            return ChatToolResponse(error="Please connect your Notion workspace first in the app settings.")

        result = notion_api_request(uid, "POST", "/search", json_data={
            "filter": {"property": "object", "value": "page"},
            "sort": {"direction": "descending", "timestamp": "last_edited_time"},
            "page_size": max_results
        })

        if not result or "error" in result:
            return ChatToolResponse(error=f"Failed to list pages: {result.get('error', 'Unknown error')}")

        pages = result.get("results", [])

        if not pages:
            return ChatToolResponse(result="No pages found in your workspace.")

        result_parts = [f"**Recent Pages ({len(pages)})**", ""]

        for page in pages:
            result_parts.append(format_page_info(page))
            result_parts.append("")

        return ChatToolResponse(result="\n".join(result_parts))

    except Exception as e:
        log(f"Error listing pages: {e}")
        return ChatToolResponse(error=f"Failed to list pages: {str(e)}")


@app.post("/tools/get_page", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_get_page(request: Request):
    """Get page details and content."""
    try:
        body = await request.json()
        uid = body.get("uid")
        page_id = body.get("page_id")

        if not uid:
            return ChatToolResponse(error="User ID is required")

        if not page_id:
            return ChatToolResponse(error="Page ID is required. Use 'search' or 'list pages' to find page IDs.")

        access_token = get_valid_access_token(uid)
        if not access_token:
            return ChatToolResponse(error="Please connect your Notion workspace first in the app settings.")

        # Get page properties
        page = notion_api_request(uid, "GET", f"/pages/{page_id}")

        if not page or "error" in page:
            return ChatToolResponse(error=f"Page not found: {page.get('error', 'Unknown error')}")

        # Get page content (blocks)
        blocks = notion_api_request(uid, "GET", f"/blocks/{page_id}/children", params={"page_size": 50})

        title = extract_title(page)
        url = page.get("url", "")
        created = page.get("created_time", "")[:10]
        last_edited = page.get("last_edited_time", "")[:10]
        archived = page.get("archived", False)

        result_parts = [
            f"**{title}**",
            "",
            f"**Created:** {created}",
            f"**Last Edited:** {last_edited}",
            f"**Status:** {'Archived' if archived else 'Active'}",
        ]

        if url:
            result_parts.append(f"**URL:** {url}")

        result_parts.append(f"**Page ID:** `{page_id}`")

        # Add content if available
        if blocks and "results" in blocks:
            content = extract_text_content(blocks.get("results", []))
            if content:
                result_parts.append("")
                result_parts.append("**Content:**")
                # Limit content length
                if len(content) > 1000:
                    content = content[:1000] + "..."
                result_parts.append(content)

        return ChatToolResponse(result="\n".join(result_parts))

    except Exception as e:
        log(f"Error getting page: {e}")
        return ChatToolResponse(error=f"Failed to get page: {str(e)}")


@app.post("/tools/create_page", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_create_page(request: Request):
    """Create a new page in Notion."""
    try:
        body = await request.json()
        log(f"=== CREATE_PAGE ===")

        uid = body.get("uid")
        title = body.get("title")
        content = body.get("content", "")
        parent_page_id = body.get("parent_page_id")
        database_id = body.get("database_id")

        if not uid:
            return ChatToolResponse(error="User ID is required")

        if not title:
            return ChatToolResponse(error="Page title is required")

        access_token = get_valid_access_token(uid)
        if not access_token:
            return ChatToolResponse(error="Please connect your Notion workspace first in the app settings.")

        # Build page data
        page_data = {
            "properties": {
                "title": {
                    "title": [{"text": {"content": title}}]
                }
            }
        }

        # Set parent
        if database_id:
            page_data["parent"] = {"database_id": database_id}
            # For database pages, use Name property instead of title
            page_data["properties"] = {
                "Name": {
                    "title": [{"text": {"content": title}}]
                }
            }
        elif parent_page_id:
            page_data["parent"] = {"page_id": parent_page_id}
        else:
            # Get workspace ID from user's token info
            tokens = get_notion_tokens(uid)
            workspace_id = tokens.get("workspace_id") if tokens else None
            if workspace_id:
                page_data["parent"] = {"page_id": workspace_id}
            else:
                return ChatToolResponse(error="Please specify a parent page or database ID.")

        # Add content as paragraph blocks
        if content:
            paragraphs = content.split("\n")
            page_data["children"] = [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"text": {"content": p}}]
                    }
                }
                for p in paragraphs if p.strip()
            ]

        log(f"Creating page with data: {page_data}")

        result = notion_api_request(uid, "POST", "/pages", json_data=page_data)

        if not result or "error" in result:
            return ChatToolResponse(error=f"Failed to create page: {result.get('error', 'Unknown error')}")

        page_id = result.get("id", "")
        url = result.get("url", "")

        result_parts = [
            "**Page Created!**",
            "",
            f"**Title:** {title}",
            f"**ID:** `{page_id}`"
        ]

        if url:
            result_parts.append(f"**URL:** {url}")

        return ChatToolResponse(result="\n".join(result_parts))

    except Exception as e:
        log(f"Error creating page: {e}")
        import traceback
        traceback.print_exc()
        return ChatToolResponse(error=f"Failed to create page: {str(e)}")


@app.post("/tools/update_page", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_update_page(request: Request):
    """Update a page's properties."""
    try:
        body = await request.json()
        log(f"=== UPDATE_PAGE ===")

        uid = body.get("uid")
        page_id = body.get("page_id")
        title = body.get("title")
        archived = body.get("archived")

        if not uid:
            return ChatToolResponse(error="User ID is required")

        if not page_id:
            return ChatToolResponse(error="Page ID is required.")

        access_token = get_valid_access_token(uid)
        if not access_token:
            return ChatToolResponse(error="Please connect your Notion workspace first in the app settings.")

        update_data = {}
        updates = []

        if title:
            # First get the page to find the title property name
            page = notion_api_request(uid, "GET", f"/pages/{page_id}")
            if page and "properties" in page:
                # Find the title property
                for prop_name, prop in page["properties"].items():
                    if prop.get("type") == "title":
                        update_data["properties"] = {
                            prop_name: {
                                "title": [{"text": {"content": title}}]
                            }
                        }
                        updates.append(f"Title: {title}")
                        break

        if archived is not None:
            update_data["archived"] = archived
            updates.append(f"Archived: {archived}")

        if not update_data:
            return ChatToolResponse(error="No updates provided. Specify title or archived.")

        result = notion_api_request(uid, "PATCH", f"/pages/{page_id}", json_data=update_data)

        if not result or "error" in result:
            return ChatToolResponse(error=f"Failed to update page: {result.get('error', 'Unknown error')}")

        result_parts = ["**Page Updated!**", ""] + updates

        return ChatToolResponse(result="\n".join(result_parts))

    except Exception as e:
        log(f"Error updating page: {e}")
        return ChatToolResponse(error=f"Failed to update page: {str(e)}")


@app.post("/tools/append_content", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_append_content(request: Request):
    """Append content to a page."""
    try:
        body = await request.json()
        uid = body.get("uid")
        page_id = body.get("page_id")
        content = body.get("content")

        if not uid:
            return ChatToolResponse(error="User ID is required")

        if not page_id:
            return ChatToolResponse(error="Page ID is required.")

        if not content:
            return ChatToolResponse(error="Content is required.")

        access_token = get_valid_access_token(uid)
        if not access_token:
            return ChatToolResponse(error="Please connect your Notion workspace first in the app settings.")

        # Create paragraph blocks from content
        paragraphs = content.split("\n")
        children = [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": p}}]
                }
            }
            for p in paragraphs if p.strip()
        ]

        result = notion_api_request(uid, "PATCH", f"/blocks/{page_id}/children", json_data={"children": children})

        if not result or "error" in result:
            return ChatToolResponse(error=f"Failed to append content: {result.get('error', 'Unknown error')}")

        return ChatToolResponse(result=f"**Content Added!**\n\nAdded {len(children)} paragraph(s) to the page.")

    except Exception as e:
        log(f"Error appending content: {e}")
        return ChatToolResponse(error=f"Failed to append content: {str(e)}")


@app.post("/tools/list_databases", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_list_databases(request: Request):
    """List databases in workspace."""
    try:
        body = await request.json()
        uid = body.get("uid")
        max_results = min(body.get("max_results", 10), 20)

        if not uid:
            return ChatToolResponse(error="User ID is required")

        access_token = get_valid_access_token(uid)
        if not access_token:
            return ChatToolResponse(error="Please connect your Notion workspace first in the app settings.")

        result = notion_api_request(uid, "POST", "/search", json_data={
            "filter": {"property": "object", "value": "database"},
            "page_size": max_results
        })

        if not result or "error" in result:
            return ChatToolResponse(error=f"Failed to list databases: {result.get('error', 'Unknown error')}")

        databases = result.get("results", [])

        if not databases:
            return ChatToolResponse(result="No databases found in your workspace.")

        result_parts = [f"**Databases ({len(databases)})**", ""]

        for db in databases:
            result_parts.append(format_database_info(db))
            result_parts.append("")

        return ChatToolResponse(result="\n".join(result_parts))

    except Exception as e:
        log(f"Error listing databases: {e}")
        return ChatToolResponse(error=f"Failed to list databases: {str(e)}")


@app.post("/tools/query_database", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_query_database(request: Request):
    """Query a database to get its entries."""
    try:
        body = await request.json()
        uid = body.get("uid")
        database_id = body.get("database_id")
        max_results = min(body.get("max_results", 10), 50)

        if not uid:
            return ChatToolResponse(error="User ID is required")

        if not database_id:
            return ChatToolResponse(error="Database ID is required. Use 'list databases' to find database IDs.")

        access_token = get_valid_access_token(uid)
        if not access_token:
            return ChatToolResponse(error="Please connect your Notion workspace first in the app settings.")

        result = notion_api_request(uid, "POST", f"/databases/{database_id}/query", json_data={
            "page_size": max_results
        })

        if not result or "error" in result:
            return ChatToolResponse(error=f"Failed to query database: {result.get('error', 'Unknown error')}")

        entries = result.get("results", [])

        if not entries:
            return ChatToolResponse(result="No entries found in this database.")

        result_parts = [f"**Database Entries ({len(entries)})**", ""]

        for entry in entries:
            title = extract_title(entry)
            entry_id = entry.get("id", "")
            url = entry.get("url", "")

            result_parts.append(f"- **{title}**")
            result_parts.append(f"  ID: `{entry_id[:20]}...`")
            if url:
                result_parts.append(f"  URL: {url}")
            result_parts.append("")

        return ChatToolResponse(result="\n".join(result_parts))

    except Exception as e:
        log(f"Error querying database: {e}")
        return ChatToolResponse(error=f"Failed to query database: {str(e)}")


# ============================================
# OAuth & Setup Endpoints
# ============================================

@app.get("/")
async def root(uid: str = Query(None)):
    """Root endpoint - Homepage."""
    if not uid:
        return {
            "app": "Notion Omi Integration",
            "version": "1.0.0",
            "status": "active",
            "endpoints": {
                "auth": "/auth/notion?uid=<user_id>",
                "setup_check": "/setup/notion?uid=<user_id>",
                "tools_manifest": "/.well-known/omi-tools.json"
            }
        }

    tokens = get_notion_tokens(uid)

    if not tokens:
        auth_url = f"/auth/notion?uid={uid}"
        return HTMLResponse(content=f"""
        <html>
            <head>
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <title>Notion - Connect</title>
                <style>{get_css()}</style>
            </head>
            <body>
                <div class="container">
                    <div class="icon">📝</div>
                    <h1>Notion</h1>
                    <p>Manage your Notion workspace through Omi chat</p>

                    <a href="{auth_url}" class="btn btn-primary btn-block">
                        Connect Notion
                    </a>

                    <div class="card">
                        <h3>What You Can Do</h3>
                        <ul>
                            <li><strong>Search</strong> - Find pages and databases</li>
                            <li><strong>Create Pages</strong> - Add new notes and content</li>
                            <li><strong>View Content</strong> - Read your pages</li>
                            <li><strong>Query Databases</strong> - Browse your tables</li>
                        </ul>
                    </div>

                    <div class="card">
                        <h3>Example Commands</h3>
                        <div class="example">"Search for meeting notes"</div>
                        <div class="example">"Create a new page called Ideas"</div>
                        <div class="example">"Show my recent pages"</div>
                    </div>

                    <div class="footer">Powered by <strong>Omi</strong></div>
                </div>
            </body>
        </html>
        """)

    # User is connected
    workspace_name = tokens.get("workspace_name", "Your Workspace")

    return HTMLResponse(content=f"""
    <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>Notion - Connected</title>
            <style>{get_css()}</style>
        </head>
        <body>
            <div class="container">
                <div class="success-box">
                    <div class="icon" style="font-size: 48px;">✓</div>
                    <h2>Notion Connected</h2>
                    <p>Connected to: {workspace_name}</p>
                </div>

                <div class="card">
                    <h3>Try These Commands</h3>
                    <div class="example">"Show my Notion pages"</div>
                    <div class="example">"Create a new page for project ideas"</div>
                    <div class="example">"Search for budget in Notion"</div>
                </div>

                <a href="/disconnect?uid={uid}" class="btn btn-secondary btn-block">
                    Disconnect Notion
                </a>

                <div class="footer">Powered by <strong>Omi</strong></div>
            </div>
        </body>
    </html>
    """)


@app.get("/auth/notion")
async def notion_auth(uid: str = Query(...)):
    """Start Notion OAuth2 flow."""
    if not NOTION_CLIENT_ID or not NOTION_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Notion OAuth credentials not configured")

    state = f"{uid}:{secrets.token_urlsafe(32)}"
    store_oauth_state(uid, state)

    params = {
        "client_id": NOTION_CLIENT_ID,
        "redirect_uri": NOTION_REDIRECT_URI,
        "response_type": "code",
        "owner": "user",
        "state": state
    }

    auth_url = f"{NOTION_AUTH_URL}?{urlencode(params)}"
    return RedirectResponse(url=auth_url)


@app.get("/auth/notion/callback")
async def notion_callback(
    code: str = Query(None),
    state: str = Query(None),
    error: str = Query(None)
):
    """Handle Notion OAuth2 callback."""
    if error:
        return HTMLResponse(content=f"""
        <html>
            <head><style>{get_css()}</style></head>
            <body>
                <div class="container">
                    <div class="error-box">
                        <h2>Authorization Failed</h2>
                        <p>{error}</p>
                    </div>
                </div>
            </body>
        </html>
        """, status_code=400)

    if not code or not state:
        return HTMLResponse(content=f"""
        <html>
            <head><style>{get_css()}</style></head>
            <body>
                <div class="container">
                    <div class="error-box">
                        <h2>Authorization Failed</h2>
                        <p>Missing authorization code or state.</p>
                    </div>
                </div>
            </body>
        </html>
        """, status_code=400)

    # Extract uid from state
    try:
        uid = state.split(":")[0]
    except:
        return HTMLResponse(content="Invalid state", status_code=400)

    # Verify state
    stored_state = get_oauth_state(uid)
    if stored_state != state:
        return HTMLResponse(content="State mismatch", status_code=400)

    delete_oauth_state(uid)

    # Exchange code for tokens
    try:
        import base64
        credentials = base64.b64encode(f"{NOTION_CLIENT_ID}:{NOTION_CLIENT_SECRET}".encode()).decode()

        response = requests.post(
            NOTION_TOKEN_URL,
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/json"
            },
            json={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": NOTION_REDIRECT_URI
            }
        )

        if response.status_code != 200:
            log(f"Token exchange failed: {response.text}")
            return HTMLResponse(content=f"Token exchange failed: {response.text}", status_code=400)

        token_data = response.json()
        access_token = token_data.get("access_token")
        workspace_id = token_data.get("workspace_id")
        workspace_name = token_data.get("workspace_name", "Notion Workspace")
        bot_id = token_data.get("bot_id")

        if not access_token:
            return HTMLResponse(content="No access token received", status_code=400)

        store_notion_tokens(uid, access_token, workspace_id, workspace_name, bot_id)

        return HTMLResponse(content=f"""
        <html>
            <head>
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <title>Connected!</title>
                <style>{get_css()}</style>
            </head>
            <body>
                <div class="container">
                    <div class="success-box">
                        <div class="icon" style="font-size: 72px;">🎉</div>
                        <h2>Successfully Connected!</h2>
                        <p>Your Notion workspace is now linked to Omi</p>
                    </div>

                    <a href="/?uid={uid}" class="btn btn-primary btn-block">
                        Continue to Settings
                    </a>

                    <div class="card">
                        <h3>Ready to Go!</h3>
                        <p>You can now manage your Notion workspace by chatting with Omi.</p>
                        <p>Try: <strong>"Show my Notion pages"</strong></p>
                    </div>

                    <div class="footer">Powered by <strong>Omi</strong></div>
                </div>
            </body>
        </html>
        """)

    except Exception as e:
        log(f"OAuth error: {e}")
        import traceback
        traceback.print_exc()
        return HTMLResponse(content=f"Authentication error: {str(e)}", status_code=500)


@app.get("/setup/notion")
async def check_setup(uid: str = Query(...)):
    """Check if user has completed Notion setup."""
    tokens = get_notion_tokens(uid)
    return {"is_setup_completed": tokens is not None}


@app.get("/disconnect")
async def disconnect(uid: str = Query(...)):
    """Disconnect Notion."""
    delete_notion_tokens(uid)
    return RedirectResponse(url=f"/?uid={uid}")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "notion-omi"}


# ============================================
# CSS Styles
# ============================================

def get_css() -> str:
    """Returns Notion-inspired dark theme CSS."""
    return """
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #191919;
            color: #e0e0e0;
            min-height: 100vh;
            padding: 20px;
            line-height: 1.6;
        }
        .container { max-width: 600px; margin: 0 auto; }
        .icon { font-size: 64px; text-align: center; margin-bottom: 20px; }
        h1 { color: #fff; font-size: 28px; text-align: center; margin-bottom: 8px; }
        h2 { color: #fff; font-size: 22px; margin-bottom: 12px; }
        h3 { color: #fff; font-size: 18px; margin-bottom: 12px; }
        p { color: #a0a0a0; text-align: center; margin-bottom: 24px; }
        .card {
            background: #252525;
            border-radius: 8px;
            padding: 24px;
            margin-bottom: 16px;
            border: 1px solid #333;
        }
        .btn {
            display: inline-block;
            padding: 14px 24px;
            border-radius: 4px;
            text-decoration: none;
            font-weight: 500;
            font-size: 16px;
            border: none;
            cursor: pointer;
            text-align: center;
            transition: all 0.2s;
        }
        .btn-primary {
            background: #fff;
            color: #191919;
        }
        .btn-primary:hover { background: #e0e0e0; }
        .btn-secondary {
            background: transparent;
            color: #a0a0a0;
            border: 1px solid #333;
        }
        .btn-secondary:hover { background: #333; }
        .btn-block { display: block; width: 100%; margin: 12px 0; }
        .success-box {
            background: rgba(52, 168, 83, 0.15);
            border: 1px solid #34a853;
            border-radius: 8px;
            padding: 32px;
            text-align: center;
            margin-bottom: 24px;
        }
        .success-box h2 { color: #34a853; }
        .error-box {
            background: rgba(234, 67, 53, 0.15);
            border: 1px solid #ea4335;
            border-radius: 8px;
            padding: 32px;
            text-align: center;
        }
        .error-box h2 { color: #ea4335; }
        ul { list-style: none; padding: 0; }
        li { padding: 10px 0; border-bottom: 1px solid #333; }
        li:last-child { border-bottom: none; }
        .example {
            background: #191919;
            padding: 12px 16px;
            border-radius: 4px;
            margin: 8px 0;
            font-style: italic;
            color: #a0a0a0;
            border: 1px solid #333;
        }
        .footer {
            text-align: center;
            color: #606060;
            margin-top: 40px;
            padding: 20px;
            font-size: 14px;
        }
        .footer strong { color: #fff; }
        @media (max-width: 480px) {
            body { padding: 12px; }
            .card { padding: 18px; }
            h1 { font-size: 24px; }
        }
    """


# ============================================
# Main Entry Point
# ============================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    host = os.getenv("HOST", "0.0.0.0")

    print("Notion Omi Integration")
    print("=" * 50)
    print(f"Starting on {host}:{port}")
    print("=" * 50)

    uvicorn.run("main:app", host=host, port=port, reload=True)
