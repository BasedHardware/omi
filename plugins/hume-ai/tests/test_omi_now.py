#!/usr/bin/env python3
"""Quick Omi notification test"""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

async def test_now():
    import httpx
    from urllib.parse import quote

    omi_app_id = os.getenv('OMI_APP_ID')
    omi_api_key = os.getenv('OMI_API_KEY')
    test_uid = "XqBKRatqZ5MS4tsX84VfBEne16W2"  # From your logs

    print(f"Testing notification to UID: {test_uid}")
    print(f"App ID: {omi_app_id}")

    message = "🎭 TEST: If you see this, notifications are working!"
    url = f"https://api.omi.me/v2/integrations/{omi_app_id}/notification?uid={quote(test_uid)}&message={quote(message)}"

    headers = {
        "Authorization": f"Bearer {omi_api_key}",
        "Content-Type": "application/json",
        "Content-Length": "0"
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, timeout=30.0)

    print(f"\nStatus: {response.status_code}")
    print(f"Response: {response.text}")

    if response.status_code == 200:
        print("\n✅ SUCCESS! Check your Omi app for the notification!")
    elif response.status_code == 403:
        print("\n❌ FORBIDDEN - User hasn't enabled your app in Omi mobile app")
    elif response.status_code == 401:
        print("\n❌ UNAUTHORIZED - API key is invalid")
    else:
        print(f"\n❌ ERROR {response.status_code}")

asyncio.run(test_now())
