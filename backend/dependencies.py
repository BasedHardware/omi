from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth

import database.mcp_api_key as mcp_api_key_db

bearer_scheme = HTTPBearer()


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
) -> str:
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        id_token = credentials.credentials
        decoded_token = auth.verify_id_token(id_token)
        return decoded_token["uid"]
    except Exception as e:
        print(f"Error verifying Firebase ID token: {e}")
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")


api_key_header = APIKeyHeader(name="Authorization", auto_error=False)


async def get_uid_from_mcp_api_key(api_key: str = Security(api_key_header)) -> str:
    if not api_key or not api_key.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header. Must be 'Bearer API_KEY'",
        )

    token = api_key.replace("Bearer ", "")
    user_id = mcp_api_key_db.get_user_id_by_api_key(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return user_id
