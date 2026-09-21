import logging
from typing import List, Any

from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.errors import SlackApiError

_logger = logging.getLogger("omi_slack_app.slack_client")

class SlackClient:
    """
    Thin wrapper around Slack's AsyncWebClient that guarantees no raw exception
    strings are ever propagated to callers.
    """

    def __init__(self):
        try:
            # The token is expected to be provided via environment variable.
            self.client = AsyncWebClient()
        except Exception as e:
            # Instantiation itself can fail (e.g., missing token)
            _logger.error("Failed to create Slack AsyncWebClient", exc_info=e)
            raise RuntimeError("Unable to initialise Slack client") from e

    async def send_message(self, channel: str, text: str) -> None:
        try:
            await self.client.chat_postMessage(channel=channel, text=text)
        except SlackApiError as e:
            _logger.error("Slack API error while sending message", exc_info=e)
            raise RuntimeError("Failed to send message") from e
        except Exception as e:
            _logger.error("Unexpected error while sending message", exc_info=e)
            raise RuntimeError("Failed to send message") from e

    async def get_channel_history(self, channel: str, limit: int = 100) -> List[Any]:
        try:
            resp = await self.client.conversations_history(channel=channel, limit=limit)
            return resp["messages"]
        except SlackApiError as e:
            _logger.error("Slack API error while fetching channel history", exc_info=e)
            raise RuntimeError("Failed to fetch channel history") from e
        except Exception as e:
            _logger.error("Unexpected error while fetching channel history", exc_info=e)
            raise RuntimeError("Failed to fetch channel history") from e

    async def search_messages(self, query: str) -> List[Any]:
        try:
            resp = await self.client.search_messages(query=query)
            return resp["messages"]["matches"]
        except SlackApiError as e:
            _logger.error("Slack API error while searching messages", exc_info=e)
            raise RuntimeError("Failed to search messages") from e
        except Exception as e:
            _logger.error("Unexpected error while searching messages", exc_info=e)
            raise RuntimeError("Failed to search messages") from e

    async def search_channels(self, query: str) -> List[Any]:
        try:
            resp = await self.client.search_channels(query=query)
            return resp["channels"]["matches"]
        except SlackApiError as e:
            _logger.error("Slack API error while searching channels", exc_info=e)
            raise RuntimeError("Failed to search channels") from e
        except Exception as e:
            _logger.error("Unexpected error while searching channels", exc_info=e)
            raise RuntimeError("Failed to search channels") from e
