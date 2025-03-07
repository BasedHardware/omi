import os
from datetime import datetime, timezone
from typing import Dict, Any
import httpx
from ulid import ULID

from database.apps import update_app_in_db, upsert_app_to_db, get_persona_by_id_db, get_persona_by_username_twitter_handle_db
from database.redis_db import delete_generic_cache, save_username, is_username_taken
from utils.llm import condense_tweets, generate_twitter_persona_prompt

rapid_api_host = os.getenv('RAPID_API_HOST')
rapid_api_key = os.getenv('RAPID_API_KEY')


async def get_twitter_profile(handle: str) -> Dict[str, Any]:
    url = f"https://{rapid_api_host}/screenname.php?screenname={handle}"

    headers = {
        "X-RapidAPI-Key": rapid_api_key,
        "X-RapidAPI-Host": rapid_api_host
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data


async def get_twitter_timeline(handle: str) -> Dict[str, Any]:
    print(f"Fetching Twitter timeline for {handle}...")
    url = f"https://{rapid_api_host}/timeline.php?screenname={handle}"

    headers = {
        "X-RapidAPI-Key": rapid_api_key,
        "X-RapidAPI-Host": rapid_api_host
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data


async def verify_latest_tweet(username: str, handle: str) -> Dict[str, Any]:
    print(f"Fetching latest tweet for {handle}, username {username}...")
    url = f"https://{rapid_api_host}/timeline.php?screenname={handle}"

    headers = {
        "X-RapidAPI-Key": rapid_api_key,
        "X-RapidAPI-Host": rapid_api_host
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        # from the timeline, the first tweet is the latest
        timeline = data.get('timeline', [])
        if len(timeline) > 0:
            latest_tweet = timeline[0]
            # check if latest_tweet['text'] contains the word "verifying my clone"
            if f'Verifying my clone({username})' in latest_tweet['text']:
                return {"tweet": latest_tweet['text'], 'verified': True}

        return {"tweet": latest_tweet['text'], 'verified': False}


async def upsert_persona_from_twitter_profile(username: str, handle: str, uid: str) -> Dict[str, Any]:
    profile = await get_twitter_profile(handle)
    profile['avatar'] = profile['avatar'].replace('_normal', '')
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
    twitter['avatar'] = twitter['avatar'].replace('_normal', '')
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
