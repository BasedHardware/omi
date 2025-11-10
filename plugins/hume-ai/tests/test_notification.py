#!/usr/bin/env python3
"""
Test Omi notification sending directly
"""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

async def test_notification():
    """Test sending a notification to Omi"""
    import httpx
    from urllib.parse import quote

    omi_app_id = os.getenv('OMI_APP_ID')
    omi_api_key = os.getenv('OMI_API_KEY')

    print(f"OMI_APP_ID: {omi_app_id}")
    print(f"OMI_API_KEY: {'*' * 20}{omi_api_key[-8:] if omi_api_key else 'NOT SET'}")

    if not omi_app_id or not omi_api_key:
        print("❌ Error: OMI_APP_ID or OMI_API_KEY not set in .env")
        return

    # You need to replace this with YOUR user ID
    # You can find it in the server logs when you send audio from Omi device
    test_uid = input("\nEnter your Omi user ID (uid from audio requests): ").strip()

    if not test_uid:
        print("❌ No UID provided. Please check server logs for the uid parameter.")
        return

    message = "🎭 Test Notification: If you see this, notifications are working!"

    print(f"\n📤 Sending test notification to user: {test_uid}")
    print(f"   Message: {message}")

    try:
        url = f"https://api.omi.me/v2/integrations/{omi_app_id}/notification?uid={quote(test_uid)}&message={quote(message)}"
        headers = {
            "Authorization": f"Bearer {omi_api_key}",
            "Content-Type": "application/json",
            "Content-Length": "0"
        }

        print(f"\n🔗 API URL: {url[:80]}...")

        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, timeout=30.0)

        print(f"\n📥 Response Status: {response.status_code}")
        print(f"📥 Response Body: {response.text}")

        if response.status_code >= 200 and response.status_code < 300:
            print("\n✅ SUCCESS! Notification sent to Omi!")
            print("   Check your Omi mobile app for the notification.")
        else:
            print(f"\n❌ FAILED! Status code: {response.status_code}")
            print(f"   Error: {response.text}")

            if response.status_code == 401:
                print("\n   → Check: Is your OMI_API_KEY correct?")
            elif response.status_code == 403:
                print("\n   → Check: Did the user enable your app in Omi mobile app?")
            elif response.status_code == 404:
                print("\n   → Check: Is the UID correct?")

    except Exception as e:
        print(f"\n❌ Exception occurred: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("=" * 60)
    print("Omi Notification Test Script")
    print("=" * 60)
    asyncio.run(test_notification())
