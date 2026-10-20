"""Refresh external MCP credentials once across workers, before retrying a tool."""

import asyncio
import logging
import math
import secrets
import time
from typing import Any

from database import redis_db
from database.mcp_client_credentials import claim_refresh, complete_refresh, release_refresh
from models.mcp_client import McpCredentialError
from utils import mcp_client
from utils.executors import db_executor, run_blocking

logger = logging.getLogger(__name__)
REFRESH_WAIT_SECONDS = 20


async def refresh_mcp_access_token(
    app_id: str,
    server_url: str,
    tokens: dict[str, Any],
    rejected_access_token: str | None,
) -> str:
    owner = secrets.token_urlsafe(24)
    expected = dict(tokens)
    deadline = time.monotonic() + REFRESH_WAIT_SECONDS
    claimed = None
    committed = False
    try:
        while True:
            claim = await run_blocking(
                db_executor, claim_refresh, app_id, server_url, expected, rejected_access_token, owner
            )
            if claim.state == 'current':
                tokens.clear()
                tokens.update(claim.tokens)
                return tokens['access_token']
            if claim.state == 'claimed':
                claimed = claim.tokens
                break
            if time.monotonic() >= deadline:
                raise McpCredentialError('MCP authorization is being refreshed. Please try again shortly.')
            await asyncio.sleep(0.1)

        response = await mcp_client.refresh_oauth_token(
            claimed['token_endpoint'],
            claimed['refresh_token'],
            claimed['client_id'],
            claimed.get('client_secret'),
        )
        access_token = response.get('access_token')
        if not isinstance(access_token, str) or not access_token:
            raise McpCredentialError('MCP token refresh did not return an access token.')
        updated = {**claimed, 'access_token': access_token}
        if response.get('refresh_token'):
            updated['refresh_token'] = response['refresh_token']
        updated.pop('expires_at', None)
        try:
            expires_in = float(response.get('expires_in') or 0)
        except (ValueError, TypeError):
            expires_in = 0
        if math.isfinite(expires_in) and expires_in > 0:
            updated['expires_at'] = time.time() + expires_in
        await run_blocking(db_executor, complete_refresh, app_id, server_url, claimed, owner, updated)
        committed = True
        tokens.clear()
        tokens.update(updated)
        await run_blocking(db_executor, redis_db.delete_app_cache_by_id, app_id)
        return access_token
    except asyncio.CancelledError:
        # The provider may consume the token after local cancellation. Keep its
        # owner fenced until lease expiry instead of admitting a second request.
        claimed = None
        raise
    except McpCredentialError:
        raise
    except Exception as error:
        logger.warning('MCP OAuth refresh failed app=%s cause=%s', app_id, type(error).__name__)
        raise McpCredentialError('MCP authorization could not be refreshed. Reconnect the integration.') from None
    finally:
        if claimed is not None and not committed:
            try:
                await run_blocking(db_executor, release_refresh, app_id, claimed, owner)
            except Exception as error:
                # A failed release remains fenced until the bounded lease expires.
                logger.warning('MCP OAuth refresh release failed app=%s cause=%s', app_id, type(error).__name__)
