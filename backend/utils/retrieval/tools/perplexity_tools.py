"""
Tools for performing web searches using Perplexity AI.
"""

import logging
import re
from typing import Any, cast

import httpx
from langchain_core.tools import tool  # type: ignore[reportUnknownVariableType]  # langchain @tool decorator partially typed
from utils.http_client import get_webhook_client
from utils.llm.gateway_client import feature_auto_lane_id, get_llm_gateway_base_url, llm_gateway_headers
from utils.log_sanitizer import sanitize

logger = logging.getLogger(__name__)

# Legacy QoS coverage anchor: web search maps to get_model('web_search') in model_config.

# Fixed primary-source retrieval appendix shared by this tool's hop-2 retry and
# the desktop managed web-search lane. sonar-pro stops at the vendor marketing
# site for product-history questions unless the query itself asks for primary
# sources (live RCA 2026-09-02: a rewritten query and a hop-2 retry both found
# the founder interviews; context size, search_type, and reasoning models did
# not move the retrieved URL set).
WEB_SEARCH_RETRIEVAL_APPENDIX = (
    "\n\nGo beyond the product's own marketing and documentation pages: search for primary sources such as "
    'founder interviews, podcast and conference appearances, Product Hunt launch posts and their comment '
    'threads, launch postmortems, and press coverage. Try likely alternative spellings and former names of '
    'the product (for example, a spoken "Whisper Flow" may be written "Wispr Flow") and search the founders\' '
    'names alongside the product. Report concrete dates and timelines from those primary sources.'
)

# Thin-miss markers on the model text of an otherwise HTTP 200 answer: the
# retrieval landed only on the vendor marketing site and produced no primary
# citation. Cheap phrase heuristic by design — a false positive costs one extra
# bounded sonar call, and hop count is capped at two either way.
_THIN_MISS_PHRASES = (
    "couldn't find",
    "couldn’t find",
    'could not find',
    "can't find",
    "can’t find",
    'cannot find',
    'unable to find',
    "couldn't locate",
    'could not locate',
    'no public information',
    'no public info',
    'no publicly available',
    'not publicly available',
    'no public timeline',
    'no exact timeline',
    'no specific timeline',
    'no official timeline',
    'no public details',
    'no specific information',
    'no detailed information',
    'limited public information',
    'no primary source',
    'site focuses on',
    'marketing site',
)
_THIN_MISS_PATTERN = re.compile('|'.join(re.escape(phrase) for phrase in _THIN_MISS_PHRASES), re.IGNORECASE)


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

    return await _perplexity_gateway_search(query)


async def _perplexity_gateway_search(query: str) -> str:
    try:
        response = await _post_gateway_chat_completion(query)
        if response.status_code != 200:
            logger.error(
                f"❌ perplexity_web_search_tool - Gateway API error: {response.status_code} - "
                f"{sanitize(response.text[:200])}"
            )
            return f"Error: Perplexity API returned status {response.status_code}. Please try again later."

        result = response.json()
        formatted = _format_perplexity_response(result)
        if not _looks_like_thin_miss(_model_text(result)):
            return formatted

        # Hop-2: the first retrieval stopped at the vendor marketing site.
        # Exactly one retry with the primary-source appendix — never a third
        # call, and any hop-2 failure keeps the first formatted answer.
        logger.info("🔁 perplexity_web_search_tool - Thin result, retrying with primary-source query rewrite")
        try:
            retry_response = await _post_gateway_chat_completion(query + WEB_SEARCH_RETRIEVAL_APPENDIX)
            if retry_response.status_code != 200:
                logger.error(
                    f"❌ perplexity_web_search_tool - Hop-2 Gateway API error: {retry_response.status_code} - "
                    f"{sanitize(retry_response.text[:200])}"
                )
                return formatted
            return _format_perplexity_response(retry_response.json())
        except Exception as e:
            logger.warning(f"🔁 perplexity_web_search_tool - Hop-2 failed ({type(e).__name__}), returning first result")
            return formatted
    except httpx.TimeoutException:
        logger.warning("❌ perplexity_web_search_tool - Gateway timeout")
        return "Error: Web search is temporarily unavailable. Please try again later."
    except httpx.HTTPError as e:
        logger.error(f"❌ perplexity_web_search_tool - Gateway request error: {type(e).__name__}")
        return "Error: Web search is temporarily unavailable. Please try again later."
    except (ValueError, IndexError, KeyError, TypeError):
        logger.error("⚠️ perplexity_web_search_tool - Unexpected response format")
        return "Error: Unexpected response format from Perplexity API"
    except Exception as e:
        logger.error(f"❌ perplexity_web_search_tool - Unexpected error: {e}")
        return f"Error: An unexpected error occurred while searching: {str(e)}"


async def _post_gateway_chat_completion(content: str) -> httpx.Response:
    return await get_webhook_client().post(
        f'{get_llm_gateway_base_url()}/v1/chat/completions',
        json={
            "model": feature_auto_lane_id('web_search'),
            "messages": [{"role": "user", "content": content}],
            "temperature": 0.2,
            "max_tokens": 1000,
        },
        headers=llm_gateway_headers(),
        timeout=30.0,
    )


def _looks_like_thin_miss(text: str) -> bool:
    return bool(text) and _THIN_MISS_PATTERN.search(text) is not None


def _model_text(result: dict[str, Any]) -> str:
    try:
        content: Any = result['choices'][0]['message']['content']
    except (KeyError, IndexError, TypeError):
        return ''
    return content if isinstance(content, str) else ''


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
