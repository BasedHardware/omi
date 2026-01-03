"""
Smoke test for sharing/revoking speech profiles.

Run this from a machine with network access to your staging backend and Redis.
It performs:
 1) POST /v3/speech-profile/share as user A to share a person with user B
 2) GET /v3/speech-profile/shared as user B to verify the doc exists
 3) (optional) subscribe to Redis channel users:{B}:shared_profiles to observe live pubsub
 4) POST /v3/speech-profile/revoke as user A to revoke
 5) GET /v3/speech-profile/shared as user B to verify removal

Environment variables required:
 - API_BASE (e.g. https://staging-api.omi.me)
 - A_TOKEN (Bearer token for sharing user A)
 - B_TOKEN (Bearer token for target user B)
 - B_UID (uid of target user B)
 - SOURCE_PERSON_ID (optional person id owned by user A to share)
 - REDIS_HOST, REDIS_PORT, REDIS_PASSWORD (optional, for listening to pubsub)

This script does not create persons or embeddings. Ensure user A has a person with a stored speaker_embedding if you want matching to work.
"""

import os
import time
import json
import requests

API_BASE = os.getenv('API_BASE')
A_TOKEN = os.getenv('A_TOKEN')
B_TOKEN = os.getenv('B_TOKEN')
B_UID = os.getenv('B_UID')
SOURCE_PERSON_ID = os.getenv('SOURCE_PERSON_ID')

if not API_BASE or not A_TOKEN or not B_TOKEN or not B_UID:
    print('Missing required environment variables. See header of this script for details.')
    exit(1)

headers_a = {'Authorization': f'Bearer {A_TOKEN}'}
headers_b = {'Authorization': f'Bearer {B_TOKEN}'}

print('1) Share profile from A -> B')
params = {'target_uid': B_UID}
if SOURCE_PERSON_ID:
    params['source_person_id'] = SOURCE_PERSON_ID

resp = requests.post(f'{API_BASE}/v3/speech-profile/share', headers=headers_a, params=params)
print('share status:', resp.status_code, resp.text)

# optionally listen for Redis pubsub message
REDIS_HOST = os.getenv('REDIS_HOST')
REDIS_PORT = int(os.getenv('REDIS_PORT') or 6379)
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD')

if REDIS_HOST:
    try:
        import redis
        print('Connecting to Redis to subscribe to pubsub channel...')
        r = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD, decode_responses=True)
        p = r.pubsub()
        channel = f'users:{B_UID}:shared_profiles'
        p.subscribe(channel)
        print('Subscribed to', channel, '- waiting up to 5 seconds for a message...')
        msg = None
        start = time.time()
        while time.time() - start < 5:
            m = p.get_message()
            if m and m.get('type') == 'message':
                msg = m['data']
                break
            time.sleep(0.2)
        print('pubsub message:', msg)
    except Exception as e:
        print('Redis listen failed:', str(e))
else:
    print('REDIS_HOST not set; skipping pubsub listening')

print('\n2) As B, list shared profiles')
resp = requests.get(f'{API_BASE}/v3/speech-profile/shared', headers=headers_b)
print('list-shared status:', resp.status_code, resp.text)

print('\n3) Revoke from A -> B')
params = {'target_uid': B_UID}
resp = requests.post(f'{API_BASE}/v3/speech-profile/revoke', headers=headers_a, params=params)
print('revoke status:', resp.status_code, resp.text)

print('\n4) As B, list shared profiles (post-revoke)')
resp = requests.get(f'{API_BASE}/v3/speech-profile/shared', headers=headers_b)
print('list-shared (after revoke) status:', resp.status_code, resp.text)

print('\nSmoke test finished.')
