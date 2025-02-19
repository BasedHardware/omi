import os
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import httpx
from fastapi import HTTPException
from ulid import ULID

from database.apps import update_app_in_db, add_app_to_db, get_persona_by_uid_db, get_persona_by_id_db
from database.redis_db import delete_generic_cache
from utils.llm import condense_tweets, generate_twitter_persona_prompt

rapid_api_host = os.getenv('RAPID_API_HOST')
rapid_api_key = os.getenv('RAPID_API_KEY')


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


async def create_persona_from_twitter_profile(username: str, uid: str) -> Dict[str, Any]:
    profile = await get_twitter_profile(username)
    profile['avatar'] = profile['avatar'].replace('_normal', '')
    persona = {
        "name": profile["name"],
        "author": profile['name'],
        "uid": uid,
        "id": str(ULID()),
        "deleted": False,
        "status": "approved",
        "capabilities": ["persona"],
        "username": profile["profile"],
        "connected_accounts": ["twitter"],
        "description": profile["desc"],
        "image": profile["avatar"],
        "category": "personality-emulation",
        "approved": True,
        "private": False,
        "created_at": datetime.now(timezone.utc),
        "twitter": {
            "username": profile["profile"],
            "avatar": profile["avatar"],
        }
    }
    tweets = await get_twitter_timeline(username)
    tweets = [{'tweet': tweet['text'], 'posted_at': tweet['created_at']} for tweet in tweets['timeline']]
    condensed_tweets = condense_tweets(tweets, profile["name"])
    persona['persona_prompt'] = generate_twitter_persona_prompt(condensed_tweets, profile["name"])
    add_app_to_db(persona)
    delete_generic_cache('get_public_approved_apps_data')
    return persona


async def add_twitter_to_persona(username: str, persona_id) -> Dict[str, Any]:
    persona = get_persona_by_id_db(persona_id)
    twitter = await get_twitter_profile(username)
    twitter['avatar'] = twitter['avatar'].replace('_normal', '')
    persona['connected_accounts'].append('twitter')
    persona['twitter'] = {
        "username": twitter["profile"],
        "avatar": twitter["avatar"],
        "connected_at": datetime.now(timezone.utc)
    }
    update_app_in_db(persona)
    delete_generic_cache('get_public_approved_apps_data')
    return persona