"""X (Twitter) connector: OAuth2 + incremental ingest with a RapidAPI fallback.

Design (see also database/x_posts.py):
  * Connect via the official X API using OAuth2 Authorization Code + PKCE. Tokens
    (incl. the offline.access refresh token) are stored server-side per user.
  * Sync pulls the user's recent tweets + bookmarks via X API v2, stores every
    post RAW under users/{uid}/x_posts, then runs Omi's memory extraction +
    Pinecone indexing over the new posts so they integrate with chat/RAG/persona.
  * If there is no usable token (not connected, refresh failed, or the API
    rate-limits / errors), we fall back to the existing RapidAPI handle-based
    timeline fetch for the user's PUBLIC tweets. Same downstream pipeline.

Required env (X developer app — confidential client):
  X_OAUTH_CLIENT_ID, X_OAUTH_CLIENT_SECRET, X_OAUTH_REDIRECT_URI
  (optional) X_OAUTH_SCOPES — defaults to the read scopes + offline.access.
"""

import asyncio
import base64
import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlencode

import httpx

from database import redis_db
from database import users as users_db
from database import x_posts as x_posts_db
from database import memories as memories_db
from database._client import db
from database.vector_db import upsert_memory_vectors_batch, upsert_x_post_vectors_batch
from models.memories import MemoryDB
from utils.llm.memories import extract_memories_from_text
from utils import social

logger = logging.getLogger(__name__)

INTEGRATION_KEY = 'x'  # users/{uid}/integrations/x

X_CLIENT_ID = os.getenv('X_OAUTH_CLIENT_ID')
X_CLIENT_SECRET = os.getenv('X_OAUTH_CLIENT_SECRET')
X_REDIRECT_URI = os.getenv('X_OAUTH_REDIRECT_URI')
X_SCOPES = os.getenv('X_OAUTH_SCOPES', 'tweet.read users.read bookmark.read like.read offline.access')

# Use x.com (not twitter.com): after X's domain migration the user's auth
# session cookies live on x.com, so the twitter.com authorize page shows a
# "you have to be logged in to X" loop even for logged-in users.
AUTHORIZE_URL = 'https://x.com/i/oauth2/authorize'
TOKEN_URL = 'https://api.x.com/2/oauth2/token'
API_BASE = 'https://api.x.com/2'

OAUTH_STATE_TTL = 600  # seconds
_STATE_PREFIX = 'x_oauth_state:'

# Lightweight registry of connected users so the periodic sync job can enumerate
# them without a collection-group query/index. Written on connect, removed on
# disconnect.
_REGISTRY_COLLECTION = 'x_connector_users'
SYNC_JOB_INTERVAL_HOURS = 6  # background sync cadence (the cron fires hourly)
_SYNC_JOB_USER_SPACING_SEC = 1.5  # gap between users to stay gentle on X limits

# Cap how much we pull per sync to stay well within X rate limits.
MAX_TWEET_PAGES = 4  # ~4 * 100 = up to 400 recent tweets per sync
MAX_BOOKMARK_PAGES = 2
MEMORY_BATCH_CHARS = 8000  # group post text into ~8k-char chunks for extraction


def is_oauth_configured() -> bool:
    return bool(X_CLIENT_ID and X_CLIENT_SECRET and X_REDIRECT_URI)


# ----------------------------------------------------------------------------
# OAuth2 + PKCE
# ----------------------------------------------------------------------------


def _gen_pkce() -> Tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b'=').decode('ascii')
    digest = hashlib.sha256(verifier.encode('ascii')).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b'=').decode('ascii')
    return verifier, challenge


def build_authorize_url(uid: str, success_redirect_url: Optional[str] = None) -> str:
    """Create the X authorize URL and stash the PKCE verifier + uid in Redis,
    keyed by the opaque `state` we hand to X."""
    if not is_oauth_configured():
        raise RuntimeError('X OAuth is not configured (missing X_OAUTH_CLIENT_ID/SECRET/REDIRECT_URI)')

    verifier, challenge = _gen_pkce()
    state = secrets.token_urlsafe(32)

    payload = {'uid': uid, 'verifier': verifier}
    if success_redirect_url:
        payload['success_redirect_url'] = success_redirect_url
    # store as a simple delimited string to avoid json import churn
    redis_db.r.setex(
        f'{_STATE_PREFIX}{state}',
        OAUTH_STATE_TTL,
        f"{uid}\n{verifier}\n{success_redirect_url or ''}",
    )

    params = {
        'response_type': 'code',
        'client_id': X_CLIENT_ID,
        'redirect_uri': X_REDIRECT_URI,
        'scope': X_SCOPES,
        'state': state,
        'code_challenge': challenge,
        'code_challenge_method': 'S256',
    }
    return f'{AUTHORIZE_URL}?{urlencode(params)}'


def consume_oauth_state(state: str) -> Optional[Dict[str, str]]:
    raw = redis_db.r.get(f'{_STATE_PREFIX}{state}')
    if not raw:
        return None
    redis_db.r.delete(f'{_STATE_PREFIX}{state}')
    if isinstance(raw, bytes):
        raw = raw.decode('utf-8')
    parts = raw.split('\n')
    if len(parts) < 2:
        return None
    return {
        'uid': parts[0],
        'verifier': parts[1],
        'success_redirect_url': parts[2] if len(parts) > 2 else '',
    }


def _basic_auth_header() -> Dict[str, str]:
    token = base64.b64encode(f'{X_CLIENT_ID}:{X_CLIENT_SECRET}'.encode()).decode()
    return {'Authorization': f'Basic {token}'}


async def exchange_code(code: str, verifier: str) -> Dict:
    logger.info(f'exchange_code: using redirect_uri={X_REDIRECT_URI!r} client_id={X_CLIENT_ID[:8]!r}…')
    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': X_REDIRECT_URI,
        'code_verifier': verifier,
        'client_id': X_CLIENT_ID,
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=3.0)) as client:
        resp = await client.post(TOKEN_URL, data=data, headers=_basic_auth_header())
        if resp.status_code >= 400:
            logger.error(f'exchange_code: X returned {resp.status_code}: {resp.text[:500]}')
        resp.raise_for_status()
        return resp.json()


async def _refresh(refresh_token: str) -> Dict:
    data = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
        'client_id': X_CLIENT_ID,
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=3.0)) as client:
        resp = await client.post(TOKEN_URL, data=data, headers=_basic_auth_header())
        resp.raise_for_status()
        return resp.json()


def _store_tokens(uid: str, token_resp: Dict, handle: Optional[str] = None, x_user_id: Optional[str] = None):
    expires_in = int(token_resp.get('expires_in', 7200))
    data = {
        'connected': True,
        'access_token': token_resp['access_token'],
        'expires_at': (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat(),
        'scope': token_resp.get('scope', X_SCOPES),
    }
    if token_resp.get('refresh_token'):
        data['refresh_token'] = token_resp['refresh_token']
    if handle:
        data['handle'] = handle
    if x_user_id:
        data['x_user_id'] = x_user_id
    users_db.set_integration(uid, INTEGRATION_KEY, data)
    _register_user(uid)


def _register_user(uid: str) -> None:
    try:
        db.collection(_REGISTRY_COLLECTION).document(uid).set(
            {'uid': uid, 'updated_at': datetime.now(timezone.utc)}, merge=True
        )
    except Exception as e:
        logger.warning(f'x_connector: failed to register user {uid} for sync: {e}')


def _unregister_user(uid: str) -> None:
    try:
        db.collection(_REGISTRY_COLLECTION).document(uid).delete()
    except Exception as e:
        logger.warning(f'x_connector: failed to unregister user {uid}: {e}')


async def get_valid_access_token(uid: str) -> Optional[str]:
    """Return a non-expired access token, refreshing if needed. None if not
    connected or refresh is impossible."""
    integ = users_db.get_integration(uid, INTEGRATION_KEY)
    if not integ or not integ.get('access_token'):
        return None
    try:
        expires_at = datetime.fromisoformat(integ['expires_at'])
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
    except Exception:
        expires_at = datetime.now(timezone.utc)

    if datetime.now(timezone.utc) < expires_at - timedelta(seconds=60):
        return integ['access_token']

    refresh = integ.get('refresh_token')
    if not refresh:
        return integ['access_token']  # best effort; may be expired
    try:
        token_resp = await _refresh(refresh)
        _store_tokens(uid, token_resp, handle=integ.get('handle'), x_user_id=integ.get('x_user_id'))
        return token_resp['access_token']
    except Exception as e:
        logger.warning(f'x_connector: token refresh failed for uid={uid}: {e}')
        return None


# ----------------------------------------------------------------------------
# X API v2 fetch
# ----------------------------------------------------------------------------


async def _api_get(token: str, path: str, params: Dict) -> Dict:
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=3.0)) as client:
        resp = await client.get(f'{API_BASE}{path}', params=params, headers={'Authorization': f'Bearer {token}'})
        resp.raise_for_status()
        return resp.json()


async def fetch_me(token: str) -> Dict:
    data = await _api_get(token, '/users/me', {})
    return data.get('data', {})


def _tweet_to_post(t: Dict, kind: str) -> Dict:
    return {
        'id': str(t.get('id')),
        'text': t.get('text', ''),
        'created_at': t.get('created_at', ''),
        'kind': kind,
        'lang': t.get('lang'),
        'metrics': t.get('public_metrics'),
    }


async def _fetch_paged(token: str, path: str, kind: str, max_pages: int, extra: Dict) -> List[Dict]:
    posts: List[Dict] = []
    params = {
        'max_results': 100,
        'tweet.fields': 'created_at,lang,public_metrics',
    }
    params.update(extra)
    pagination_token = None
    for _ in range(max_pages):
        if pagination_token:
            params['pagination_token'] = pagination_token
        data = await _api_get(token, path, params)
        for t in data.get('data', []) or []:
            posts.append(_tweet_to_post(t, kind))
        pagination_token = data.get('meta', {}).get('next_token')
        if not pagination_token:
            break
    return posts


async def fetch_tweets(token: str, x_user_id: str, since_id: Optional[str]) -> List[Dict]:
    extra = {'exclude': 'retweets'}
    if since_id:
        extra['since_id'] = since_id
    return await _fetch_paged(token, f'/users/{x_user_id}/tweets', x_posts_db.KIND_TWEET, MAX_TWEET_PAGES, extra)


async def fetch_bookmarks(token: str, x_user_id: str) -> List[Dict]:
    try:
        return await _fetch_paged(
            token, f'/users/{x_user_id}/bookmarks', x_posts_db.KIND_BOOKMARK, MAX_BOOKMARK_PAGES, {}
        )
    except Exception as e:
        logger.info(f'x_connector: bookmarks fetch skipped/failed: {e}')
        return []


# ----------------------------------------------------------------------------
# Memory extraction + indexing over new raw posts
# ----------------------------------------------------------------------------


def _extract_and_index(uid: str, posts: List[Dict]) -> int:
    """Run memory extraction over the given posts (grouped into chunks) and
    vector-index the resulting memories. Returns memories created."""
    if not posts:
        return 0

    chunks: List[str] = []
    buf: List[str] = []
    size = 0
    for p in posts:
        line = f"{p.get('text', '')} (Posted: {p.get('created_at', '')})"
        if size + len(line) > MEMORY_BATCH_CHARS and buf:
            chunks.append('\n'.join(buf))
            buf, size = [], 0
        buf.append(line)
        size += len(line)
    if buf:
        chunks.append('\n'.join(buf))

    total = 0
    for chunk in chunks:
        extracted = extract_memories_from_text(uid, chunk, 'twitter_tweets')
        if not extracted:
            continue
        memory_dbs: List[MemoryDB] = []
        for m in extracted:
            mdb = MemoryDB.from_memory(m, uid, None, False)
            mdb.manually_added = False
            # Tag with the connector key so X-derived memories are identifiable
            # (and cleanly removable on disconnect / re-import).
            mdb.app_id = INTEGRATION_KEY
            memory_dbs.append(mdb)
        memories_db.save_memories(uid, [m.dict() for m in memory_dbs])
        upsert_memory_vectors_batch(
            uid,
            [{'memory_id': m.id, 'content': m.content, 'category': m.category.value} for m in memory_dbs],
        )
        total += len(memory_dbs)
    return total


# ----------------------------------------------------------------------------
# Sync orchestrator (official API first, RapidAPI fallback)
# ----------------------------------------------------------------------------


async def sync_x_for_user(uid: str) -> Dict:
    """Pull new X posts, store raw, extract memories. Returns a summary dict."""
    integ = users_db.get_integration(uid, INTEGRATION_KEY) or {}
    # Mark syncing so the desktop can show live progress while this runs in the
    # background (the OAuth callback kicks this off as a background task).
    users_db.set_integration(uid, INTEGRATION_KEY, {'syncing': True})
    since_id = x_posts_db.get_newest_tweet_id(uid)

    new_posts: List[Dict] = []
    source = None
    token = await get_valid_access_token(uid)

    if token:
        try:
            x_user_id = integ.get('x_user_id')
            handle = integ.get('handle')
            if not x_user_id:
                me = await fetch_me(token)
                x_user_id = str(me.get('id')) if me.get('id') else None
                handle = me.get('username') or handle
                if x_user_id:
                    users_db.set_integration(uid, INTEGRATION_KEY, {'x_user_id': x_user_id, 'handle': handle})
            if x_user_id:
                tweets = await fetch_tweets(token, x_user_id, since_id)
                bookmarks = await fetch_bookmarks(token, x_user_id)
                new_posts = tweets + bookmarks
                source = 'oauth'
        except Exception as e:
            logger.warning(f'x_connector: official API sync failed for uid={uid}, falling back: {e}')

    # Fallback: RapidAPI public timeline by handle.
    if source is None:
        handle = integ.get('handle')
        if not handle:
            users_db.set_integration(uid, INTEGRATION_KEY, {'syncing': False})
            return {'success': False, 'error': 'not_connected', 'new_posts': 0, 'memories_created': 0}
        try:
            timeline = await social.get_twitter_timeline(handle)
            new_posts = [
                {
                    'id': str(t.id),
                    'text': t.text,
                    'created_at': t.created_at,
                    'kind': x_posts_db.KIND_TWEET,
                }
                for t in timeline.timeline
            ]
            source = 'rapidapi'
        except Exception as e:
            logger.error(f'x_connector: RapidAPI fallback failed for uid={uid}: {e}')
            users_db.set_integration(uid, INTEGRATION_KEY, {'syncing': False})
            return {'success': False, 'error': 'fetch_failed', 'new_posts': 0, 'memories_created': 0}

    written = x_posts_db.save_x_posts(uid, new_posts)
    # Only mine memories from posts we hadn't seen before (the raw store dedupes,
    # but extraction is the expensive part — restrict it to genuinely new text).
    fresh = new_posts if written == len(new_posts) else new_posts[:written]
    # Vector-index the raw posts so agents can semantically search the actual
    # tweets (not just the extracted memories) via the MCP search_x_posts tool.
    # Chunk to stay within Pinecone's per-upsert vector limit (~100).
    items_to_index = [
        {'post_id': p['id'], 'content': p.get('text', ''), 'kind': p.get('kind', 'tweet')} for p in fresh
    ]
    for i in range(0, len(items_to_index), 100):
        try:
            upsert_x_post_vectors_batch(uid, items_to_index[i : i + 100])
        except Exception as e:
            logger.warning(f'x_connector: failed to index x_posts chunk[{i}:{i+100}] for uid={uid}: {e}')
    memories_created = _extract_and_index(uid, fresh)

    users_db.set_integration(
        uid,
        INTEGRATION_KEY,
        {
            'last_synced_at': datetime.now(timezone.utc).isoformat(),
            'last_sync_source': source,
            'post_count': x_posts_db.count_x_posts(uid),
            'memory_count': int(integ.get('memory_count', 0)) + memories_created,
            'syncing': False,
        },
    )
    return {
        'success': True,
        'source': source,
        'new_posts': written,
        'memories_created': memories_created,
    }


def connection_status(uid: str) -> Dict:
    integ = users_db.get_integration(uid, INTEGRATION_KEY)
    if not integ or not integ.get('connected'):
        return {'success': True, 'connected': False}
    return {
        'success': True,
        'connected': True,
        'handle': integ.get('handle'),
        'post_count': integ.get('post_count', 0),
        'memory_count': integ.get('memory_count', 0),
        'syncing': bool(integ.get('syncing', False)),
        'last_synced_at': integ.get('last_synced_at'),
        'last_sync_source': integ.get('last_sync_source'),
    }


def disconnect(uid: str) -> None:
    users_db.set_integration(uid, INTEGRATION_KEY, {'connected': False, 'access_token': '', 'refresh_token': ''})
    _unregister_user(uid)


# ----------------------------------------------------------------------------
# Periodic background sync (driven by the hourly cron in modal/job.py)
# ----------------------------------------------------------------------------


def should_run_x_sync_job() -> bool:
    """Gate the sync to every SYNC_JOB_INTERVAL_HOURS (the cron fires hourly)."""
    return datetime.now(timezone.utc).hour % SYNC_JOB_INTERVAL_HOURS == 0


async def run_x_sync_job() -> Dict:
    """Incrementally sync every connected X user. Errors are isolated per user;
    a slow/failed account never blocks the others."""
    try:
        uids = [d.id for d in db.collection(_REGISTRY_COLLECTION).stream()]
    except Exception as e:
        logger.error(f'x_connector: sync job could not list users: {e}')
        return {'users': 0, 'synced': 0, 'new_posts': 0}

    synced = 0
    new_posts = 0
    for uid in uids:
        try:
            result = await sync_x_for_user(uid)
            if result.get('success'):
                synced += 1
                new_posts += int(result.get('new_posts', 0))
        except Exception as e:
            logger.warning(f'x_connector: sync job failed for uid={uid}: {e}')
        await asyncio.sleep(_SYNC_JOB_USER_SPACING_SEC)

    logger.info(f'x_connector: sync job done — users={len(uids)} synced={synced} new_posts={new_posts}')
    return {'users': len(uids), 'synced': synced, 'new_posts': new_posts}
