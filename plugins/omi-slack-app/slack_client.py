import os
from typing import Any, Dict, List

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from .logger import logger
from .error_handler import http_exception

# NOTE: The WebClient is deliberately instantiated inside each method
# to ensure that any credential‑related errors are caught and handled
# uniformly. This also prevents the client from being created at import
# time, which could raise exceptions before we have a chance to log them.


class SlackClient:
    """
    Thin wrapper around ``slack_sdk.WebClient`` providing the subset of
    functionality required by the OMI Slack app plugin.
    """

    def _get_client(self) -> WebClient:
        """
        Create a ``WebClient`` instance using the ``SLACK_BOT_TOKEN``
        environment variable. Any exception (e.g. missing token) is
        re‑raised as a generic HTTPException after logging.
        """
        try:
            token = os.getenv("SLACK_BOT_TOKEN")
            if not token:
                raise RuntimeError("SLACK_BOT_TOKEN is not set")
            return WebClient(token=token)
        except Exception as e:  # pragma: no cover – exercised via tests
            raise http_exception(
                status_code=500,
                user_message="Failed to initialise Slack client",
                original=e,
            )

    async def complete_oauth(self, *, state: str, code: str) -> None:
        """
        Complete the OAuth flow. Errors are logged and re‑raised as generic
        HTTPExceptions by the caller.
        """
        client = self._get_client()
        # Placeholder for actual OAuth logic.
        # Any exception from the SDK will bubble up and be handled by the route.
        await client.oauth_v2_access(client_id=os.getenv("SLACK_CLIENT_ID"), client_secret=os.getenv("SLACK_CLIENT_SECRET"), code=code)

    async def update_channel(self, payload: Dict[str, Any]) -> None:
        client = self._get_client()
        try:
            await client.conversations_rename(channel=payload["channel_id"], name=payload["new_name"])
        except SlackApiError as e:
            logger.error("Slack API error while updating channel: %s", e)
            raise

    async def refresh_channels(self) -> None:
        client = self._get_client()
        try:
            await client.conversations_list()
        except SlackApiError as e:
            logger.error("Slack API error while refreshing channels: %s", e)
            raise

    async def logout(self) -> None:
        client = self._get_client()
        try:
            await client.auth_revoke()
        except SlackApiError as e:
            logger.error("Slack API error while revoking token: %s", e)
            raise

    async def handle_event(self, payload: Dict[str, Any]) -> None:
        client = self._get_client()
        # Simplified event handling – real implementation would be more complex.
        try:
            event_type = payload.get("type")
            if event_type == "message":
                await client.chat_postMessage(channel=payload["channel"], text=payload["text"])
        except SlackApiError as e:
            logger.error("Slack API error while handling event: %s", e)
            raise

    async def send_message(self, payload: Dict[str, Any]) -> None:
        client = self._get_client()
        try:
            await client.chat_postMessage(channel=payload["channel"], text=payload["text"])
        except SlackApiError as e:
            logger.error("Slack API error while sending message: %s", e)
            raise

    async def search_messages(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        client = self._get_client()
        try:
            response = await client.search_messages(query=payload["query"])
            return response["messages"]["matches"]
        except SlackApiError as e:
            logger.error("Slack API error while searching messages: %s", e)
            raise

    async def search_channels(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        client = self._get_client()
        try:
            response = await client.search_conversations(query=payload["query"])
            return response["channels"]["matches"]
        except SlackApiError as e:
            logger.error("Slack API error while searching channels: %s", e)
            raise
