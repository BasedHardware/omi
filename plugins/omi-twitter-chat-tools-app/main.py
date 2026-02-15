"""
Twitter/X Integration App for Omi

This app provides Twitter/X integration through OAuth2 authentication
and chat tools for managing tweets, reading timeline, and more.
"""
import os
import sys
import secrets
import hashlib
import base64
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

from db import (
    store_twitter_tokens,
    get_twitter_tokens,
    update_twitter_tokens,
    delete_twitter_tokens,
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


# Twitter OAuth2 Configuration
TWITTER_CLIENT_ID = os.getenv("TWITTER_CLIENT_ID", "")
TWITTER_CLIENT_SECRET = os.getenv("TWITTER_CLIENT_SECRET", "")
TWITTER_REDIRECT_URI = os.getenv("TWITTER_REDIRECT_URI", "http://localhost:8080/auth/twitter/callback")

# Twitter API endpoints
TWITTER_AUTH_URL = "https://twitter.com/i/oauth2/authorize"
TWITTER_TOKEN_URL = "https://api.twitter.com/2/oauth2/token"
TWITTER_API_BASE = "https://api.twitter.com/2"

# Scopes needed for Twitter access
TWITTER_SCOPES = [
    "tweet.read",
    "tweet.write",
    "users.read",
    "follows.read",
    "like.read",
    "like.write",
    "offline.access"
]

app = FastAPI(
    title="Twitter Omi Integration",
    description="Twitter/X integration for Omi - Post tweets and read your timeline with chat",
    version="1.0.0"
)


# ============================================
# Helper Functions
# ============================================

def generate_code_verifier() -> str:
    """Generate PKCE code verifier."""
    return secrets.token_urlsafe(64)[:128]


def generate_code_challenge(verifier: str) -> str:
    """Generate PKCE code challenge from verifier."""
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def get_valid_access_token(uid: str) -> Optional[str]:
    """
    Get a valid access token, refreshing if necessary.
    Returns None if user is not authenticated.
    """
    tokens = get_twitter_tokens(uid)
    if not tokens:
        return None

    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    expires_at = tokens.get("expires_at")

    # Check if token is expired (with 5 minute buffer)
    if expires_at:
        try:
            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if datetime.now(expiry.tzinfo) >= expiry - timedelta(minutes=5):
                # Token expired or about to expire, refresh it
                log(f"Token expired for {uid}, refreshing...")
                new_token = refresh_access_token(refresh_token)
                if new_token:
                    access_token = new_token["access_token"]
                    new_refresh = new_token.get("refresh_token", refresh_token)
                    new_expires_at = (datetime.utcnow() + timedelta(seconds=new_token.get("expires_in", 7200))).isoformat() + "Z"
                    update_twitter_tokens(uid, access_token, new_refresh, new_expires_at)
                else:
                    return None
        except Exception as e:
            log(f"Error checking token expiry: {e}")

    return access_token


def refresh_access_token(refresh_token: str) -> Optional[dict]:
    """Refresh the access token using the refresh token."""
    try:
        response = requests.post(
            TWITTER_TOKEN_URL,
            data={
                "client_id": TWITTER_CLIENT_ID,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token
            },
            auth=(TWITTER_CLIENT_ID, TWITTER_CLIENT_SECRET) if TWITTER_CLIENT_SECRET else None
        )

        if response.status_code == 200:
            return response.json()
        else:
            log(f"Token refresh failed: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        log(f"Error refreshing token: {e}")
        return None


def twitter_api_request(uid: str, method: str, endpoint: str, params: dict = None, json_data: dict = None) -> Optional[dict]:
    """Make an authenticated request to the Twitter API."""
    access_token = get_valid_access_token(uid)
    if not access_token:
        return None

    url = f"{TWITTER_API_BASE}{endpoint}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    try:
        if method == "GET":
            response = requests.get(url, headers=headers, params=params)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=json_data)
        elif method == "DELETE":
            response = requests.delete(url, headers=headers)
        else:
            return None

        if response.status_code in [200, 201]:
            return response.json()
        elif response.status_code == 204:
            return {"success": True}
        else:
            log(f"Twitter API error: {response.status_code} - {response.text}")
            return {"error": response.text, "status_code": response.status_code}

    except Exception as e:
        log(f"Twitter API request error: {e}")
        return {"error": str(e)}


def format_tweet(tweet: dict, includes: dict = None) -> str:
    """Format a tweet for display."""
    text = tweet.get("text", "")
    tweet_id = tweet.get("id", "")
    created_at = tweet.get("created_at", "")
    metrics = tweet.get("public_metrics", {})

    # Get author info if available
    author_name = "Unknown"
    author_username = ""
    if includes and "users" in includes:
        author_id = tweet.get("author_id")
        for user in includes["users"]:
            if user.get("id") == author_id:
                author_name = user.get("name", "Unknown")
                author_username = user.get("username", "")
                break

    # Format timestamp
    time_str = ""
    if created_at:
        try:
            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            time_str = dt.strftime("%b %d, %Y %I:%M %p")
        except:
            time_str = created_at[:10]

    # Build output
    parts = []
    if author_username:
        parts.append(f"**@{author_username}** ({author_name})")
    parts.append(text)

    if time_str:
        parts.append(f"*{time_str}*")

    # Add engagement metrics
    likes = metrics.get("like_count", 0)
    retweets = metrics.get("retweet_count", 0)
    replies = metrics.get("reply_count", 0)
    if likes or retweets or replies:
        parts.append(f"Likes: {likes} | Retweets: {retweets} | Replies: {replies}")

    parts.append(f"ID: `{tweet_id}`")

    return "\n".join(parts)


def get_user_id(uid: str) -> Optional[str]:
    """Get the Twitter user ID for the authenticated user."""
    tokens = get_twitter_tokens(uid)
    if tokens and tokens.get("twitter_user_id"):
        return tokens.get("twitter_user_id")

    # Fetch from API if not cached
    result = twitter_api_request(uid, "GET", "/users/me", params={"user.fields": "id,username,name"})
    if result and "data" in result:
        user_id = result["data"].get("id")
        # Cache it
        if user_id:
            tokens = get_twitter_tokens(uid)
            if tokens:
                tokens["twitter_user_id"] = user_id
                store_twitter_tokens(
                    uid,
                    tokens["access_token"],
                    tokens.get("refresh_token", ""),
                    tokens.get("expires_at", ""),
                    tokens.get("username", ""),
                    user_id
                )
        return user_id
    return None


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
                "name": "post_tweet",
                "description": "Post a new tweet to Twitter/X. Use this when the user wants to tweet something, post an update, or share on Twitter.",
                "endpoint": "/tools/post_tweet",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "The tweet text (max 280 characters). Required."
                        },
                        "reply_to": {
                            "type": "string",
                            "description": "Tweet ID to reply to (optional)."
                        }
                    },
                    "required": ["text"]
                },
                "auth_required": True,
                "status_message": "Posting tweet..."
            },
            {
                "name": "get_timeline",
                "description": "Get the user's home timeline with recent tweets. Use this when the user wants to see their feed, check what's happening, or view recent tweets.",
                "endpoint": "/tools/get_timeline",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "max_results": {
                            "type": "integer",
                            "description": "Number of tweets to return (default: 10, max: 100)"
                        }
                    },
                    "required": []
                },
                "auth_required": True,
                "status_message": "Getting your timeline..."
            },
            {
                "name": "get_my_tweets",
                "description": "Get the user's own recent tweets. Use this when the user wants to see their own tweets, check what they've posted, or view their tweet history.",
                "endpoint": "/tools/get_my_tweets",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "max_results": {
                            "type": "integer",
                            "description": "Number of tweets to return (default: 10, max: 100)"
                        }
                    },
                    "required": []
                },
                "auth_required": True,
                "status_message": "Getting your tweets..."
            },
            {
                "name": "get_mentions",
                "description": "Get tweets that mention the user. Use this when the user wants to see who mentioned them, check notifications, or see replies.",
                "endpoint": "/tools/get_mentions",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "max_results": {
                            "type": "integer",
                            "description": "Number of mentions to return (default: 10, max: 100)"
                        }
                    },
                    "required": []
                },
                "auth_required": True,
                "status_message": "Getting your mentions..."
            },
            {
                "name": "search_tweets",
                "description": "Search for tweets about a topic. Use this when the user wants to find tweets about something, search Twitter, or see what people are saying.",
                "endpoint": "/tools/search_tweets",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query. Required."
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Number of results (default: 10, max: 100)"
                        }
                    },
                    "required": ["query"]
                },
                "auth_required": True,
                "status_message": "Searching tweets..."
            },
            {
                "name": "like_tweet",
                "description": "Like a tweet. Use this when the user wants to like a specific tweet.",
                "endpoint": "/tools/like_tweet",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "tweet_id": {
                            "type": "string",
                            "description": "ID of the tweet to like. Required."
                        }
                    },
                    "required": ["tweet_id"]
                },
                "auth_required": True,
                "status_message": "Liking tweet..."
            },
            {
                "name": "unlike_tweet",
                "description": "Remove a like from a tweet. Use this when the user wants to unlike a tweet.",
                "endpoint": "/tools/unlike_tweet",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "tweet_id": {
                            "type": "string",
                            "description": "ID of the tweet to unlike. Required."
                        }
                    },
                    "required": ["tweet_id"]
                },
                "auth_required": True,
                "status_message": "Removing like..."
            },
            {
                "name": "retweet",
                "description": "Retweet a tweet. Use this when the user wants to retweet or share a tweet.",
                "endpoint": "/tools/retweet",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "tweet_id": {
                            "type": "string",
                            "description": "ID of the tweet to retweet. Required."
                        }
                    },
                    "required": ["tweet_id"]
                },
                "auth_required": True,
                "status_message": "Retweeting..."
            },
            {
                "name": "delete_tweet",
                "description": "Delete one of the user's tweets. Use this when the user wants to remove or delete their tweet.",
                "endpoint": "/tools/delete_tweet",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "tweet_id": {
                            "type": "string",
                            "description": "ID of the tweet to delete. Required."
                        }
                    },
                    "required": ["tweet_id"]
                },
                "auth_required": True,
                "status_message": "Deleting tweet..."
            },
            {
                "name": "get_user_profile",
                "description": "Get a Twitter user's profile information. Use this when the user wants to look up someone on Twitter or see profile details.",
                "endpoint": "/tools/get_user_profile",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "username": {
                            "type": "string",
                            "description": "Twitter username (without @). If not provided, returns the authenticated user's profile."
                        }
                    },
                    "required": []
                },
                "auth_required": True,
                "status_message": "Getting profile..."
            }
        ]
    }


# ============================================
# Chat Tool Endpoints
# ============================================

@app.post("/tools/post_tweet", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_post_tweet(request: Request):
    """Post a new tweet."""
    try:
        body = await request.json()
        log(f"=== POST_TWEET ===")

        uid = body.get("uid")
        text = body.get("text")
        reply_to = body.get("reply_to")

        if not uid:
            return ChatToolResponse(error="User ID is required")

        if not text:
            return ChatToolResponse(error="Tweet text is required")

        if len(text) > 280:
            return ChatToolResponse(error=f"Tweet is too long ({len(text)} characters). Maximum is 280 characters.")

        access_token = get_valid_access_token(uid)
        if not access_token:
            return ChatToolResponse(error="Please connect your Twitter account first in the app settings.")

        tweet_data = {"text": text}

        if reply_to:
            tweet_data["reply"] = {"in_reply_to_tweet_id": reply_to}

        result = twitter_api_request(uid, "POST", "/tweets", json_data=tweet_data)

        if not result or "error" in result:
            return ChatToolResponse(error=f"Failed to post tweet: {result.get('error', 'Unknown error')}")

        tweet = result.get("data", {})
        tweet_id = tweet.get("id", "")
        tweet_text = tweet.get("text", text)

        result_parts = [
            "**Tweet Posted!**",
            "",
            tweet_text,
            "",
            f"ID: `{tweet_id}`",
            f"Link: https://twitter.com/i/status/{tweet_id}"
        ]

        return ChatToolResponse(result="\n".join(result_parts))

    except Exception as e:
        log(f"Error posting tweet: {e}")
        import traceback
        traceback.print_exc()
        return ChatToolResponse(error=f"Failed to post tweet: {str(e)}")


@app.post("/tools/get_timeline", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_get_timeline(request: Request):
    """Get user's home timeline."""
    try:
        body = await request.json()
        log(f"=== GET_TIMELINE ===")

        uid = body.get("uid")
        max_results = min(body.get("max_results", 10), 100)

        if not uid:
            return ChatToolResponse(error="User ID is required")

        access_token = get_valid_access_token(uid)
        if not access_token:
            return ChatToolResponse(error="Please connect your Twitter account first in the app settings.")

        twitter_user_id = get_user_id(uid)
        if not twitter_user_id:
            return ChatToolResponse(error="Could not get your Twitter user ID.")

        result = twitter_api_request(uid, "GET", f"/users/{twitter_user_id}/timelines/reverse_chronological", params={
            "max_results": max_results,
            "tweet.fields": "created_at,public_metrics,author_id",
            "expansions": "author_id",
            "user.fields": "name,username"
        })

        if not result or "error" in result:
            return ChatToolResponse(error=f"Failed to get timeline: {result.get('error', 'Unknown error')}")

        tweets = result.get("data", [])
        includes = result.get("includes", {})

        if not tweets:
            return ChatToolResponse(result="No tweets in your timeline.")

        result_parts = [f"**Your Timeline ({len(tweets)} tweets)**", ""]

        for tweet in tweets:
            result_parts.append(format_tweet(tweet, includes))
            result_parts.append("")
            result_parts.append("---")
            result_parts.append("")

        return ChatToolResponse(result="\n".join(result_parts))

    except Exception as e:
        log(f"Error getting timeline: {e}")
        return ChatToolResponse(error=f"Failed to get timeline: {str(e)}")


@app.post("/tools/get_my_tweets", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_get_my_tweets(request: Request):
    """Get user's own tweets."""
    try:
        body = await request.json()
        log(f"=== GET_MY_TWEETS ===")

        uid = body.get("uid")
        max_results = min(body.get("max_results", 10), 100)

        if not uid:
            return ChatToolResponse(error="User ID is required")

        access_token = get_valid_access_token(uid)
        if not access_token:
            return ChatToolResponse(error="Please connect your Twitter account first in the app settings.")

        twitter_user_id = get_user_id(uid)
        if not twitter_user_id:
            return ChatToolResponse(error="Could not get your Twitter user ID.")

        result = twitter_api_request(uid, "GET", f"/users/{twitter_user_id}/tweets", params={
            "max_results": max_results,
            "tweet.fields": "created_at,public_metrics"
        })

        if not result or "error" in result:
            return ChatToolResponse(error=f"Failed to get tweets: {result.get('error', 'Unknown error')}")

        tweets = result.get("data", [])

        if not tweets:
            return ChatToolResponse(result="You haven't posted any tweets yet.")

        result_parts = [f"**Your Tweets ({len(tweets)})**", ""]

        for tweet in tweets:
            text = tweet.get("text", "")
            tweet_id = tweet.get("id", "")
            created_at = tweet.get("created_at", "")
            metrics = tweet.get("public_metrics", {})

            time_str = ""
            if created_at:
                try:
                    dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    time_str = dt.strftime("%b %d, %Y %I:%M %p")
                except:
                    time_str = created_at[:10]

            result_parts.append(f"- {text}")
            if time_str:
                result_parts.append(f"  *{time_str}*")
            likes = metrics.get("like_count", 0)
            retweets = metrics.get("retweet_count", 0)
            result_parts.append(f"  Likes: {likes} | Retweets: {retweets}")
            result_parts.append(f"  ID: `{tweet_id}`")
            result_parts.append("")

        return ChatToolResponse(result="\n".join(result_parts))

    except Exception as e:
        log(f"Error getting tweets: {e}")
        return ChatToolResponse(error=f"Failed to get tweets: {str(e)}")


@app.post("/tools/get_mentions", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_get_mentions(request: Request):
    """Get tweets mentioning the user."""
    try:
        body = await request.json()
        uid = body.get("uid")
        max_results = min(body.get("max_results", 10), 100)

        if not uid:
            return ChatToolResponse(error="User ID is required")

        access_token = get_valid_access_token(uid)
        if not access_token:
            return ChatToolResponse(error="Please connect your Twitter account first in the app settings.")

        twitter_user_id = get_user_id(uid)
        if not twitter_user_id:
            return ChatToolResponse(error="Could not get your Twitter user ID.")

        result = twitter_api_request(uid, "GET", f"/users/{twitter_user_id}/mentions", params={
            "max_results": max_results,
            "tweet.fields": "created_at,public_metrics,author_id",
            "expansions": "author_id",
            "user.fields": "name,username"
        })

        if not result or "error" in result:
            return ChatToolResponse(error=f"Failed to get mentions: {result.get('error', 'Unknown error')}")

        tweets = result.get("data", [])
        includes = result.get("includes", {})

        if not tweets:
            return ChatToolResponse(result="No mentions found.")

        result_parts = [f"**Your Mentions ({len(tweets)})**", ""]

        for tweet in tweets:
            result_parts.append(format_tweet(tweet, includes))
            result_parts.append("")
            result_parts.append("---")
            result_parts.append("")

        return ChatToolResponse(result="\n".join(result_parts))

    except Exception as e:
        log(f"Error getting mentions: {e}")
        return ChatToolResponse(error=f"Failed to get mentions: {str(e)}")


@app.post("/tools/search_tweets", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_search_tweets(request: Request):
    """Search for tweets."""
    try:
        body = await request.json()
        uid = body.get("uid")
        query = body.get("query")
        max_results = min(body.get("max_results", 10), 100)

        if not uid:
            return ChatToolResponse(error="User ID is required")

        if not query:
            return ChatToolResponse(error="Search query is required")

        access_token = get_valid_access_token(uid)
        if not access_token:
            return ChatToolResponse(error="Please connect your Twitter account first in the app settings.")

        result = twitter_api_request(uid, "GET", "/tweets/search/recent", params={
            "query": query,
            "max_results": max_results,
            "tweet.fields": "created_at,public_metrics,author_id",
            "expansions": "author_id",
            "user.fields": "name,username"
        })

        if not result or "error" in result:
            return ChatToolResponse(error=f"Search failed: {result.get('error', 'Unknown error')}")

        tweets = result.get("data", [])
        includes = result.get("includes", {})

        if not tweets:
            return ChatToolResponse(result=f"No tweets found for '{query}'.")

        result_parts = [f"**Search Results for '{query}' ({len(tweets)} tweets)**", ""]

        for tweet in tweets:
            result_parts.append(format_tweet(tweet, includes))
            result_parts.append("")
            result_parts.append("---")
            result_parts.append("")

        return ChatToolResponse(result="\n".join(result_parts))

    except Exception as e:
        log(f"Error searching tweets: {e}")
        return ChatToolResponse(error=f"Search failed: {str(e)}")


@app.post("/tools/like_tweet", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_like_tweet(request: Request):
    """Like a tweet."""
    try:
        body = await request.json()
        uid = body.get("uid")
        tweet_id = body.get("tweet_id")

        if not uid:
            return ChatToolResponse(error="User ID is required")

        if not tweet_id:
            return ChatToolResponse(error="Tweet ID is required")

        access_token = get_valid_access_token(uid)
        if not access_token:
            return ChatToolResponse(error="Please connect your Twitter account first in the app settings.")

        twitter_user_id = get_user_id(uid)
        if not twitter_user_id:
            return ChatToolResponse(error="Could not get your Twitter user ID.")

        result = twitter_api_request(uid, "POST", f"/users/{twitter_user_id}/likes", json_data={
            "tweet_id": tweet_id
        })

        if not result or "error" in result:
            return ChatToolResponse(error=f"Failed to like tweet: {result.get('error', 'Unknown error')}")

        return ChatToolResponse(result=f"**Liked!**\n\nTweet ID: `{tweet_id}`")

    except Exception as e:
        log(f"Error liking tweet: {e}")
        return ChatToolResponse(error=f"Failed to like tweet: {str(e)}")


@app.post("/tools/unlike_tweet", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_unlike_tweet(request: Request):
    """Unlike a tweet."""
    try:
        body = await request.json()
        uid = body.get("uid")
        tweet_id = body.get("tweet_id")

        if not uid:
            return ChatToolResponse(error="User ID is required")

        if not tweet_id:
            return ChatToolResponse(error="Tweet ID is required")

        access_token = get_valid_access_token(uid)
        if not access_token:
            return ChatToolResponse(error="Please connect your Twitter account first in the app settings.")

        twitter_user_id = get_user_id(uid)
        if not twitter_user_id:
            return ChatToolResponse(error="Could not get your Twitter user ID.")

        result = twitter_api_request(uid, "DELETE", f"/users/{twitter_user_id}/likes/{tweet_id}")

        if result and "error" in result:
            return ChatToolResponse(error=f"Failed to unlike tweet: {result.get('error', 'Unknown error')}")

        return ChatToolResponse(result=f"**Unliked!**\n\nTweet ID: `{tweet_id}`")

    except Exception as e:
        log(f"Error unliking tweet: {e}")
        return ChatToolResponse(error=f"Failed to unlike tweet: {str(e)}")


@app.post("/tools/retweet", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_retweet(request: Request):
    """Retweet a tweet."""
    try:
        body = await request.json()
        uid = body.get("uid")
        tweet_id = body.get("tweet_id")

        if not uid:
            return ChatToolResponse(error="User ID is required")

        if not tweet_id:
            return ChatToolResponse(error="Tweet ID is required")

        access_token = get_valid_access_token(uid)
        if not access_token:
            return ChatToolResponse(error="Please connect your Twitter account first in the app settings.")

        twitter_user_id = get_user_id(uid)
        if not twitter_user_id:
            return ChatToolResponse(error="Could not get your Twitter user ID.")

        result = twitter_api_request(uid, "POST", f"/users/{twitter_user_id}/retweets", json_data={
            "tweet_id": tweet_id
        })

        if not result or "error" in result:
            return ChatToolResponse(error=f"Failed to retweet: {result.get('error', 'Unknown error')}")

        return ChatToolResponse(result=f"**Retweeted!**\n\nTweet ID: `{tweet_id}`")

    except Exception as e:
        log(f"Error retweeting: {e}")
        return ChatToolResponse(error=f"Failed to retweet: {str(e)}")


@app.post("/tools/delete_tweet", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_delete_tweet(request: Request):
    """Delete a tweet."""
    try:
        body = await request.json()
        uid = body.get("uid")
        tweet_id = body.get("tweet_id")

        if not uid:
            return ChatToolResponse(error="User ID is required")

        if not tweet_id:
            return ChatToolResponse(error="Tweet ID is required")

        access_token = get_valid_access_token(uid)
        if not access_token:
            return ChatToolResponse(error="Please connect your Twitter account first in the app settings.")

        result = twitter_api_request(uid, "DELETE", f"/tweets/{tweet_id}")

        if result and "error" in result:
            return ChatToolResponse(error=f"Failed to delete tweet: {result.get('error', 'Unknown error')}")

        return ChatToolResponse(result=f"**Tweet Deleted!**\n\nTweet ID: `{tweet_id}`")

    except Exception as e:
        log(f"Error deleting tweet: {e}")
        return ChatToolResponse(error=f"Failed to delete tweet: {str(e)}")


@app.post("/tools/get_user_profile", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_get_user_profile(request: Request):
    """Get a user's profile."""
    try:
        body = await request.json()
        uid = body.get("uid")
        username = body.get("username")

        if not uid:
            return ChatToolResponse(error="User ID is required")

        access_token = get_valid_access_token(uid)
        if not access_token:
            return ChatToolResponse(error="Please connect your Twitter account first in the app settings.")

        if username:
            # Look up by username
            result = twitter_api_request(uid, "GET", f"/users/by/username/{username}", params={
                "user.fields": "description,public_metrics,created_at,profile_image_url,verified"
            })
        else:
            # Get authenticated user's profile
            result = twitter_api_request(uid, "GET", "/users/me", params={
                "user.fields": "description,public_metrics,created_at,profile_image_url,verified"
            })

        if not result or "error" in result:
            return ChatToolResponse(error=f"Failed to get profile: {result.get('error', 'Unknown error')}")

        user = result.get("data", {})
        name = user.get("name", "Unknown")
        handle = user.get("username", "")
        bio = user.get("description", "")
        verified = user.get("verified", False)
        metrics = user.get("public_metrics", {})
        created = user.get("created_at", "")[:10]

        followers = metrics.get("followers_count", 0)
        following = metrics.get("following_count", 0)
        tweets = metrics.get("tweet_count", 0)

        result_parts = [
            f"**{name}** {'(Verified)' if verified else ''}",
            f"@{handle}",
            ""
        ]

        if bio:
            result_parts.append(bio)
            result_parts.append("")

        result_parts.append(f"**Followers:** {followers:,}")
        result_parts.append(f"**Following:** {following:,}")
        result_parts.append(f"**Tweets:** {tweets:,}")

        if created:
            result_parts.append(f"**Joined:** {created}")

        result_parts.append(f"\nProfile: https://twitter.com/{handle}")

        return ChatToolResponse(result="\n".join(result_parts))

    except Exception as e:
        log(f"Error getting profile: {e}")
        return ChatToolResponse(error=f"Failed to get profile: {str(e)}")


# ============================================
# OAuth & Setup Endpoints
# ============================================

@app.get("/")
async def root(uid: str = Query(None)):
    """Root endpoint - Homepage."""
    if not uid:
        return {
            "app": "Twitter Omi Integration",
            "version": "1.0.0",
            "status": "active",
            "endpoints": {
                "auth": "/auth/twitter?uid=<user_id>",
                "setup_check": "/setup/twitter?uid=<user_id>",
                "tools_manifest": "/.well-known/omi-tools.json"
            }
        }

    tokens = get_twitter_tokens(uid)

    if not tokens:
        auth_url = f"/auth/twitter?uid={uid}"
        return HTMLResponse(content=f"""
        <html>
            <head>
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <title>Twitter - Connect</title>
                <style>{get_css()}</style>
            </head>
            <body>
                <div class="container">
                    <div class="icon">𝕏</div>
                    <h1>Twitter / X</h1>
                    <p>Post tweets and manage your timeline through Omi chat</p>

                    <a href="{auth_url}" class="btn btn-primary btn-block">
                        Connect Twitter
                    </a>

                    <div class="card">
                        <h3>What You Can Do</h3>
                        <ul>
                            <li><strong>Post Tweets</strong> - Share updates with your followers</li>
                            <li><strong>View Timeline</strong> - See what's happening</li>
                            <li><strong>Search</strong> - Find tweets about any topic</li>
                            <li><strong>Engage</strong> - Like, retweet, and reply</li>
                        </ul>
                    </div>

                    <div class="card">
                        <h3>Example Commands</h3>
                        <div class="example">"Tweet: Just tried the new AI assistant!"</div>
                        <div class="example">"Show my Twitter timeline"</div>
                        <div class="example">"Search Twitter for AI news"</div>
                    </div>

                    <div class="footer">Powered by <strong>Omi</strong></div>
                </div>
            </body>
        </html>
        """)

    # User is connected
    username = tokens.get("username", "Unknown")

    return HTMLResponse(content=f"""
    <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>Twitter - Connected</title>
            <style>{get_css()}</style>
        </head>
        <body>
            <div class="container">
                <div class="success-box">
                    <div class="icon" style="font-size: 48px;">✓</div>
                    <h2>Twitter Connected</h2>
                    <p>Connected as @{username}</p>
                </div>

                <div class="card">
                    <h3>Try These Commands</h3>
                    <div class="example">"Post a tweet: Hello from Omi!"</div>
                    <div class="example">"Show my recent tweets"</div>
                    <div class="example">"Who mentioned me on Twitter?"</div>
                </div>

                <a href="/disconnect?uid={uid}" class="btn btn-secondary btn-block">
                    Disconnect Twitter
                </a>

                <div class="footer">Powered by <strong>Omi</strong></div>
            </div>
        </body>
    </html>
    """)


@app.get("/auth/twitter")
async def twitter_auth(uid: str = Query(...)):
    """Start Twitter OAuth2 flow with PKCE."""
    if not TWITTER_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Twitter OAuth credentials not configured")

    # Generate PKCE code verifier and challenge
    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)

    state = f"{uid}:{secrets.token_urlsafe(32)}"
    store_oauth_state(uid, state)
    store_user_setting(uid, "code_verifier", code_verifier)

    params = {
        "response_type": "code",
        "client_id": TWITTER_CLIENT_ID,
        "redirect_uri": TWITTER_REDIRECT_URI,
        "scope": " ".join(TWITTER_SCOPES),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256"
    }

    auth_url = f"{TWITTER_AUTH_URL}?{urlencode(params)}"
    return RedirectResponse(url=auth_url)


@app.get("/auth/twitter/callback")
async def twitter_callback(
    code: str = Query(None),
    state: str = Query(None),
    error: str = Query(None)
):
    """Handle Twitter OAuth2 callback."""
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

    # Get code verifier
    code_verifier = get_user_setting(uid, "code_verifier")
    if not code_verifier:
        return HTMLResponse(content="Code verifier not found", status_code=400)

    delete_oauth_state(uid)

    # Exchange code for tokens
    try:
        token_data = {
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": TWITTER_REDIRECT_URI,
            "code_verifier": code_verifier
        }

        if TWITTER_CLIENT_SECRET:
            # Confidential client
            response = requests.post(
                TWITTER_TOKEN_URL,
                data=token_data,
                auth=(TWITTER_CLIENT_ID, TWITTER_CLIENT_SECRET)
            )
        else:
            # Public client
            token_data["client_id"] = TWITTER_CLIENT_ID
            response = requests.post(
                TWITTER_TOKEN_URL,
                data=token_data
            )

        if response.status_code != 200:
            log(f"Token exchange failed: {response.text}")
            return HTMLResponse(content=f"Token exchange failed: {response.text}", status_code=400)

        token_response = response.json()
        access_token = token_response.get("access_token")
        refresh_token = token_response.get("refresh_token", "")
        expires_in = token_response.get("expires_in", 7200)

        if not access_token:
            return HTMLResponse(content="No access token received", status_code=400)

        expires_at = (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat() + "Z"

        # Get user info
        headers = {"Authorization": f"Bearer {access_token}"}
        user_response = requests.get(
            f"{TWITTER_API_BASE}/users/me",
            headers=headers,
            params={"user.fields": "username"}
        )

        username = ""
        twitter_user_id = ""
        if user_response.status_code == 200:
            user_data = user_response.json().get("data", {})
            username = user_data.get("username", "")
            twitter_user_id = user_data.get("id", "")

        store_twitter_tokens(uid, access_token, refresh_token, expires_at, username, twitter_user_id)

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
                        <p>Your Twitter account @{username} is now linked to Omi</p>
                    </div>

                    <a href="/?uid={uid}" class="btn btn-primary btn-block">
                        Continue to Settings
                    </a>

                    <div class="card">
                        <h3>Ready to Go!</h3>
                        <p>You can now manage Twitter by chatting with Omi.</p>
                        <p>Try: <strong>"Show my Twitter timeline"</strong></p>
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


@app.get("/setup/twitter")
async def check_setup(uid: str = Query(...)):
    """Check if user has completed Twitter setup."""
    tokens = get_twitter_tokens(uid)
    return {"is_setup_completed": tokens is not None}


@app.get("/disconnect")
async def disconnect(uid: str = Query(...)):
    """Disconnect Twitter."""
    delete_twitter_tokens(uid)
    return RedirectResponse(url=f"/?uid={uid}")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "twitter-omi"}


# ============================================
# CSS Styles
# ============================================

def get_css() -> str:
    """Returns Twitter/X-inspired dark theme CSS."""
    return """
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #000;
            color: #e7e9ea;
            min-height: 100vh;
            padding: 20px;
            line-height: 1.6;
        }
        .container { max-width: 600px; margin: 0 auto; }
        .icon { font-size: 64px; text-align: center; margin-bottom: 20px; }
        h1 { color: #fff; font-size: 28px; text-align: center; margin-bottom: 8px; }
        h2 { color: #fff; font-size: 22px; margin-bottom: 12px; }
        h3 { color: #fff; font-size: 18px; margin-bottom: 12px; }
        p { color: #71767b; text-align: center; margin-bottom: 24px; }
        .card {
            background: #16181c;
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 16px;
            border: 1px solid #2f3336;
        }
        .btn {
            display: inline-block;
            padding: 14px 24px;
            border-radius: 9999px;
            text-decoration: none;
            font-weight: 700;
            font-size: 16px;
            border: none;
            cursor: pointer;
            text-align: center;
            transition: all 0.2s;
        }
        .btn-primary {
            background: #1d9bf0;
            color: #fff;
        }
        .btn-primary:hover { background: #1a8cd8; }
        .btn-secondary {
            background: transparent;
            color: #1d9bf0;
            border: 1px solid #536471;
        }
        .btn-secondary:hover { background: rgba(29, 155, 240, 0.1); }
        .btn-block { display: block; width: 100%; margin: 12px 0; }
        .success-box {
            background: rgba(0, 186, 124, 0.1);
            border: 1px solid #00ba7c;
            border-radius: 16px;
            padding: 32px;
            text-align: center;
            margin-bottom: 24px;
        }
        .success-box h2 { color: #00ba7c; }
        .error-box {
            background: rgba(244, 33, 46, 0.1);
            border: 1px solid #f4212e;
            border-radius: 16px;
            padding: 32px;
            text-align: center;
        }
        .error-box h2 { color: #f4212e; }
        ul { list-style: none; padding: 0; }
        li { padding: 10px 0; border-bottom: 1px solid #2f3336; }
        li:last-child { border-bottom: none; }
        .example {
            background: #000;
            padding: 12px 16px;
            border-radius: 8px;
            margin: 8px 0;
            font-style: italic;
            color: #71767b;
            border: 1px solid #2f3336;
        }
        .footer {
            text-align: center;
            color: #71767b;
            margin-top: 40px;
            padding: 20px;
            font-size: 14px;
        }
        .footer strong { color: #1d9bf0; }
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

    print("Twitter Omi Integration")
    print("=" * 50)
    print(f"Starting on {host}:{port}")
    print("=" * 50)

    uvicorn.run("main:app", host=host, port=port, reload=True)
