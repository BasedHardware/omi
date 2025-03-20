import os
import time
from datetime import datetime, timezone
from typing import Dict, Any, Callable, TypeVar, List, Optional, Tuple
import httpx
from pydantic import BaseModel
from ulid import ULID

from database.apps import update_app_in_db, upsert_app_to_db, get_persona_by_id_db, get_persona_by_username_twitter_handle_db
from database.facts import create_fact
from database.redis_db import delete_generic_cache, save_username, is_username_taken
from utils.llm import condense_tweets, generate_twitter_persona_prompt
from utils.memories.facts import process_twitter_facts
rapid_api_host = os.getenv('RAPID_API_HOST')
rapid_api_key = os.getenv('RAPID_API_KEY')

defaultTimeoutSec = 15

class TwitterTweet(BaseModel):
    text: str
    created_at: str
    id: str

class TwitterTimeline(BaseModel):
    timeline: List[TwitterTweet]

class TwitterProfile(BaseModel):
    name: str
    profile: str  # Twitter handle
    rest_id: str
    avatar: str
    desc: str  # Bio description
    friends: int  # Following count
    sub_count: int  # Followers count
    id: str
    status: str = "error"  # Default status for successful profile fetch

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TwitterProfile":
        """Create a TwitterProfile instance from API response dictionary"""
        return cls(
            name=data.get("name", ""),
            profile=data.get("profile", ""),
            rest_id=data.get("rest_id", ""),
            avatar=(data.get("avatar") or "").replace("_normal", ""),  # Get full-size avatar
            desc=data.get("desc", ""),
            friends=data.get("friends", 0),
            sub_count=data.get("sub_count", 0),
            id=data.get("id", ""),
            status=data.get("status", "error")
        )


T = TypeVar('T')
def with_retry(operation_name: str, func: Callable[[], T]) -> T:
    max_retries = 5
    base_delay = 1

    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            delay = base_delay * (2 ** attempt)
            if attempt == max_retries - 1:
                raise
            print(f"Error in {operation_name} (attempt {attempt+1}/{max_retries}): {str(e)}")
            print(f"Retrying in {delay} seconds...")
            time.sleep(delay)
    raise Exception("Maximum retries exceeded")

async def get_twitter_profile(handle: str) -> TwitterProfile:
    """Fetch Twitter profile for a user and return structured data"""
    url = f"https://{rapid_api_host}/screenname.php?screenname={handle}"

    headers = {
        "X-RapidAPI-Key": rapid_api_key,
        "X-RapidAPI-Host": rapid_api_host
    }


    def fetch_profile():
        response = httpx.get(url, headers=headers, timeout=defaultTimeoutSec)
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'error':
                raise Exception(f"API returned error status: {data.get('message', 'Unknown error')}")

            # Ensure avatar URL is properly formatted (full size)
            if 'avatar' in data and data['avatar'] and '_normal' in data['avatar']:
                data['avatar'] = data['avatar'].replace('_normal', '')

            return TwitterProfile.from_dict(data)
        # else
        response.raise_for_status()

    return with_retry(f"fetching Twitter profile for {handle}", fetch_profile)

def create_facts_from_twitter_tweets(uid: str, persona_id: str, tweets: List[TwitterTweet]) -> None:
    """Create individual facts from tweets for more detailed persona information"""
    # Combine tweets into a single text for fact extraction
    combined_text = "\n".join([f"{tweet.text} (Posted: {tweet.created_at})" for tweet in tweets])

    # Process tweets and extract facts using the dedicated function
    process_twitter_facts(uid, combined_text, persona_id)

async def get_twitter_timeline(handle: str) -> TwitterTimeline:
    """Fetch Twitter timeline for a user and return structured data"""
    print(f"Fetching Twitter timeline for {handle}...")
    url = f"https://{rapid_api_host}/timeline.php?screenname={handle}"

    headers = {
        "X-RapidAPI-Key": rapid_api_key,
        "X-RapidAPI-Host": rapid_api_host
    }

    def fetch_timeline():
        response = httpx.get(url, headers=headers, timeout=defaultTimeoutSec)
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'error':
                raise Exception(f"API returned error status: {data.get('message', 'Unknown error')}")

            # Convert raw timeline to structured model
            timeline_data = data.get('timeline', [])
            tweets = [TwitterTweet(
                text=tweet['text'],
                created_at=tweet['created_at'],
                id=tweet['tweet_id']
            ) for tweet in timeline_data]

            return TwitterTimeline(timeline=tweets)
        # else
        response.raise_for_status()

    return with_retry(f"fetching Twitter timeline for {handle}", fetch_timeline)

async def verify_latest_tweet(username: str, handle: str) -> Dict[str, Any]:
    """Verify if the latest tweet contains verification text"""
    print(f"Fetching latest tweet for {handle}, username {username}...")

    # Get timeline
    timeline = await get_twitter_timeline(handle)

    # Check if there are any tweets
    if not timeline.timeline:
        return {"tweet": "", "verified": False}

    # Get the latest tweet (first in the timeline)
    latest_tweet = timeline.timeline[0]

    # Check if it contains verification text
    if f'Verifying my clone({username})' in latest_tweet.text:
        return {"tweet": latest_tweet.text, "verified": True}

    return {"tweet": latest_tweet.text, "verified": False}


async def upsert_persona_from_twitter_profile(username: str, handle: str, uid: str) -> Dict[str, Any]:
    """Create or update a persona based on Twitter profile and generate facts"""
    # Get Twitter profile data
    profile = await get_twitter_profile(handle)

    # Get tweets
    timeline = await get_twitter_timeline(handle)

    # Create or update persona
    persona = _create_or_update_persona(profile, username, uid, handle)

    # Generate persona prompt from tweets
    formatted_tweets = [{'tweet': tweet.text, 'posted_at': tweet.created_at} for tweet in timeline.timeline]
    persona_prompt = generate_twitter_persona_prompt(formatted_tweets, persona["name"])
    persona['persona_prompt'] = persona_prompt

    # Save persona to database
    upsert_app_to_db(persona)
    save_username(username, uid)
    delete_generic_cache('get_public_approved_apps_data')

    # Create facts from persona prompt and tweets
    create_facts_from_twitter_tweets(uid, persona['id'], timeline.timeline)

    return persona

def _create_or_update_persona(profile: TwitterProfile, username: str, uid: str, handle: str) -> Dict[str, Any]:
    """Create a new persona or update an existing one"""
    persona = get_persona_by_username_twitter_handle_db(username, handle)

    # Create new persona if it doesn't exist
    if not persona:
        persona = {
            "name": profile.name,
            "author": profile.name,
            "uid": uid,
            "id": str(ULID()),
            "deleted": False,
            "status": "approved",
            "capabilities": ["persona"],
            "username": username,
            "connected_accounts": ["twitter"],
            "description": profile.desc,
            "image": profile.avatar,
            "category": "personality-emulation",
            "approved": True,
            "private": False,
            "created_at": datetime.now(timezone.utc),
        }

    # Update persona with Twitter data
    persona["twitter"] = {
        "username": profile.profile,
        "avatar": profile.avatar,
        "connected_at": datetime.now(timezone.utc)
    }

    # Ensure persona is published
    persona["status"] = "approved"
    persona["approved"] = True
    persona["private"] = False

    return persona


async def add_twitter_to_persona(handle: str, persona_id) -> Dict[str, Any]:
    """Add Twitter account to an existing persona"""
    persona = get_persona_by_id_db(persona_id)
    profile = await get_twitter_profile(handle)

    if 'twitter' not in persona['connected_accounts']:
        persona['connected_accounts'].append('twitter')

    persona['twitter'] = {
        "username": profile.profile,
        "avatar": profile.avatar,
        "connected_at": datetime.now(timezone.utc)
    }

    update_app_in_db(persona)
    delete_generic_cache('get_public_approved_apps_data')

    # Get tweets from the Twitter timeline
    timeline = await get_twitter_timeline(handle)

    # Create facts from the tweets
    if timeline and timeline.timeline:
        create_facts_from_twitter_tweets(persona['uid'], persona_id, timeline.timeline)

    return persona
