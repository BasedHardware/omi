import os
import json
import base64
import requests
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, Request, status, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import logging
import asyncio

from .db import store_notion_credentials, get_notion_credentials, store_memory
from .omi_api import store_fact

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize router and templates
router = APIRouter(prefix="/api/notion", tags=["notion"])
templates = Jinja2Templates(directory="templates")

# Global variables to store credentials
NOTION_CLIENT_ID = ""
NOTION_CLIENT_SECRET = ""
NOTION_REDIRECT_URI = ""

def init_notion_credentials(client_id: str, client_secret: str, redirect_uri: str):
    """Initialize Notion credentials"""
    global NOTION_CLIENT_ID, NOTION_CLIENT_SECRET, NOTION_REDIRECT_URI
    NOTION_CLIENT_ID = client_id
    NOTION_CLIENT_SECRET = client_secret
    NOTION_REDIRECT_URI = redirect_uri
    logger.info(f"Notion credentials initialized - Client ID: {'Yes' if client_id else 'No'}")
    logger.info(f"Redirect URI: {redirect_uri}")

# Models
class NotionSearchRequest(BaseModel):
    uid: str
    query: Optional[str] = None
    filter: Optional[Dict[str, Any]] = None
    sort: Optional[Dict[str, Any]] = None

class NotionBlocksRequest(BaseModel):
    uid: str
    block_id: str

# Authentication routes
@router.get("/auth", response_class=HTMLResponse)
async def auth_notion(request: Request, uid: str):
    """Start Notion OAuth flow"""
    if not NOTION_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="NOTION_CLIENT_ID not configured"
        )
    
    if not uid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing uid parameter"
        )
    
    # URL encode both the redirect_uri and state
    encoded_redirect_uri = requests.utils.quote(NOTION_REDIRECT_URI, safe='')
    encoded_state = requests.utils.quote(uid)
    
    oauth_url = f"https://api.notion.com/v1/oauth/authorize?client_id={NOTION_CLIENT_ID}&response_type=code&owner=user&redirect_uri={encoded_redirect_uri}&state={encoded_state}"
    
    logger.info(f"Generated OAuth URL with state: {encoded_state}")
    logger.info(f"Redirect URI: {encoded_redirect_uri}")
    
    # Redirect directly to Notion OAuth
    return RedirectResponse(oauth_url)

def split_into_chunks(content_blocks):
    """Split content blocks into meaningful chunks"""
    chunks = []
    current_chunk = []
    current_chunk_size = 0
    
    for block in content_blocks:
        block_type = block.get("type", "")
        if block_type in ["paragraph", "heading_1", "heading_2", "heading_3", "bulleted_list_item", "numbered_list_item", "to_do", "toggle", "quote"]:
            text_content = block.get(block_type, {}).get("rich_text", [])
            block_text = ""
            for text in text_content:
                if "plain_text" in text:
                    block_text += text["plain_text"]
            
            # If it's a heading or the chunk is getting too large, start a new chunk
            if (block_type.startswith("heading_") and current_chunk) or current_chunk_size > 500:
                if current_chunk:
                    chunks.append("\n".join(current_chunk))
                current_chunk = []
                current_chunk_size = 0
            
            if block_text.strip():
                current_chunk.append(block_text)
                current_chunk_size += len(block_text)
    
    # Add the last chunk if not empty
    if current_chunk:
        chunks.append("\n".join(current_chunk))
    
    return chunks

async def extract_all_pages(access_token: str, uid: str):
    """Extract all pages from Notion and store them as facts"""
    try:
        # Search for all pages
        response = requests.post(
            "https://api.notion.com/v1/search",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json"
            },
            json={}  # Empty search to get all pages
        )
        response.raise_for_status()
        pages = response.json().get("results", [])
        
        logger.info(f"Found {len(pages)} pages to process")
        total_facts_stored = 0
        
        # Process pages in smaller batches
        batch_size = 5  # Process 5 pages at a time
        for i in range(0, len(pages), batch_size):
            batch = pages[i:i + batch_size]
            for page in batch:
                try:
                    # Get page content
                    page_id = page["id"]
                    
                    # Get page title
                    title = ""
                    if "properties" in page:
                        title_prop = page["properties"].get("title", {})
                        if "title" in title_prop and len(title_prop["title"]) > 0:
                            title = title_prop["title"][0].get("plain_text", "Untitled")
                        else:
                            title = "Untitled"
                    
                    logger.info(f"\n=== Processing page: {title} ({page_id}) ===")
                    
                    # Get all blocks with pagination
                    all_blocks = []
                    has_more = True
                    next_cursor = None
                    
                    while has_more:
                        # Prepare URL and params for pagination
                        url = f"https://api.notion.com/v1/blocks/{page_id}/children"
                        params = {"page_size": 100}
                        if next_cursor:
                            params["start_cursor"] = next_cursor
                        
                        blocks_response = requests.get(
                            url,
                            params=params,
                            headers={
                                "Authorization": f"Bearer {access_token}",
                                "Notion-Version": "2022-06-28"
                            }
                        )
                        blocks_response.raise_for_status()
                        blocks_data = blocks_response.json()
                        
                        # Add blocks to our collection
                        all_blocks.extend(blocks_data.get("results", []))
                        
                        # Check if there are more blocks
                        has_more = blocks_data.get("has_more", False)
                        next_cursor = blocks_data.get("next_cursor")
                        
                        if has_more:
                            logger.info(f"Fetching more blocks for page: {title} (collected {len(all_blocks)} blocks so far)")
                    
                    # Split content into chunks
                    content_chunks = split_into_chunks(all_blocks)
                    logger.info(f"\nSplit content into {len(content_chunks)} chunks")
                    
                    # Store each chunk as a separate fact
                    facts_stored = 0
                    for i, chunk in enumerate(content_chunks, 1):
                        if chunk.strip():
                            # Add title and chunk number to each fact
                            fact_text = f"Title: {title} (Part {i}/{len(content_chunks)})\n\n{chunk}"
                            
                            # Store as fact in OMI
                            await store_fact(uid, fact_text, source_type="notion", source_id=f"{page_id}_chunk_{i}")
                            facts_stored += 1
                            total_facts_stored += 1
                    
                    logger.info(f"✓ Successfully stored {facts_stored} facts from page: {title}")
                
                except Exception as e:
                    logger.error(f"Error processing page {page_id}: {str(e)}")
                    continue  # Continue with next page even if one fails
            
            # Small delay between batches to prevent overload
            await asyncio.sleep(1)
        
        logger.info(f"✓ Total facts stored: {total_facts_stored}")
        return total_facts_stored
        
    except Exception as e:
        logger.error(f"Error in extract_all_pages: {str(e)}")
        raise

@router.get("/callback")
async def notion_callback(
    request: Request,
    background_tasks: BackgroundTasks,
    code: str,
    state: str
):
    """Handle Notion OAuth callback"""
    try:
        # Exchange code for access token
        response = requests.post(
            "https://api.notion.com/v1/oauth/token",
            headers={"Authorization": f"Basic {base64.b64encode(f'{NOTION_CLIENT_ID}:{NOTION_CLIENT_SECRET}'.encode()).decode()}"},
            json={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": NOTION_REDIRECT_URI
            }
        )
        response.raise_for_status()
        token_data = response.json()
        
        # Store credentials
        access_token = token_data.get("access_token")
        workspace_id = token_data.get("workspace_id")
        workspace_name = token_data.get("workspace_name", "Notion Workspace")  # Get workspace name from response
        store_notion_credentials(state, access_token, workspace_id, workspace_name)
        
        # Start page extraction in background
        background_tasks.add_task(extract_all_pages, access_token, state)
        
        # Redirect to success page immediately
        return templates.TemplateResponse(
            "notion_success.html",
            {"request": request}
        )
        
    except Exception as e:
        logger.error(f"Error in notion_callback: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.get("/import", response_class=HTMLResponse)
async def import_page(request: Request, uid: str):
    """Render the Notion import page"""
    if not uid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing uid parameter"
        )
    
    # Check if the user has connected Notion
    creds = get_notion_credentials(uid)
    if not creds or not creds.get("notion_access_token"):
        return RedirectResponse(url=f"/api/notion/auth?uid={uid}")
    
    workspace_name = creds.get("notion_workspace_name", "Notion Workspace")
    
    return templates.TemplateResponse(
        "notion_import.html", 
        {"request": request, "uid": uid, "workspace_name": workspace_name}
    )

# Notion API routes
@router.post("/search")
async def search_notion(request: NotionSearchRequest):
    """Search the Notion workspace"""
    creds = get_notion_credentials(request.uid)
    if not creds or not creds.get("notion_access_token"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Notion credentials not found"
        )
    
    access_token = creds["notion_access_token"]
    
    payload = {}
    if request.query:
        payload["query"] = request.query
    if request.filter:
        payload["filter"] = request.filter
    if request.sort:
        payload["sort"] = request.sort
    
    try:
        response = requests.post(
            "https://api.notion.com/v1/search",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Notion-Version": "2022-06-28"
            },
            json=payload
        )
        response.raise_for_status()
        return response.json()
    
    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error searching Notion: {str(e)}"
        )

@router.post("/blocks/{block_id}")
async def get_blocks(block_id: str, request: NotionBlocksRequest):
    """Get blocks from a Notion page or block"""
    creds = get_notion_credentials(request.uid)
    if not creds or not creds.get("notion_access_token"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Notion credentials not found"
        )
    
    access_token = creds["notion_access_token"]
    
    try:
        response = requests.get(
            f"https://api.notion.com/v1/blocks/{block_id}/children",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Notion-Version": "2022-06-28"
            }
        )
        response.raise_for_status()
        return response.json()
    
    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting blocks from Notion: {str(e)}"
        )

@router.get("/page/{page_id}")
async def get_page(page_id: str, uid: str):
    """Get content of a Notion page"""
    creds = get_notion_credentials(uid)
    if not creds or not creds.get("notion_access_token"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Notion credentials not found"
        )
    
    access_token = creds["notion_access_token"]
    
    try:
        # Get page metadata
        page_response = requests.get(
            f"https://api.notion.com/v1/pages/{page_id}",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Notion-Version": "2022-06-28"
            }
        )
        page_response.raise_for_status()
        page_data = page_response.json()
        
        # Get page content (blocks)
        blocks_response = requests.get(
            f"https://api.notion.com/v1/blocks/{page_id}/children",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Notion-Version": "2022-06-28"
            }
        )
        blocks_response.raise_for_status()
        blocks_data = blocks_response.json()
        
        return {
            "page": page_data,
            "blocks": blocks_data
        }
    
    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting page from Notion: {str(e)}"
        )

@router.post("/extract-memories")
async def extract_memories(uid: str, block_type: str = Form("page"), block_id: str = Form(...)):
    """Extract memories from Notion content"""
    creds = get_notion_credentials(uid)
    if not creds or not creds.get("notion_access_token"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Notion credentials not found"
        )
    
    access_token = creds["notion_access_token"]
    
    try:
        # Get the content based on block type
        if block_type == "page":
            # Get page content (blocks)
            blocks_response = requests.get(
                f"https://api.notion.com/v1/blocks/{block_id}/children?page_size=100",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Notion-Version": "2022-06-28"
                }
            )
            blocks_response.raise_for_status()
            blocks_data = blocks_response.json()
            
            # Extract text content from blocks
            content = extract_text_from_blocks(blocks_data.get("results", []))
            
            # Extract memories from content
            memories = extract_memories_from_text(content)
            
            # Store memories in database
            memory_ids = []
            for memory in memories:
                memory_id = store_memory(uid, "notion_page", memory)
                memory_ids.append(memory_id)
            
            return {
                "success": True,
                "message": f"Successfully extracted {len(memories)} memories",
                "memories": memories,
                "memory_ids": memory_ids
            }
        
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported block type: {block_type}"
            )
    
    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error extracting memories from Notion: {str(e)}"
        )

# Helper function to extract text from blocks
def extract_text_from_blocks(blocks):
    """Extract text content from Notion blocks"""
    content = []
    
    for block in blocks:
        block_type = block.get("type")
        
        if block_type == "paragraph":
            paragraph_text = extract_rich_text(block.get("paragraph", {}).get("rich_text", []))
            if paragraph_text:
                content.append(paragraph_text)
        
        elif block_type == "heading_1":
            heading_text = extract_rich_text(block.get("heading_1", {}).get("rich_text", []))
            if heading_text:
                content.append(f"# {heading_text}")
        
        elif block_type == "heading_2":
            heading_text = extract_rich_text(block.get("heading_2", {}).get("rich_text", []))
            if heading_text:
                content.append(f"## {heading_text}")
        
        elif block_type == "heading_3":
            heading_text = extract_rich_text(block.get("heading_3", {}).get("rich_text", []))
            if heading_text:
                content.append(f"### {heading_text}")
        
        elif block_type == "bulleted_list_item":
            item_text = extract_rich_text(block.get("bulleted_list_item", {}).get("rich_text", []))
            if item_text:
                content.append(f"• {item_text}")
        
        elif block_type == "numbered_list_item":
            item_text = extract_rich_text(block.get("numbered_list_item", {}).get("rich_text", []))
            if item_text:
                content.append(f"1. {item_text}")
        
        elif block_type == "to_do":
            item_text = extract_rich_text(block.get("to_do", {}).get("rich_text", []))
            checked = block.get("to_do", {}).get("checked", False)
            if item_text:
                content.append(f"{'[x]' if checked else '[ ]'} {item_text}")
    
    return "\n".join(content)

def extract_rich_text(rich_text):
    """Extract text from rich text array"""
    return "".join([text.get("plain_text", "") for text in rich_text])

# Function to extract memories from text content
def extract_memories_from_text(text):
    """
    Extract memories from text content
    
    This is a simple implementation that treats each sentence as a potential memory
    In a real-world scenario, you might want to use NLP techniques to identify
    personal facts/preferences
    """
    # Split text into sentences
    sentences = [s.strip() for s in text.replace("\n", " ").split(".") if s.strip()]
    
    # Filter sentences to find potential memories
    memories = []
    for sentence in sentences:
        # Criteria for identifying potential memories:
        # - Not too short (at least 30 characters)
        # - Not too long (at most 200 characters)
        # - Contains personal information keywords (this is very basic)
        if 30 <= len(sentence) <= 200 and contains_personal_info(sentence):
            # Format as "User has/likes/enjoys..."
            formatted_memory = format_as_memory(sentence)
            if formatted_memory:
                memories.append(formatted_memory)
    
    return memories

def contains_personal_info(text):
    """Check if text contains personal information keywords"""
    personal_keywords = [
        "I am", "I'm", "I like", "I love", "I enjoy", "I prefer", "I don't like",
        "I hate", "my favorite", "I want", "I need", "I have", "I feel", "I believe",
        "I think", "I wish", "I hope", "I plan", "I try", "I always", "I never",
        "I usually", "I sometimes", "I often", "I rarely", "my friend", "my family",
        "my parents", "my job", "my work", "my hobby", "my pet", "my birthday"
    ]
    
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in personal_keywords)

def format_as_memory(text):
    """Format text as a memory about the user"""
    text_lower = text.lower()
    
    # Replace first-person pronouns with "User"
    if "i am" in text_lower or "i'm" in text_lower:
        return text.replace("I am", "User is").replace("I'm", "User is")
    elif "i like" in text_lower:
        return text.replace("I like", "User likes")
    elif "i love" in text_lower:
        return text.replace("I love", "User loves")
    elif "i enjoy" in text_lower:
        return text.replace("I enjoy", "User enjoys")
    elif "i prefer" in text_lower:
        return text.replace("I prefer", "User prefers")
    elif "i don't like" in text_lower or "i do not like" in text_lower:
        return text.replace("I don't like", "User doesn't like").replace("I do not like", "User does not like")
    elif "i hate" in text_lower:
        return text.replace("I hate", "User hates")
    elif "my favorite" in text_lower:
        return text.replace("My favorite", "User's favorite")
    elif "i have" in text_lower:
        return text.replace("I have", "User has")
    elif "my friend" in text_lower:
        return text.replace("My friend", "User's friend")
    else:
        # If no specific pattern is matched, prepend with "User:"
        return f"User note: {text}" 