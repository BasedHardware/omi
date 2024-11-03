from fastapi import Request, HTTPException
import firebase_admin
from firebase_admin import auth

async def verify_token(request: Request):
    """Verify Firebase ID token"""
    authorization = request.headers.get("Authorization")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No authorization token provided")
    
    token = authorization.split(" ")[1]
    
    try:
        # Verify the Firebase token
        decoded_token = auth.verify_id_token(token)
        return decoded_token
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid authorization token: {str(e)}") 