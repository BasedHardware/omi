from datetime import datetime, timezone
from typing import Optional, Dict, Any
import httpx
from fastapi import HTTPException
from ulid import ULID

from database.apps import update_app_in_db
from database.redis_db import delete_generic_cache
from utils.llm import condense_tweets, generate_twitter_persona_prompt

rapid_api_host = ''
rapid_api_key = ''


async def get_twitter_profile(username: str) -> Dict[str, Any]:
    url = f"https://{rapid_api_host}/screenname.php?screenname={username}"

    headers = {
        "X-RapidAPI-Key": rapid_api_key,
        "X-RapidAPI-Host": rapid_api_host
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data


async def get_twitter_timeline(username: str) -> Dict[str, Any]:
    print(f"Fetching Twitter timeline for {username}...")
    url = f"https://{rapid_api_host}/timeline.php?screenname={username}"

    headers = {
        "X-RapidAPI-Key": rapid_api_key,
        "X-RapidAPI-Host": rapid_api_host
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data


async def get_latest_tweet(username: str) -> Dict[str, Any]:
    print(f"Fetching latest tweet for {username}...")
    url = f"https://{rapid_api_host}/timeline.php?screenname={username}"

    headers = {
        "X-RapidAPI-Key": rapid_api_key,
        "X-RapidAPI-Host": rapid_api_host
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        # from the timeline, the first tweet is the latest
        latest_tweet = data['timeline'][0]
        # check if latest_tweet['text'] contains the word "verifying my clone"
        if "Verifying my clone" in latest_tweet['text']:
            return {"tweet": latest_tweet['text'], 'verified': True}
        else:
            return {"tweet": latest_tweet['text'], 'verified': False}


async def create_persona_from_twitter_profile(username: str) -> Dict[str, Any]:
    profile = await get_twitter_profile(username)
    persona = {
        "name": profile["name"],
        "id": str(ULID()),
        "deleted": False,
        "archived": True,
        "status": "approved",
        "capabilities": ["persona"],
        "username": profile["profile"],
        "connected_accounts": ["twitter"],
        "description": profile["desc"],
        "image": profile["avatar"],
        "category": "personality-emulation",
        "created_at": datetime.now(timezone.utc),
    }
    tweets = get_twitter_timeline(username)
    condensed_tweets = condense_tweets(tweets, profile["name"])
    persona['persona_prompt'] = generate_twitter_persona_prompt(condensed_tweets, profile["name"])
    update_app_in_db(persona)
    delete_generic_cache('get_public_approved_apps_data')
    return persona
