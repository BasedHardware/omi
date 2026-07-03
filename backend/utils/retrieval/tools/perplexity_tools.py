"""
Tools for performing web searches using Perplexity AI.
"""

from langchain_core.tools import tool
from openai import APIConnectionError, APIStatusError, APITimeoutError
from utils.llm.gateway_client import feature_auto_lane_id
from utils.llm.providers import get_or_create_omi_gateway_llm
import logging

logger = logging.getLogger(__name__)

# Legacy QoS coverage anchor: web search still maps to get_model('web_search') in model_config,
# while this tool now invokes the generated gateway lane directly.


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

    try:
        response = await get_or_create_omi_gateway_llm(feature_auto_lane_id('web_search')).ainvoke(
            query, max_tokens=1000, temperature=0.2
        )
        content = response.content if hasattr(response, 'content') else str(response)
        if content:
            logger.info("✅ perplexity_web_search_tool - Successfully retrieved search results")
            return f"Web Search Results:\n\n{content}".strip()
        logger.error("⚠️ perplexity_web_search_tool - Empty response")
        return "Error: Unexpected response format from Perplexity API"
    except ValueError as e:
        logger.error(f"❌ perplexity_web_search_tool - Gateway routing unavailable: {e}")
        return "Error: Perplexity gateway route not configured"
    except APIStatusError as e:
        logger.error(f"❌ perplexity_web_search_tool - API error: {e.status_code}")
        return f"Error: Perplexity API returned status {e.status_code}. Please try again later."
    except APITimeoutError:
        logger.warning("❌ perplexity_web_search_tool - Request timeout")
        return "Error: Request to Perplexity API timed out. Please try again later."
    except APIConnectionError as e:
        logger.error(f"❌ perplexity_web_search_tool - Request error: {e}")
        return f"Error: Failed to connect to Perplexity API. {str(e)}"
    except (IndexError, KeyError, TypeError):
        logger.error("⚠️ perplexity_web_search_tool - Unexpected response format")
        return "Error: Unexpected response format from Perplexity API"

    except Exception as e:
        logger.error(f"❌ perplexity_web_search_tool - Unexpected error: {e}")
        return f"Error: An unexpected error occurred while searching: {str(e)}"
