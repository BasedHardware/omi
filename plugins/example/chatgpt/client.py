import os
import requests
from datetime import datetime, timedelta


class ChatGPTOAuthModel:
    def __init__(self):
        self.access_token = ""
        self.refresh_token = ""
        self.expires_at = None
    
    @classmethod
    def from_dict(cls, data: dict) -> "ChatGPTOAuthModel":
        model = cls()
        model.access_token = data.get("access_token", "")
        model.refresh_token = data.get("refresh_token", "")
        expires_in = data.get("expires_in", 3600)
        model.expires_at = datetime.now() + timedelta(seconds=expires_in)
        return model


class ChatGPTClient:
    """Implementation of the ChatGPT OAuth APIs."""

    def __init__(
            self,
            oauth_client_id="",
            oauth_client_secret="",
            oauth_redirect_uri="",
            auth_url="",
            token_url="",
    ) -> None:
        self.oauth_client_id = oauth_client_id
        self.oauth_client_secret = oauth_client_secret
        self.oauth_redirect_uri = oauth_redirect_uri
        self.auth_url = auth_url
        self.token_url = token_url

    def get_oauth_url(self, uid: str):
        """Generate OAuth URL with state parameter for user auth flow"""
        # Use user ID as state to identify user in callback
        state = uid
        return f"{self.auth_url}?client_id={self.oauth_client_id}&redirect_uri={self.oauth_redirect_uri}&response_type=code&state={state}&scope=read"

    def get_access_token(self, code: str):
        """Exchange authorization code for access token"""
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.oauth_redirect_uri,
            "client_id": self.oauth_client_id,
            "client_secret": self.oauth_client_secret
        }
        
        resp = requests.post(self.token_url, headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }, data=data)
        
        if resp.status_code != 200:
            resp_json = resp.json()
            print(f"Error: HTTP_{resp.status_code} {resp_json}")
            return {
                "error": {
                    "status": resp.status_code,
                    "message": resp_json.get("error_description", "Unknown error"),
                },
            }

        print(resp.json())
        return {"result": ChatGPTOAuthModel.from_dict(resp.json())}

    def refresh_access_token(self, refresh_token: str):
        """Refresh the access token using refresh token"""
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.oauth_client_id,
            "client_secret": self.oauth_client_secret
        }
        
        resp = requests.post(self.token_url, headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }, data=data)
        
        if resp.status_code != 200:
            resp_json = resp.json()
            print(f"Error: HTTP_{resp.status_code} {resp_json}")
            return {
                "error": {
                    "status": resp.status_code,
                    "message": resp_json.get("error_description", "Unknown error"),
                },
            }

        print(resp.json())
        return {"result": ChatGPTOAuthModel.from_dict(resp.json())}


# Initialize client with environment variables
client = ChatGPTClient(
    oauth_client_id=os.getenv('CHATGPT_OAUTH_CLIENT_ID', ''),
    oauth_client_secret=os.getenv('CHATGPT_OAUTH_CLIENT_SECRET', ''),
    oauth_redirect_uri=os.getenv('CHATGPT_OAUTH_REDIRECT_URI', ''),
    auth_url=os.getenv('CHATGPT_AUTH_URL', 'https://auth.openai.com/oauth/authorize'),
    token_url=os.getenv('CHATGPT_TOKEN_URL', 'https://auth.openai.com/oauth/token'),
)


def get_chatgpt():
    return client


# This block will run when the script is executed directly
if __name__ == "__main__":
    print("ChatGPT OAuth Client Initialized")
    print("-----------------------------------")
    print("OAuth Configuration:")
    print(f"Client ID: {client.oauth_client_id or 'Not set'}")
    print(f"Redirect URI: {client.oauth_redirect_uri or 'Not set'}")
    print(f"Auth URL: {client.auth_url}")
    print(f"Token URL: {client.token_url}")
    print("-----------------------------------")
    print("Test OAuth URL for a sample user:")
    print(client.get_oauth_url("test_user_123"))
    print("-----------------------------------")
    print("NOTE: This script doesn't do anything when run directly.")
    print("It provides classes and functions for the OMI-ChatGPT integration.")
    print("To test the full integration, run the FastAPI server with:")
    print("  python -m uvicorn main:app --reload")
    print("-----------------------------------") 