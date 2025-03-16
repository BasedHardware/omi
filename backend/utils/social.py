import os
import time
from datetime import datetime, timezone
from typing import Dict, Any, Callable, TypeVar
import httpx
from ulid import ULID

from database.apps import update_app_in_db, upsert_app_to_db, get_persona_by_id_db, get_persona_by_username_twitter_handle_db
from database.redis_db import delete_generic_cache, save_username, is_username_taken
from utils.llm import condense_tweets, generate_twitter_persona_prompt

rapid_api_host = os.getenv('RAPID_API_HOST')
rapid_api_key = os.getenv('RAPID_API_KEY')

defaultTimeoutSec = 15

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

async def get_twitter_profile(handle: str) -> Dict[str, Any]:
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
            return data
        # else
        response.raise_for_status()

    return with_retry(f"fetching Twitter profile for {handle}", fetch_profile)

async def get_twitter_timeline(handle: str) -> Dict[str, Any]:
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
            return data
        # else
        response.raise_for_status()

    return with_retry(f"fetching Twitter timeline for {handle}", fetch_timeline)

async def verify_latest_tweet(username: str, handle: str) -> Dict[str, Any]:
    print(f"Fetching latest tweet for {handle}, username {username}...")
    url = f"https://{rapid_api_host}/timeline.php?screenname={handle}"

    headers = {
        "X-RapidAPI-Key": rapid_api_key,
        "X-RapidAPI-Host": rapid_api_host
    }

    def verify_tweet():
        response = httpx.get(url, headers=headers, timeout=defaultTimeoutSec)
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'error':
                raise Exception(f"API returned error status: {data.get('message', 'Unknown error')}")
            # from the timeline, the first tweet is the latest
            latest_tweet = None
            timeline = data.get('timeline', [])
            if len(timeline) > 0:
                latest_tweet = timeline[0]
                if f'Verifying my clone({username})' in latest_tweet['text']:
                    return {"tweet": latest_tweet['text'], 'verified': True}

            return {"tweet": latest_tweet['text'] if latest_tweet else "", 'verified': False}

        # else
        response.raise_for_status()

    return with_retry(f"verifying latest tweet for {handle}", verify_tweet)


async def upsert_persona_from_twitter_profile(username: str, handle: str, uid: str) -> Dict[str, Any]:
    profile = await get_twitter_profile(handle)
    profile['avatar'] = (profile.get('avatar') or '').replace('_normal', '')
    persona = get_persona_by_username_twitter_handle_db(username, handle)

    if not persona:
        persona = {
            "name": profile["name"],
            "author": profile['name'],
            "uid": uid,
            "id": str(ULID()),
            "deleted": False,
            "status": "approved",
            "capabilities": ["persona"],
            "username": username,
            "connected_accounts": ["twitter"],
            "description": profile["desc"],
            "image": profile["avatar"],
            "category": "personality-emulation",
            "approved": True,
            "private": False,
            "created_at": datetime.now(timezone.utc),
        }

    # update profle
    persona["twitter"] = {
        "username": handle,
        "avatar": profile["avatar"],
        "connected_at": datetime.now(timezone.utc)
    }

    # publish automatically
    persona["status"] = "approved"
    persona["approved"] = True
    persona["private"] = False

    tweets = await get_twitter_timeline(handle)
    tweets = [{'tweet': tweet['text'], 'posted_at': tweet['created_at']} for tweet in tweets['timeline']]
    persona['persona_prompt'] = generate_twitter_persona_prompt(tweets, persona["name"])
    upsert_app_to_db(persona)
    save_username(persona['username'], uid)
    delete_generic_cache('get_public_approved_apps_data')
    return persona


async def add_twitter_to_persona(handle: str, persona_id) -> Dict[str, Any]:
    persona = get_persona_by_id_db(persona_id)
    twitter = await get_twitter_profile(handle)
    twitter['avatar'] = (twitter.get('avatar') or '').replace('_normal', '')
    if 'twitter' not in persona['connected_accounts']:
        persona['connected_accounts'].append('twitter')
    persona['twitter'] = {
        "username": handle,
        "avatar": twitter["avatar"],
        "connected_at": datetime.now(timezone.utc)
    }
    update_app_in_db(persona)
    delete_generic_cache('get_public_approved_apps_data')
    return persona
