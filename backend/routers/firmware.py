import os
import re
import httpx
from fastapi import APIRouter, HTTPException, Depends
from utils import auth


router = APIRouter()

@router.get("/latest-version")
async def get_latest_version():
    async with httpx.AsyncClient() as client:
        # TODO: Change this to the official repo
        url = "https://api.github.com/repos/basedhardware/Friend/releases/latest"
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Authorization": f"Bearer {os.getenv('GITHUB_TOKEN')}",
        }
        response = await client.get(url, headers=headers)
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="Failed to fetch latest release")

        release_data = response.json()
        kv = extract_key_value_pairs(release_data.get("body"))
        assets = release_data.get("assets")
        asset = None
        for asset in assets:
            if asset.get("content_type") == "application/zip":
                asset = asset
                break
        return {
            "version": kv.get("release_firmware_version"),
            "min_version": kv.get("minimum_firmware_required"),
            "min_app_version": kv.get("minimum_app_version"),
            "min_app_version_code": kv.get("minimum_app_version_code"),
            "id": release_data.get("id"),
            "tag_name": release_data.get("tag_name"),
            "published_at": release_data.get("published_at"),
            "draft": release_data.get("draft"),
            "prerelease": release_data.get("prerelease"),
            "zip_url": asset.get("browser_download_url"),
            "zip_name": asset.get("name"),
            "zip_size": asset.get("size"),
            "release_name": release_data.get("name"),
        }


def extract_key_value_pairs(markdown_content):
    key_value_pattern = re.compile(r'<!-- KEY_VALUE_START\s*(.*?)\s*KEY_VALUE_END -->', re.DOTALL)
    key_value_match = key_value_pattern.search(markdown_content)

    if not key_value_match:
        return {}

    key_value_string = key_value_match.group(1)
    lines = key_value_string.split('\n')
    key_value_map = {}

    for line in lines:
        key_value = line.split(':')
        if len(key_value) == 2:
            key = key_value[0].strip()
            value = key_value[1].strip()
            key_value_map[key] = value

    return key_value_map