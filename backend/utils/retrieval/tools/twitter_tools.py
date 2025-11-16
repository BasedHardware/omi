"""
Tools for accessing Twitter/X data.
"""

import os
import contextvars
from datetime import datetime, timezone
from typing import Optional

from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

import database.users as users_db
import requests

# Import the context variable from agentic module
try:
    from utils.retrieval.agentic import agent_config_context
except ImportError:
    # Fallback if import fails
    agent_config_context = contextvars.ContextVar('agent_config', default=None)


def get_twitter_user_id(access_token: str, username: Optional[str] = None) -> Optional[str]:
    """
    Get Twitter user ID from username or return authenticated user's ID.

    Args:
        access_token: Twitter access token
        username: Optional username (without @). If None, returns authenticated user's ID.

    Returns:
        User ID string or None if not found
    """
    if username:
        # Get user ID by username
        url = f'https://api.twitter.com/2/users/by/username/{username}'
    else:
        # Get authenticated user's info
        url = 'https://api.twitter.com/2/users/me'

    headers = {
        'Authorization': f'Bearer {access_token}',
    }

    try:
        response = requests.get(url, headers=headers, timeout=10.0)

        if response.status_code == 200:
            data = response.json()
            if 'data' in data:
                return data['data'].get('id')
        elif response.status_code == 404:
            return None
        else:
            error_body = response.text[:200] if response.text else "No error body"
            print(f"❌ Twitter User API error {response.status_code}: {error_body}")
            return None
    except Exception as e:
        print(f"❌ Error fetching Twitter user ID: {e}")
        return None


def get_twitter_tweets(
    access_token: str,
    user_id: Optional[str] = None,
    username: Optional[str] = None,
    max_results: int = 10,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
) -> dict:
    """
    Fetch tweets from Twitter API v2.

    Args:
        access_token: Twitter access token
        user_id: Optional user ID to fetch tweets for
        username: Optional username (without @) to fetch tweets for
        max_results: Maximum number of tweets to return (default: 10, max: 100)
        start_time: Optional start time in ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ)
        end_time: Optional end time in ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ)

    Returns:
        Dict with tweet data
    """
    # If username provided but not user_id, get user_id first
    if username and not user_id:
        user_id = get_twitter_user_id(access_token, username)
        if not user_id:
            raise Exception(f"User '{username}' not found on Twitter")

    # If no user_id provided, get authenticated user's tweets
    if not user_id:
        user_id = get_twitter_user_id(access_token)
        if not user_id:
            raise Exception("Could not get authenticated user's Twitter ID")

    url = f'https://api.twitter.com/2/users/{user_id}/tweets'

    headers = {
        'Authorization': f'Bearer {access_token}',
    }

    params = {
        'max_results': min(max_results, 100),  # Twitter API max is 100
        'tweet.fields': 'created_at,author_id,public_metrics,text',
        'expansions': 'author_id',
        'user.fields': 'username,name',
    }

    if start_time:
        params['start_time'] = start_time
    if end_time:
        params['end_time'] = end_time

    print(f"🐦 Calling Twitter Tweets API for user_id={user_id}, max_results={params['max_results']}")

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10.0)

        print(f"🐦 Twitter Tweets API response status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            return data
        elif response.status_code == 401:
            print(f"❌ Twitter Tweets API 401 - token expired or invalid")
            raise Exception("Authentication failed - token may be expired or invalid")
        else:
            error_body = response.text[:200] if response.text else "No error body"
            print(f"❌ Twitter Tweets API error {response.status_code}: {error_body}")
            raise Exception(f"Twitter Tweets API error: {response.status_code} - {error_body}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Network error fetching Twitter tweets: {e}")
        raise
    except Exception as e:
        print(f"❌ Error fetching Twitter tweets: {e}")
        raise


@tool
def get_twitter_tweets_tool(
    username: Optional[str] = None,
    max_results: int = 10,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    config: RunnableConfig = None,
) -> str:
    """
    Retrieve tweets from Twitter/X.

    Use this tool when:
    - User asks about their tweets or what they tweeted
    - User asks about someone else's tweets (e.g., "what did @username tweet?")
    - User wants to see recent tweets from a specific user
    - User asks "show me tweets" or "what are my tweets?"
    - **ALWAYS use this tool when the user asks about Twitter/X tweets**

    Args:
        username: Optional Twitter username (without @) to get tweets for. If not provided, returns authenticated user's tweets.
        max_results: Maximum number of tweets to return (default: 10, max: 100)
        start_time: Optional start time in ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ)
        end_time: Optional end time in ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ)

    Returns:
        Formatted list of tweets with author, text, timestamp, and engagement metrics.
    """
    print(f"🔧 get_twitter_tweets_tool called - username: {username}, max_results: {max_results}")

    # Get config from parameter or context variable
    if config is None:
        try:
            config = agent_config_context.get()
            if config:
                print(f"🔧 get_twitter_tweets_tool - got config from context variable")
        except LookupError:
            print(f"❌ get_twitter_tweets_tool - config not found in context variable")
            config = None

    if config is None:
        print(f"❌ get_twitter_tweets_tool - config is None")
        return "Error: Configuration not available"

    try:
        uid = config['configurable'].get('user_id')
    except (KeyError, TypeError) as e:
        print(f"❌ get_twitter_tweets_tool - error accessing config: {e}")
        return "Error: Configuration not available"

    if not uid:
        print(f"❌ get_twitter_tweets_tool - no user_id in config")
        return "Error: User ID not found in configuration"

    print(f"✅ get_twitter_tweets_tool - uid: {uid}, max_results: {max_results}")

    try:
        # Cap at 100 per call
        if max_results > 100:
            print(f"⚠️ get_twitter_tweets_tool - max_results capped from {max_results} to 100")
            max_results = 100

        # Check if user has Twitter connected
        print(f"🐦 Checking Twitter connection for user {uid}...")
        try:
            integration = users_db.get_integration(uid, 'twitter')
            print(f"🐦 Integration data retrieved: {integration is not None}")
            if integration:
                print(f"🐦 Integration connected status: {integration.get('connected')}")
                print(f"🐦 Integration has access_token: {bool(integration.get('access_token'))}")
            else:
                print(f"❌ No integration found for user {uid}")
                return "Twitter is not connected. Please connect your Twitter account from settings to view tweets."
        except Exception as e:
            print(f"❌ Error checking Twitter integration: {e}")
            import traceback

            traceback.print_exc()
            return f"Error checking Twitter connection: {str(e)}"

        if not integration or not integration.get('connected'):
            print(f"❌ Twitter not connected for user {uid}")
            return "Twitter is not connected. Please connect your Twitter account from settings to view tweets."

        access_token = integration.get('access_token')
        if not access_token:
            print(f"❌ No access token found in integration data")
            return "Twitter access token not found. Please reconnect your Twitter account from settings."

        print(f"✅ Access token found, length: {len(access_token)}")

        # Fetch tweets
        try:
            tweets_data = get_twitter_tweets(
                access_token=access_token,
                username=username,
                max_results=max_results,
                start_time=start_time,
                end_time=end_time,
            )

            print(f"✅ Successfully fetched Twitter tweets")
        except Exception as e:
            error_msg = str(e)
            print(f"❌ Error fetching Twitter tweets: {error_msg}")
            import traceback

            traceback.print_exc()
            return f"Error fetching tweets: {error_msg}"

        tweets = tweets_data.get('data', [])
        users = tweets_data.get('includes', {}).get('users', [])

        # Create user lookup map
        user_map = {user['id']: user for user in users}

        tweets_count = len(tweets) if tweets else 0
        print(f"📊 get_twitter_tweets_tool - found {tweets_count} tweets")

        if not tweets:
            username_info = f" for @{username}" if username else ""
            return f"No tweets found{username_info}."

        # Format tweets
        result = f"Twitter Tweets ({tweets_count} found):\n\n"

        for i, tweet in enumerate(tweets, 1):
            tweet_id = tweet.get('id', '')
            text = tweet.get('text', '')
            created_at = tweet.get('created_at', '')
            author_id = tweet.get('author_id', '')
            metrics = tweet.get('public_metrics', {})

            # Get author info
            author_name = "Unknown"
            author_username = "unknown"
            if author_id and author_id in user_map:
                author = user_map[author_id]
                author_name = author.get('name', 'Unknown')
                author_username = author.get('username', 'unknown')

            # Format timestamp
            try:
                if created_at:
                    dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    time_str = dt.strftime('%Y-%m-%d %H:%M:%S UTC')
                else:
                    time_str = "Unknown time"
            except Exception:
                time_str = created_at if created_at else "Unknown time"

            result += f"{i}. @{author_username} ({author_name})\n"
            result += f"   {text}\n"
            result += f"   Posted: {time_str}\n"

            # Add engagement metrics
            if metrics:
                likes = metrics.get('like_count', 0)
                retweets = metrics.get('retweet_count', 0)
                replies = metrics.get('reply_count', 0)
                if likes > 0 or retweets > 0 or replies > 0:
                    result += f"   Likes: {likes}, Retweets: {retweets}, Replies: {replies}\n"

            result += "\n"

        return result.strip()
    except Exception as e:
        print(f"❌ Unexpected error in get_twitter_tweets_tool: {e}")
        import traceback

        traceback.print_exc()
        return f"Unexpected error fetching tweets: {str(e)}"
