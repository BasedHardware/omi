import json
import os
import secrets
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException, Request, Response, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer
from fastapi.templating import Jinja2Templates
from models import Memory, EndpointResponse

# Fix relative imports
import sys
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)
from client import get_chatgpt
from storage import store_memory, get_memory, get_memories_by_uid, delete_memory, MEMORY_STORE

# Helper function for logging with timestamps
def log_with_timestamp(message: str):
    """Log a message with the current timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # Millisecond precision
    print(f"[{timestamp}] {message}")

router = APIRouter()
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates"))

# In-memory storage for OAuth state validation and authorization codes
# In production, use a more secure storage like Redis
AUTH_STATES = {}
AUTH_CODES = {}
ACCESS_TOKENS = {}

# OAuth2 scheme for token validation
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="chatgpt/oauth/token")

# --- Webhook endpoint for receiving memory data from OMI ---

@router.post('/chatgpt/webhook/memory', tags=['webhook'])
async def webhook_memory(request: Request):
    """
    Webhook endpoint to receive memory data from OMI.
    This endpoint logs the received data and stores it for later retrieval.
    """
    try:
        # Get the request body (raw JSON)
        body = await request.json()
        
        # Log the received data
        log_with_timestamp("\n=== RECEIVED WEBHOOK DATA ===")
        log_with_timestamp(f"Body: {json.dumps(body, indent=2)}")
        log_with_timestamp("==============================\n")
        
        # Get UID from query parameters
        uid = request.query_params.get("uid", "default_user")
        
        # Parse and store the memory
        # Note: In a production environment, you'd validate this data more thoroughly
        try:
            memory = Memory(**body)
            memory_id = str(datetime.now().timestamp())
            store_memory(uid, memory_id, memory)
            log_with_timestamp(f"Successfully stored memory with ID: {memory_id} for user: {uid}")
        except Exception as e:
            log_with_timestamp(f"Error parsing/storing memory: {str(e)}")
            # Even if parsing fails, we'll still return 200 to acknowledge receipt
        
        return {"status": "success", "message": "Memory data received and logged"}
    except Exception as e:
        log_with_timestamp(f"Error processing webhook: {str(e)}")
        # Return success even if there's an error to acknowledge receipt
        # In a production environment, you might want different behavior
        return {"status": "error", "message": str(e)}

@router.post('/chatgpt/memory', tags=['chatgpt'], response_model=EndpointResponse)
async def receive_memory(memory: Memory, uid: str):
    """
    Endpoint to receive memory/conversation data from OMI.
    This stores the conversation for later retrieval by ChatGPT actions.
    """
    try:
        # Log the received data
        log_with_timestamp("\n=== RECEIVED MEMORY DATA ===")
        log_with_timestamp(f"User ID: {uid}")
        log_with_timestamp(f"Memory Title: {memory.structured.title}")
        log_with_timestamp("===========================\n")
        
        # Store the memory with a timestamp and user ID
        memory_id = str(datetime.now().timestamp())
        store_memory(uid, memory_id, memory)
        
        return {"message": "Memory successfully received and stored"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store memory: {str(e)}")

@router.get('/chatgpt/setup', response_class=HTMLResponse, tags=['chatgpt'])
async def setup_chatgpt(request: Request, uid: str):
    """
    Setup page for ChatGPT integration.
    """
    if not uid:
        raise HTTPException(status_code=400, detail='UID is required')
    
    oauth_url = get_chatgpt().get_oauth_url(uid)
    return templates.TemplateResponse("setup_chatgpt.html", {"request": request, "uid": uid, "oauth_url": oauth_url})

@router.get('/auth/chatgpt/callback', response_class=HTMLResponse, tags=['chatgpt'])
async def callback_auth_chatgpt(request: Request, state: str, code: str):
    """
    Callback from ChatGPT OAuth.
    """
    uid = state

    # Get access token
    oauth_result = get_chatgpt().get_access_token(code)
    if "error" in oauth_result:
        err = oauth_result["error"]
        log_with_timestamp(err)
        return templates.TemplateResponse("setup_chatgpt.html", {
            "request": request, 
            "uid": uid,
            "oauth_url": get_chatgpt().get_oauth_url(uid),
            "error_message": f"Authentication failed. Please try again! (Error: {err.get('message', 'Unknown error')})"
        })

    # Store the token
    from db import r
    oauth = oauth_result["result"]
    r.set(f'chatgpt_access_token:{uid}', oauth.access_token)
    r.set(f'chatgpt_refresh_token:{uid}', oauth.refresh_token)
    r.set(f'chatgpt_token_expires:{uid}', oauth.expires_at.isoformat() if oauth.expires_at else "")
    
    return templates.TemplateResponse("okpage.html", {"request": request, "uid": uid})

# --- OAuth endpoints for OpenAI integration ---

@router.get('/chatgpt/oauth/authorize', tags=['oauth'])
async def authorize(
    response_type: str, 
    client_id: str, 
    redirect_uri: str, 
    state: str,
    scope: Optional[str] = ""
):
    """
    OAuth 2.0 authorization endpoint.
    This is the URL that should be provided in the OpenAI "Authorization URL" field.
    """
    # Validate client_id (should match your configured client ID)
    expected_client_id = os.getenv('OPENAI_CLIENT_ID')
    if expected_client_id and client_id != expected_client_id:
        raise HTTPException(status_code=400, detail="Invalid client_id")
    
    # Generate random state for CSRF protection
    auth_state = secrets.token_urlsafe(32)
    
    # Store state for validation in callback
    AUTH_STATES[auth_state] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "openai_state": state,  # Original state from OpenAI
        "timestamp": datetime.now()
    }
    
    # Redirect to login/consent page
    # In a real implementation, you would show a login page first
    return RedirectResponse(f"/chatgpt/consent?state={auth_state}")

@router.get('/chatgpt/consent', response_class=HTMLResponse, tags=['oauth'])
async def consent_page(request: Request, state: str):
    """
    Show consent page to user for authorizing the GPT to access their OMI data.
    """
    # Validate state
    if state not in AUTH_STATES:
        raise HTTPException(status_code=400, detail="Invalid state")
    
    # Get state info
    state_info = AUTH_STATES[state]
    
    # Show consent page
    return templates.TemplateResponse("oauth_consent.html", {
        "request": request,
        "state": state,
        "client_id": state_info["client_id"],
        "scopes": state_info["scope"].split() if state_info["scope"] else []
    })

@router.post('/chatgpt/consent', tags=['oauth'])
async def handle_consent(state: str, user_id: str, accept: bool = Form(False)):
    """
    Handle user consent decision.
    """
    # Validate state
    if state not in AUTH_STATES:
        raise HTTPException(status_code=400, detail="Invalid state")
    
    # Get state info
    state_info = AUTH_STATES[state]
    
    if not accept:
        # User declined, redirect back to OpenAI with error
        return RedirectResponse(
            f"{state_info['redirect_uri']}?error=access_denied&state={state_info['openai_state']}"
        )
    
    # User accepted, generate authorization code
    auth_code = secrets.token_urlsafe(32)
    
    # Store authorization code with user ID for later token exchange
    AUTH_CODES[auth_code] = {
        "user_id": user_id,
        "client_id": state_info["client_id"],
        "scope": state_info["scope"],
        "timestamp": datetime.now(),
        "redirect_uri": state_info["redirect_uri"]
    }
    
    # Redirect back to OpenAI with code
    return RedirectResponse(
        f"{state_info['redirect_uri']}?code={auth_code}&state={state_info['openai_state']}"
    )

@router.post('/chatgpt/oauth/token', tags=['oauth'])
async def token_exchange(
    grant_type: str = Form(...),
    code: Optional[str] = Form(None),
    refresh_token: Optional[str] = Form(None),
    client_id: str = Form(...),
    client_secret: str = Form(...),
    redirect_uri: Optional[str] = Form(None)
):
    """
    OAuth 2.0 token endpoint.
    This is the URL that should be provided in the OpenAI "Token URL" field.
    """
    # Validate client credentials
    expected_client_id = os.getenv('OPENAI_CLIENT_ID')
    expected_client_secret = os.getenv('OPENAI_CLIENT_SECRET')
    
    if (expected_client_id and client_id != expected_client_id) or \
       (expected_client_secret and client_secret != expected_client_secret):
        return {"error": "invalid_client", "error_description": "Invalid client credentials"}
    
    if grant_type == "authorization_code":
        # Authorization code flow
        if not code or code not in AUTH_CODES:
            return {"error": "invalid_grant", "error_description": "Invalid authorization code"}
        
        # Get code info
        code_info = AUTH_CODES[code]
        
        # Validate redirect URI
        if redirect_uri != code_info["redirect_uri"]:
            return {"error": "invalid_grant", "error_description": "Redirect URI mismatch"}
        
        # Generate tokens
        access_token = secrets.token_urlsafe(32)
        refresh_token_val = secrets.token_urlsafe(32)
        expires_in = 3600  # 1 hour
        
        # Store tokens
        ACCESS_TOKENS[access_token] = {
            "user_id": code_info["user_id"],
            "scope": code_info["scope"],
            "expires_at": datetime.now() + timedelta(seconds=expires_in),
            "refresh_token": refresh_token_val
        }
        
        # Remove used authorization code
        del AUTH_CODES[code]
        
        # Return tokens
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": expires_in,
            "refresh_token": refresh_token_val,
            "scope": code_info["scope"]
        }
    
    elif grant_type == "refresh_token":
        # Refresh token flow
        if not refresh_token:
            return {"error": "invalid_grant", "error_description": "Refresh token required"}
        
        # Find token by refresh token
        user_id = None
        scope = ""
        for token, token_info in ACCESS_TOKENS.items():
            if token_info.get("refresh_token") == refresh_token:
                user_id = token_info["user_id"]
                scope = token_info["scope"]
                # Remove old token
                del ACCESS_TOKENS[token]
                break
        
        if not user_id:
            return {"error": "invalid_grant", "error_description": "Invalid refresh token"}
        
        # Generate new tokens
        new_access_token = secrets.token_urlsafe(32)
        new_refresh_token = secrets.token_urlsafe(32)
        expires_in = 3600  # 1 hour
        
        # Store new tokens
        ACCESS_TOKENS[new_access_token] = {
            "user_id": user_id,
            "scope": scope,
            "expires_at": datetime.now() + timedelta(seconds=expires_in),
            "refresh_token": new_refresh_token
        }
        
        # Return new tokens
        return {
            "access_token": new_access_token,
            "token_type": "bearer",
            "expires_in": expires_in,
            "refresh_token": new_refresh_token,
            "scope": scope
        }
    
    else:
        return {"error": "unsupported_grant_type", "error_description": "Unsupported grant type"}

# Function to validate access token and get user ID
async def get_current_user(token: str = Depends(oauth2_scheme)):
    if token not in ACCESS_TOKENS:
        raise HTTPException(
            status_code=401,
            detail="Invalid access token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token_info = ACCESS_TOKENS[token]
    
    # Check if token has expired
    if datetime.now() > token_info["expires_at"]:
        raise HTTPException(
            status_code=401,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return token_info["user_id"]

# --- API Endpoints for ChatGPT actions to retrieve data ---

@router.get('/api/conversations', tags=['chatgpt'])
async def get_conversations(user_id: str = Depends(get_current_user)):
    """
    API endpoint for ChatGPT Actions to retrieve a list of conversations for the authenticated user.
    """
    # Get all memories for the user
    memories = get_memories_by_uid(user_id)
    
    # Format the response
    conversations = []
    for memory_id, memory in memories.items():
        conversations.append({
            "id": memory_id,
            "title": memory.structured.title,
            "created_at": memory.created_at.isoformat(),
            "category": memory.structured.category,
            "overview": memory.structured.overview
        })
    
    return {"conversations": conversations}

@router.get('/api/conversations/{conversation_id}', tags=['chatgpt'])
async def get_conversation(conversation_id: str, user_id: str = Depends(get_current_user)):
    """
    API endpoint for ChatGPT Actions to retrieve a specific conversation.
    """
    # Get the memory
    memory = get_memory(user_id, conversation_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Format the response
    return {
        "id": conversation_id,
        "created_at": memory.created_at.isoformat(),
        "started_at": memory.started_at.isoformat() if memory.started_at else None,
        "finished_at": memory.finished_at.isoformat() if memory.finished_at else None,
        "transcript": memory.get_transcript(include_timestamps=True),
        "structured": {
            "title": memory.structured.title,
            "overview": memory.structured.overview,
            "emoji": memory.structured.emoji,
            "category": memory.structured.category
        }
    }

# --- API endpoints for retrieving memories ---

@router.get('/chatgpt/api/memories', tags=['api'])
async def get_user_memories(uid: Optional[str] = None):
    """
    Retrieve all memories for a user.
    If no UID is provided, returns memories for all users.
    """
    try:
        if uid:
            # Get memories for specific user
            memories = get_memories_by_uid(uid)
            if not memories:
                return {"memories": [], "message": f"No memories found for user {uid}"}
            
            # Convert memories to dict format for JSON response
            formatted_memories = {}
            for memory_id, memory in memories.items():
                formatted_memories[memory_id] = memory.dict()
            
            return {"memories": formatted_memories, "count": len(formatted_memories)}
        else:
            # Get all memories for all users
            all_memories = {}
            for user_id in MEMORY_STORE:
                user_memories = {}
                for memory_id, memory in MEMORY_STORE[user_id].items():
                    user_memories[memory_id] = memory.dict()
                all_memories[user_id] = user_memories
            
            return {"memories": all_memories, "users": len(all_memories)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve memories: {str(e)}")

@router.get('/chatgpt/api/memories/{memory_id}', tags=['api'])
async def get_memory_by_id(memory_id: str, uid: str):
    """
    Retrieve a specific memory by ID for a user.
    """
    try:
        memory = get_memory(uid, memory_id)
        if not memory:
            raise HTTPException(status_code=404, detail=f"Memory {memory_id} not found for user {uid}")
        
        return {"memory": memory.dict()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve memory: {str(e)}") 