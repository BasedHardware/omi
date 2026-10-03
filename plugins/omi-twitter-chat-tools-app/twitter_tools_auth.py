<content>
import os
from fastapi import Depends, HTTPException, status, Request, Query
from fastapi.security import APIKeyHeader, APIKeyQuery

# Read the shared secret from environment variable
# The service should be down if this is not configured
TWITTER_TOOLS_SECRET = os.environ.get("TWITTER_TOOLS_SECRET")
if not TWITTER_TOOLS_SECRET:
    raise RuntimeError("TWITTER_TOOLS_SECRET environment variable must be set")

api_key_header = APIKeyHeader(name="Authorization", auto_error=False)
api_key_query = APIKeyQuery(name="twitter_tools_token", auto_error=False)

async def get_api_key(
    api_key_header: str = Depends(api_key_header),
    api_key_query: str = Depends(api_key_query),
) -> str:
    """
    Retrieve the API key from either the Authorization header or query parameter.
    The Authorization header should be in the format 'Bearer <api_key>'.
    """
    api_key = None

    # Check Authorization header
    if api_key_header and api_key_header.startswith("Bearer "):
        api_key = api_key_header.split(" ", 1)[1]
    
    # Check query parameter if header not found or invalid
    if not api_key and api_key_query:
        api_key = api_key_query

    # Validate the API key
    if api_key is None or api_key != TWITTER_TOOLS_SECRET:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    
    return api_key

async def require_twitter_tools_auth(request: Request, api_key: str = Depends(get_api_key)):
    """
    Dependency to require authentication for Twitter tools routes.
    This function simply passes through if the API key is valid.
    It can be extended to include additional logic if needed.
    """
    # The api_key is already validated by get_api_key
    # We can add any additional request processing here if needed
    pass

# Export the dependency for use in other modules
require_twitter_tools_auth_dependency = require_twitter_tools_auth
</content>