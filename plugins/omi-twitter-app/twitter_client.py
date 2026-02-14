import tweepy
from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv()  # Load .env file


class TwitterClient:
    """Handles Twitter API interactions."""
    
    def __init__(self):
        self.api_key = os.getenv("TWITTER_API_KEY")
        self.api_secret = os.getenv("TWITTER_API_SECRET")
        self.client_id = os.getenv("TWITTER_CLIENT_ID")
        self.client_secret = os.getenv("TWITTER_CLIENT_SECRET")
        self._oauth_handlers = {}  # Store OAuth handlers for callback
        self._state_to_uid = {}  # Map Tweepy's state to our uid
    
    def get_oauth2_client(self, access_token: str) -> tweepy.Client:
        """Create Twitter API client with OAuth 2.0 user context."""
        # For OAuth 2.0 user access tokens, use bearer_token parameter
        # This sends the token in Authorization: Bearer header
        return tweepy.Client(bearer_token=access_token)
    
    async def post_tweet(self, access_token: str, text: str) -> Optional[dict]:
        """Post a tweet to Twitter."""
        try:
            # Use Tweepy Client with OAuth 2.0 bearer token
            client = tweepy.Client(bearer_token=access_token)
            
            # Create tweet using user context
            response = client.create_tweet(text=text, user_auth=False)
            
            if response.data:
                return {
                    "success": True,
                    "tweet_id": response.data['id'],
                    "text": text
                }
            return None
            
        except tweepy.TweepyException as e:
            print(f"Twitter API error: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e)
            }
        except Exception as e:
            print(f"Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_authorization_url(self, redirect_uri: str, uid: str) -> str:
        """
        Generate OAuth 2.0 authorization URL with PKCE.
        Tweepy handles PKCE internally through the OAuth2UserHandler instance.
        Returns auth_url
        """
        oauth2_user_handler = tweepy.OAuth2UserHandler(
            client_id=self.client_id,
            redirect_uri=redirect_uri,
            scope=["tweet.read", "tweet.write", "users.read", "offline.access"],
            client_secret=self.client_secret
        )
        
        # get_authorization_url() returns the URL with Tweepy's own state parameter
        # Tweepy internally generates and stores code_verifier in the handler
        auth_url = oauth2_user_handler.get_authorization_url()
        
        # Extract the state parameter that Tweepy generated
        # The state is stored in the handler internally
        tweepy_state = oauth2_user_handler._state
        
        # Store handler by Tweepy's state for later use in callback
        self._oauth_handlers[tweepy_state] = oauth2_user_handler
        
        # Map Tweepy's state to our uid
        self._state_to_uid[tweepy_state] = uid
        
        return auth_url
    
    def get_access_token(self, authorization_response: str, state: str) -> tuple[dict, str]:
        """
        Exchange authorization code for access token.
        Returns (token_dict, uid)
        """
        # Retrieve the stored OAuth handler by state
        oauth2_user_handler = self._oauth_handlers.get(state)
        
        if not oauth2_user_handler:
            raise Exception("OAuth session not found. Please restart authentication.")
        
        # Get the uid associated with this state
        uid = self._state_to_uid.get(state)
        
        if not uid:
            raise Exception("User ID not found for this session.")
        
        # Exchange code for token
        token_dict = oauth2_user_handler.fetch_token(authorization_response)
        
        # Debug: Log what we got
        print(f"📦 Token exchange result:", flush=True)
        print(f"   Keys in token_dict: {list(token_dict.keys())}", flush=True)
        print(f"   Has refresh_token: {'refresh_token' in token_dict}", flush=True)
        
        # Clean up stored handler and mapping
        if state in self._oauth_handlers:
            del self._oauth_handlers[state]
        if state in self._state_to_uid:
            del self._state_to_uid[state]
        
        return token_dict, uid
    
    def refresh_access_token(self, refresh_token: str) -> dict:
        """
        Refresh the access token using refresh token.
        Returns new token_dict with access_token, refresh_token, expires_in
        """
        try:
            import requests
            
            # Make direct API call to refresh token
            # Tweepy's refresh_token method can be unreliable
            response = requests.post(
                "https://api.twitter.com/2/oauth2/token",
                auth=(self.client_id, self.client_secret),
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": self.client_id
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            
            if response.status_code == 200:
                token_data = response.json()
                print(f"✅ Token refresh successful")
                return token_data
            else:
                error_msg = response.text
                print(f"❌ Token refresh failed: {response.status_code} - {error_msg}")
                raise Exception(f"Token refresh failed: {error_msg}")
                
        except Exception as e:
            print(f"❌ Token refresh error: {e}", flush=True)
            import traceback
            traceback.print_exc()
            raise Exception(f"Failed to refresh token: {e}")

