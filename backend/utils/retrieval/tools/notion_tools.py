"""
Tools for accessing Notion pages and databases.
"""

import os
import contextvars
from datetime import datetime, timezone
from typing import Optional

from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

import database.users as users_db
import requests
from utils.retrieval.tools.integration_base import (
    resolve_config_uid,
    get_integration_checked,
    get_access_token_checked,
    cap_limit,
)

# Import the context variable from agentic module
try:
    from utils.retrieval.agentic import agent_config_context
except ImportError:
    # Fallback if import fails
    agent_config_context = contextvars.ContextVar('agent_config', default=None)


def search_notion_pages(
    access_token: str,
    query: Optional[str] = None,
    filter_type: Optional[str] = None,
    page_size: int = 10,
) -> dict:
    """
    Search Notion pages and databases using the Notion Search API.

    Args:
        access_token: Notion access token
        query: Optional search query string
        filter_type: Optional filter by type ('page' or 'database')
        page_size: Maximum number of results to return (default: 10, max: 100)

    Returns:
        Dict with search results containing pages and databases
    """
    url = 'https://api.notion.com/v1/search'

    headers = {
        'Authorization': f'Bearer {access_token}',
        'Notion-Version': '2022-06-28',
        'Content-Type': 'application/json',
    }

    body = {
        'page_size': min(page_size, 100),  # Notion API max is 100
    }

    if query:
        body['query'] = query

    if filter_type:
        body['filter'] = {'property': 'object', 'value': filter_type}

    try:
        response = requests.post(
            url,
            headers=headers,
            json=body,
            timeout=10.0,
        )

        if response.status_code == 200:
            data = response.json()
            return data
        elif response.status_code == 401:
            print(f"❌ Notion Search API 401 - token expired or invalid")
            raise Exception("Authentication failed - token may be expired or invalid")
        else:
            error_body = response.text[:200] if response.text else "No error body"
            print(f"❌ Notion Search API error {response.status_code}: {error_body}")
            raise Exception(f"Notion Search API error: {response.status_code} - {error_body}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Network error fetching Notion pages: {e}")
        raise
    except Exception as e:
        print(f"❌ Error fetching Notion pages: {e}")
        raise


def get_notion_page_content(
    access_token: str,
    page_id: str,
) -> dict:
    """
    Retrieve content from a specific Notion page.

    Args:
        access_token: Notion access token
        page_id: Notion page ID

    Returns:
        Dict with page content
    """
    url = f'https://api.notion.com/v1/pages/{page_id}'

    headers = {
        'Authorization': f'Bearer {access_token}',
        'Notion-Version': '2022-06-28',
    }

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=10.0,
        )

        if response.status_code == 200:
            data = response.json()
            return data
        elif response.status_code == 401:
            print(f"❌ Notion Page API 401 - token expired or invalid")
            raise Exception("Authentication failed - token may be expired or invalid")
        else:
            error_body = response.text[:200] if response.text else "No error body"
            print(f"❌ Notion Page API error {response.status_code}: {error_body}")
            raise Exception(f"Notion Page API error: {response.status_code} - {error_body}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Network error fetching Notion page: {e}")
        raise
    except Exception as e:
        print(f"❌ Error fetching Notion page: {e}")
        raise


def get_notion_page_blocks(
    access_token: str,
    page_id: str,
) -> list:
    """
    Retrieve blocks (content) from a Notion page, handling pagination.

    Args:
        access_token: Notion access token
        page_id: Notion page ID

    Returns:
        List of all blocks (including paginated results)
    """
    url = f'https://api.notion.com/v1/blocks/{page_id}/children'

    headers = {
        'Authorization': f'Bearer {access_token}',
        'Notion-Version': '2022-06-28',
    }

    all_blocks = []
    start_cursor = None

    try:
        while True:
            params = {}
            if start_cursor:
                params['start_cursor'] = start_cursor

            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=10.0,
            )

            if response.status_code == 200:
                data = response.json()
                blocks = data.get('results', [])
                all_blocks.extend(blocks)

                # Check if there are more pages
                has_more = data.get('has_more', False)
                if has_more:
                    start_cursor = data.get('next_cursor')
                    if not start_cursor:
                        break
                else:
                    break
            elif response.status_code == 401:
                print(f"❌ Notion Blocks API 401 - token expired or invalid")
                raise Exception("Authentication failed - token may be expired or invalid")
            else:
                error_body = response.text[:200] if response.text else "No error body"
                print(f"❌ Notion Blocks API error {response.status_code}: {error_body}")
                raise Exception(f"Notion Blocks API error: {response.status_code} - {error_body}")

        return all_blocks
    except requests.exceptions.RequestException as e:
        print(f"❌ Network error fetching Notion blocks: {e}")
        raise
    except Exception as e:
        print(f"❌ Error fetching Notion blocks: {e}")
        raise


def extract_text_from_block(block: dict, access_token: str = None, indent: int = 0) -> str:
    """
    Extract text content from a Notion block, recursively handling child blocks.

    Args:
        block: Notion block object
        access_token: Optional access token for fetching child blocks
        indent: Indentation level for nested blocks

    Returns:
        Extracted text content
    """
    block_type = block.get('type', '')
    content = []
    indent_str = '  ' * indent

    if block_type == 'paragraph':
        rich_text = block.get('paragraph', {}).get('rich_text', [])
        for text_obj in rich_text:
            content.append(text_obj.get('plain_text', ''))
    elif block_type == 'heading_1':
        rich_text = block.get('heading_1', {}).get('rich_text', [])
        for text_obj in rich_text:
            content.append(text_obj.get('plain_text', ''))
    elif block_type == 'heading_2':
        rich_text = block.get('heading_2', {}).get('rich_text', [])
        for text_obj in rich_text:
            content.append(text_obj.get('plain_text', ''))
    elif block_type == 'heading_3':
        rich_text = block.get('heading_3', {}).get('rich_text', [])
        for text_obj in rich_text:
            content.append(text_obj.get('plain_text', ''))
    elif block_type == 'bulleted_list_item':
        rich_text = block.get('bulleted_list_item', {}).get('rich_text', [])
        for text_obj in rich_text:
            content.append(text_obj.get('plain_text', ''))
    elif block_type == 'numbered_list_item':
        rich_text = block.get('numbered_list_item', {}).get('rich_text', [])
        for text_obj in rich_text:
            content.append(text_obj.get('plain_text', ''))
    elif block_type == 'to_do':
        rich_text = block.get('to_do', {}).get('rich_text', [])
        checked = block.get('to_do', {}).get('checked', False)
        checkbox = '[x]' if checked else '[ ]'
        for text_obj in rich_text:
            content.append(f"{checkbox} {text_obj.get('plain_text', '')}")
    elif block_type == 'quote':
        rich_text = block.get('quote', {}).get('rich_text', [])
        for text_obj in rich_text:
            content.append(f"> {text_obj.get('plain_text', '')}")
    elif block_type == 'code':
        rich_text = block.get('code', {}).get('rich_text', [])
        for text_obj in rich_text:
            content.append(text_obj.get('plain_text', ''))
    else:
        # For other block types, try to extract any rich_text
        if block_type in block:
            rich_text = block.get(block_type, {}).get('rich_text', [])
            for text_obj in rich_text:
                content.append(text_obj.get('plain_text', ''))

    block_text = '\n'.join(content)

    # Handle child blocks if they exist and we have an access token
    has_children = block.get('has_children', False)
    block_id = block.get('id', '')

    if has_children and access_token and block_id:
        try:
            child_blocks = get_notion_page_blocks(access_token, block_id)
            child_texts = []
            for child_block in child_blocks:
                child_text = extract_text_from_block(child_block, access_token, indent + 1)
                if child_text.strip():
                    child_texts.append(indent_str + '  ' + child_text)
            if child_texts:
                block_text += '\n' + '\n'.join(child_texts)
        except Exception as e:
            print(f"⚠️ Could not fetch child blocks for {block_id}: {e}")
            # Continue without child blocks

    return block_text


@tool
def search_notion_pages_tool(
    query: Optional[str] = None,
    page_size: int = 10,
    config: RunnableConfig = None,
) -> str:
    """
    Search and retrieve content from the user's Notion pages and databases.

    Use this tool when:
    - User asks about their Notion pages, notes, or documents
    - User asks "what's in my Notion?" or "show me my Notion pages"
    - User wants to find specific information in their Notion workspace
    - User asks about content, notes, or documents stored in Notion
    - User mentions searching their Notion workspace
    - User asks about a specific person, topic, or keyword in Notion (e.g., "What does it say about Roy Lee?")
    - **ALWAYS use this tool when the user asks about Notion pages or content**
    - **IMPORTANT: If the user asks about a different topic than what was previously searched, you MUST call this tool again with the new query**
    - **IMPORTANT: When user asks about something "on that page" or "in my learnings page", include the page name in the query (e.g., "Roy Lee learnings" or "learnings Roy Lee") to find the correct page**

    Args:
        query: Search query to filter pages (e.g., "meeting notes", "project plan", "Replit", "Roy Lee", "Roy Lee learnings"). REQUIRED when searching for specific information. Include page context (e.g., "learnings") when user refers to a specific page.
        page_size: Maximum number of pages to return (default: 10, max: 100)

    Returns:
        Formatted list of Notion pages with their titles and full content (when query is provided) or content previews.
    """
    uid, uid_err = resolve_config_uid(config)
    if uid_err:
        return uid_err

    try:
        page_size = cap_limit(page_size, 100)
        integration, int_err = get_integration_checked(
            uid,
            'notion',
            'Notion',
            'Notion is not connected. Please connect your Notion account from settings to view your pages.',
            'Error checking Notion connection',
        )
        if int_err:
            return int_err

        access_token, token_err = get_access_token_checked(
            integration,
            'Notion access token not found. Please reconnect your Notion account from settings.',
        )
        if token_err:
            return token_err

        # Search Notion pages
        # If query contains common page references, try to find the specific page first
        page_context = None
        search_query = query

        if query:
            query_lower = query.lower()
            # Check if user is referring to a specific page
            if 'learnings' in query_lower or 'learning' in query_lower:
                page_context = 'learnings'
            elif 'notes' in query_lower:
                page_context = 'notes'
            elif 'meetings' in query_lower:
                page_context = 'meetings'

        try:
            search_results = search_notion_pages(
                access_token=access_token,
                query=search_query,
                page_size=page_size,
            )
        except Exception as e:
            error_msg = str(e)
            print(f"❌ Error fetching Notion pages: {error_msg}")
            return f"Error fetching Notion pages: {error_msg}"

        results = search_results.get('results', [])
        results_count = len(results) if results else 0

        if not results:
            query_info = f" matching '{query}'" if query else ""
            return f"No Notion pages found{query_info}."

        # Format results
        result_text = f"Notion Pages ({results_count} found):\n\n"

        for i, page in enumerate(results, 1):
            # Extract page title
            properties = page.get('properties', {})
            title = "Untitled"

            # Try to find title in properties
            for prop_name, prop_data in properties.items():
                prop_type = prop_data.get('type', '')
                if prop_type == 'title':
                    title_rich_text = prop_data.get('title', [])
                    if title_rich_text:
                        title = title_rich_text[0].get('plain_text', 'Untitled')
                    break

            # If no title property found, try to get from page object
            if title == "Untitled" and 'title' in page:
                if isinstance(page['title'], list) and page['title']:
                    title = page['title'][0].get('plain_text', 'Untitled')

            result_text += f"{i}. {title}\n"

            # Get page URL if available
            page_url = page.get('url', '')
            if page_url:
                result_text += f"   URL: {page_url}\n"

            # Fetch and extract full page content
            page_id = page.get('id', '')
            if page_id:
                try:
                    blocks = get_notion_page_blocks(access_token, page_id)
                    if blocks:
                        # Extract text from ALL blocks (including nested children)
                        all_text_lines = []
                        for block in blocks:
                            block_text = extract_text_from_block(block, access_token)
                            if block_text.strip():
                                all_text_lines.append(block_text.strip())

                        if all_text_lines:
                            full_content = '\n'.join(all_text_lines)

                            # If query is provided, check if it matches and include full content
                            # Otherwise, show a preview
                            if query:
                                # Include full content when searching so LLM can find the answer
                                result_text += f"   Content:\n{full_content}\n"
                            else:
                                # Show preview for general browsing
                                preview = full_content[:500] + "..." if len(full_content) > 500 else full_content
                                result_text += f"   Content: {preview}\n"
                except Exception as e:
                    print(f"⚠️ Could not fetch content for page {page_id}: {e}")
                    # Continue without content

            result_text += "\n"

        return result_text.strip()
    except Exception as e:
        print(f"❌ Unexpected error in search_notion_pages_tool: {e}")
        import traceback

        traceback.print_exc()
        return f"Unexpected error fetching Notion pages: {str(e)}"
