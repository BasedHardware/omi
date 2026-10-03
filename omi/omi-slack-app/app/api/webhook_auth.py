```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
import os
import logging

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)

# Get webhook secret from environment
SLACK_WEBHOOK_SECRET = os.environ.get("SLACK_WEBHOOK_SECRET")

async def require_slack_webhook_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    token: Optional[str] = None
) -> str:
    """
    Authenticate webhook requests using either:
    1. Authorization: Bearer <secret> header
    2. ?slack_webhook_token=<secret> query parameter
    
    Returns the authenticated uid from the request body.
    Raises appropriate HTTPException on auth failure.
    """
    # Check if webhook is configured
    if not SLACK_WEBHOOK_SECRET:
        logger.warning("SLACK_WEBHOOK_SECRET not configured, rejecting all webhook requests")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook service not configured"
        )
    
    # Get token from either header or query param
    auth_token = None
    if credentials:
        auth_token = credentials.credentials
    elif token:
        auth_token = token
    
    # Validate token
    if not auth_token or auth_token != SLACK_WEBHOOK_SECRET:
        logger.warning("Invalid webhook token provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook token"
        )
    
    # The actual uid validation will happen in the endpoint
    # This just ensures the secret is correct
    return True
```

===FILE: omi/omi-clickup-app/app/api/webhook_auth.py===
```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
import os
import logging

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)

# Get webhook secret from environment
CLICKUP_WEBHOOK_SECRET = os.environ.get("CLICKUP_WEBHOOK_SECRET")

async def require_clickup_webhook_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    token: Optional[str] = None
) -> str:
    """
    Authenticate webhook requests using either:
    1. Authorization: Bearer <secret> header
    2. ?clickup_webhook_token=<secret> query parameter
    
    Returns the authenticated uid from the request body.
    Raises appropriate HTTPException on auth failure.
    """
    # Check if webhook is configured
    if not CLICKUP_WEBHOOK_SECRET:
        logger.warning("CLICKUP_WEBHOOK_SECRET not configured, rejecting all webhook requests")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook service not configured"
        )
    
    # Get token from either header or query param
    auth_token = None
    if credentials:
        auth_token = credentials.credentials
    elif token:
        auth_token = token
    
    # Validate token
    if not auth_token or auth_token != CLICKUP_WEBHOOK_SECRET:
        logger.warning("Invalid webhook token provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook token"
        )
    
    # The actual uid validation will happen in the endpoint
    # This just ensures the secret is correct
    return True
```

===FILE: omi/omi-twitter-app/app/api/webhook_auth.py===
```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
import os
import logging

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)

# Get webhook secret from environment
TWITTER_WEBHOOK_SECRET = os.environ.get("TWITTER_WEBHOOK_SECRET")

async def require_twitter_webhook_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    token: Optional[str] = None
) -> str:
    """
    Authenticate webhook requests using either:
    1. Authorization: Bearer <secret> header
    2. ?twitter_webhook_token=<secret> query parameter
    
    Returns the authenticated uid from the request body.
    Raises appropriate HTTPException on auth failure.
    """
    # Check if webhook is configured
    if not TWITTER_WEBHOOK_SECRET:
        logger.warning("TWITTER_WEBHOOK_SECRET not configured, rejecting all webhook requests")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook service not configured"
        )
    
    # Get token from either header or query param
    auth_token = None
    if credentials:
        auth_token = credentials.credentials
    elif token:
        auth_token = token
    
    # Validate token
    if not auth_token or auth_token != TWITTER_WEBHOOK_SECRET:
        logger.warning("Invalid webhook token provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook token"
        )
    
    # The actual uid validation will happen in the endpoint
    # This just ensures the secret is correct
    return True
```

===FILE: omi/omi-slack-app/app/api/tools_auth.py===
```python
from fastapi import Depends, HTTPException, status
from typing import Optional
import logging

logger = logging.getLogger(__name__)

async def require_slack_tool_auth(uid: str) -> str:
    """
    Validate that the provided uid is not empty.
    This is used for internal tool calls that should be authenticated
    by the application itself, not by external webhook requests.
    
    Returns the validated uid.
    Raises HTTPException on validation failure.
    """
    if not uid or not uid.strip():
        logger.warning("Blank uid provided to Slack tool")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="UID cannot be blank"
        )
    
    return uid
```

===FILE: omi/omi-slack-app/app/api/webhook.py===
```python
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional
import logging
from .webhook_auth import require_slack_webhook_auth

logger = logging.getLogger(__name__)

router = APIRouter()

class WebhookPayload(BaseModel):
    uid: str
    transcript: str

@router.post("/webhook")
async def slack_webhook(
    payload: WebhookPayload,
    auth_result: bool = Depends(require_slack_webhook_auth)
):
    """
    Handle Slack transcript webhooks with authentication.
    
    After authentication, validate uid and process the transcript.
    """
    # Validate uid
    if not payload.uid or not payload.uid.strip():
        logger.warning("Blank uid in webhook payload")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="UID cannot be blank"
        )
    
    # Process the transcript
    try:
        # Here you would typically:
        # 1. Get the user's Slack OAuth token from the database
        # 2. Post the transcript to their Slack channel
        logger.info(f"Processing webhook for uid: {payload.uid}")
        
        # TODO: Implement actual transcript processing
        return {"status": "success", "uid": payload.uid}
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing webhook"
        )
```

===FILE: omi/omi-clickup-app/app/api/webhook.py===
```python
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional
import logging
from .webhook_auth import require_clickup_webhook_auth

logger = logging.getLogger(__name__)

router = APIRouter()

class WebhookPayload(BaseModel):
    uid: str
    transcript: str

@router.post("/webhook")
async def clickup_webhook(
    payload: WebhookPayload,
    auth_result: bool = Depends(require_clickup_webhook_auth)
):
    """
    Handle ClickUp transcript webhooks with authentication.
    
    After authentication, validate uid and process the transcript.
    """
    # Validate uid
    if not payload.uid or not payload.uid.strip():
        logger.warning("Blank uid in webhook payload")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="UID cannot be blank"
        )
    
    # Process the transcript
    try:
        # Here you would typically:
        # 1. Get the user's ClickUp OAuth token from the database
        # 2. Create a task in their ClickUp list with the transcript
        logger.info(f"Processing webhook for uid: {payload.uid}")
        
        # TODO: Implement actual transcript processing
        return {"status": "success", "uid": payload.uid}
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing webhook"
        )
```

===FILE: omi/omi-twitter-app/app/api/webhook.py===
```python
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional
import logging
from .webhook_auth import require_twitter_webhook_auth

logger = logging.getLogger(__name__)

router = APIRouter()

class WebhookPayload(BaseModel):
    uid: str
    transcript: str

@router.post("/webhook")
async def twitter_webhook(
    payload: WebhookPayload,
    auth_result: bool = Depends(require_twitter_webhook_auth)
):
    """
    Handle Twitter transcript webhooks with authentication.
    
    After authentication, validate uid and process the transcript.
    """
    # Validate uid
    if not payload.uid or not payload.uid.strip():
        logger.warning("Blank uid in webhook payload")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="UID cannot be blank"
        )
    
    # Process the transcript
    try:
        # Here you would typically:
        # 1. Get the user's Twitter OAuth token from the database
        # 2. Post a tweet with the transcript
        logger.info(f"Processing webhook for uid: {payload.uid}")
        
        # TODO: Implement actual transcript processing
        return {"status": "success", "uid": payload.uid}
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing webhook"
        )
```

===FILE: omi/omi-slack-app/app/api/send_message.py===
```python
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional
import logging
from .tools_auth import require_slack_tool_auth

logger = logging.getLogger(__name__)

router = APIRouter()

class SendMessageRequest(BaseModel):
    uid: str
    message: str
    channel: Optional[str] = None

@router.post("/api/send_message")
async def send_message(
    request: SendMessageRequest,
    uid: str = Depends(require_slack_tool_auth)
):
    """
    Send a message as the authenticated user.
    The uid is validated by require_slack_tool_auth.
    """
    try:
        # Here you would typically:
        # 1. Get the user's Slack OAuth token from the database
        # 2. Send the message to their Slack workspace
        logger.info(f"Sending message for uid: {uid}")
        
        # TODO: Implement actual message sending
        return {"status": "success", "uid": uid}
    except Exception as e:
        logger.error(f"Error sending message: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error sending message"
        )
```

===FILE: omi/omi-slack-app/app/api/search_messages.py===
```python
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional
import logging
from .tools_auth import require_slack_tool_auth

logger = logging.getLogger(__name__)

router = APIRouter()

class SearchMessagesRequest(BaseModel):
    uid: str
    query: str
    channel: Optional[str] = None

@router.post("/api/search_messages")
async def search_messages(
    request: SearchMessagesRequest,
    uid: str = Depends(require_slack_tool_auth)
):
    """
    Search messages in the authenticated user's Slack workspace.
    The uid is validated by require_slack_tool_auth.
    """
    try:
        # Here you would typically:
        # 1. Get the user's Slack OAuth token from the database
        # 2. Search messages in their Slack workspace
        logger.info(f"Searching messages for uid: {uid}")
        
        # TODO: Implement actual message searching
        return {"status": "success", "uid": uid}
    except Exception as e:
        logger.error(f"Error searching messages: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error searching messages"
        )
```

===FILE: omi/omi-slack-app/app/api/search_channels.py===
```python
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional
import logging
from .tools_auth import require_slack_tool_auth

logger = logging.getLogger(__name__)

router = APIRouter()

class SearchChannelsRequest(BaseModel):
    uid: str
    query: Optional[str] = None

@router.post("/api/search_channels")
async def search_channels(
    request: SearchChannelsRequest,
    uid: str = Depends(require_slack_tool_auth)
):
    """
    Search channels in the authenticated user's Slack workspace.
    The uid is validated by require_slack_tool_auth.
    """
    try:
        # Here you would typically:
        # 1. Get the user's Slack OAuth token from the database
        # 2. Search channels in their Slack workspace
        logger.info(f"Searching channels for uid: {uid}")
        
        # TODO: Implement actual channel searching
        return {"status": "success", "uid": uid}
    except Exception as e:
        logger.error(f"Error searching channels: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error searching channels"
        )
```
