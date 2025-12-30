Smoke test: share/revoke speech profile

Purpose
- Quick verification that share and revoke endpoints work and that Redis pubsub notifications are emitted.

Prerequisites
- A staging backend accessible via environment variable API_BASE.
- User A (sharer) and user B (recipient) tokens (`A_TOKEN`, `B_TOKEN`) and the UID of user B (`B_UID`).
- (Optional) Redis connection if you want to observe pubsub events.
 - `aioredis` must be available in the runtime for `/v4/listen` sessions to subscribe to pubsub (add to requirements if needed).
 - Note: share payload now includes `speaker_embedding` so listeners can update caches without a DB roundtrip.

How to run

Set environment variables (example):

```bash
export API_BASE=https://staging-api.example.com
export A_TOKEN=<A bearer token>
export B_TOKEN=<B bearer token>
export B_UID=<uid of B>
export SOURCE_PERSON_ID=<optional person id owned by A>
# optional: redis info
export REDIS_HOST=redis.example.com
export REDIS_PORT=6379
export REDIS_PASSWORD=<password if needed>

python3 backend/scripts/smoke_shared_profile_test.py
```

Expected
- The share endpoint returns status 200 and the response body `{"status":"ok"}`.
- If Redis is reachable, a pubsub message should be observed on `users:{B_UID}:shared_profiles` with action `add`.
- The subsequent GET /v3/speech-profile/shared as B shows the shared doc.
- After revoke, GET /v3/speech-profile/shared does not include the shared doc and a `remove` event is published.

Notes
- This test does not exercise the `/v4/listen` real-time matching, which requires streaming audio and a running STT/embedding stack. Use a separate test to stream audio and confirm `SpeakerLabelSuggestionEvent` arrives in a live session.
