"""
Tools for performing web searches using Perplexity AI.
"""

import logging
import os
from typing import Any, cast

import httpx
from langchain_core.tools import tool  # type: ignore[reportUnknownVariableType]  # langchain @tool decorator partially typed
from utils.http_client import get_webhook_client
from utils.llm.clients import get_model
from utils.llm.gateway_client import feature_auto_lane_id, get_llm_gateway_base_url, llm_gateway_headers
from utils.llm.gateway_client import should_route_features_through_gateway
from utils.log_sanitizer import sanitize

logger = logging.getLogger(__name__)

# Legacy QoS coverage anchor: web search maps to get_model('web_search') in model_config.


@tool
async def perplexity_web_search_tool(
    query: str,
) -> str:
    """
    Search the web for current information using Perplexity AI's search capabilities.

    Use this tool when:
    - User asks about current events, news, or recent information
    - User asks questions that require up-to-date web information
    - User asks "what is the latest on X" or "tell me about X"
    - User asks factual questions that may require web search
    - User asks about topics not in your training data or memory

    DO NOT use this tool for:
    - Questions about the user's personal conversations or memories (use get_memories_tool instead)
    - Questions about the user's action items (use get_action_items_tool instead)
    - Questions about conversations the user had (use get_conversations_tool or search_conversations_tool instead)
    - Questions about Omi/Friend product information (use get_omi_product_info_tool instead)

    Args:
        query: The search query or question to search for on the web

    Returns:
        Formatted search results with citations from Perplexity AI

    Example:
        query="What are the latest developments in AI in 2025?"
        Returns web search results with citations about recent AI developments
    """
    logger.info(f"🔍 perplexity_web_search_tool called - query: {query}")

    if should_route_features_through_gateway():
        return await _perplexity_gateway_search(query)
    return await _perplexity_legacy_search(query)


async def _perplexity_gateway_search(query: str) -> str:
    try:
        response = await get_webhook_client().post(
            f'{get_llm_gateway_base_url()}/v1/chat/completions',
            json={
                "model": feature_auto_lane_id('web_search'),
                "messages": [{"role": "user", "content": query}],
                "temperature": 0.2,
                "max_tokens": 1000,
            },
            headers=llm_gateway_headers(),
            timeout=30.0,
        )

        if response.status_code != 200:
            logger.error(
                f"❌ perplexity_web_search_tool - Gateway API error: {response.status_code} - "
                f"{sanitize(response.text[:200])}"
            )
            return f"Error: Perplexity API returned status {response.status_code}. Please try again later."

        return _format_perplexity_response(response.json())
    except httpx.TimeoutException:
        logger.warning("❌ perplexity_web_search_tool - Request timeout")
        return "Error: Request to Perplexity API timed out. Please try again later."
    except httpx.HTTPError as e:
        logger.error(f"❌ perplexity_web_search_tool - Request error: {e}")
        return f"Error: Failed to connect to Perplexity API. {str(e)}"
    except (ValueError, IndexError, KeyError, TypeError):
        logger.error("⚠️ perplexity_web_search_tool - Unexpected response format")
        return "Error: Unexpected response format from Perplexity API"
    except Exception as e:
        logger.error(f"❌ perplexity_web_search_tool - Unexpected error: {e}")
        return f"Error: An unexpected error occurred while searching: {str(e)}"


async def _perplexity_legacy_search(query: str) -> str:
    api_key = os.getenv('PERPLEXITY_API_KEY')
    if not api_key:
        logger.warning("❌ perplexity_web_search_tool - PERPLEXITY_API_KEY not found in environment")
        return "Error: Perplexity API key not configured"

    try:
        response = await get_webhook_client().post(
            "https://api.perplexity.ai/chat/completions",
            json={
                "model": get_model('web_search'),
                "messages": [{"role": "user", "content": query}],
                "temperature": 0.2,
                "max_tokens": 1000,
            },
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=30.0,
        )

        if response.status_code != 200:
            logger.error(
                f"❌ perplexity_web_search_tool - API error: {response.status_code} - {sanitize(response.text[:200])}"
            )
            return f"Error: Perplexity API returned status {response.status_code}. Please try again later."

        return _format_perplexity_response(response.json())
    except ValueError:
        logger.error("⚠️ perplexity_web_search_tool - Unexpected response format")
        return "Error: Unexpected response format from Perplexity API"
    except httpx.TimeoutException:
        logger.warning("❌ perplexity_web_search_tool - Request timeout")
        return "Error: Request to Perplexity API timed out. Please try again later."
    except httpx.HTTPError as e:
        logger.error(f"❌ perplexity_web_search_tool - Request error: {e}")
        return f"Error: Failed to connect to Perplexity API. {str(e)}"
    except Exception as e:
        logger.error(f"❌ perplexity_web_search_tool - Unexpected error: {e}")
        return f"Error: An unexpected error occurred while searching: {str(e)}"


def _format_perplexity_response(result: dict[str, Any]) -> str:
    if 'choices' in result and len(result['choices']) > 0:
        content: Any = result['choices'][0]['message']['content']
        formatted_result = f"Web Search Results:\n\n{content}\n\n"

        citations = _extract_citations(result)
        if citations:
            formatted_result += "\nSources:\n"
            for i, citation in enumerate(citations[:10], 1):
                if isinstance(citation, dict):
                    cit = cast(dict[str, Any], citation)
                    url = cit.get('url', cit.get('citation', ''))
                    title = cit.get('title', '')
                    if url:
                        formatted_result += f"{i}. {title}\n   {url}\n"
                elif isinstance(citation, str):
                    formatted_result += f"{i}. {citation}\n"

        logger.info("✅ perplexity_web_search_tool - Successfully retrieved search results")
        return formatted_result.strip()

    logger.error(f"⚠️ perplexity_web_search_tool - Unexpected response format: {sanitize(str(result)[:200])}")
    return "Error: Unexpected response format from Perplexity API"


def _extract_citations(result: dict[str, Any]) -> list[Any]:
    citations: Any = result.get('citations') or result.get('search_results')
    if citations:
        return citations
    return result.get('choices', [{}])[0].get('message', {}).get('citations', [])
