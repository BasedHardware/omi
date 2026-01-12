"""
Tools for performing web searches using Perplexity AI.
"""

import os

import requests
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig


@tool
def perplexity_web_search_tool(
    query: str,
    config: RunnableConfig = None,
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
    print(f"🔍 perplexity_web_search_tool called - query: {query}")

    api_key = os.getenv('PERPLEXITY_API_KEY')
    if not api_key:
        print("❌ perplexity_web_search_tool - PERPLEXITY_API_KEY not found in environment")
        return "Error: Perplexity API key not configured"

    try:
        url = "https://api.perplexity.ai/chat/completions"

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        payload = {
            "model": "sonar",
            "messages": [{"role": "user", "content": query}],
            "temperature": 0.2,
            "max_tokens": 1000,
        }

        response = requests.post(url, json=payload, headers=headers, timeout=30)

        if response.status_code != 200:
            print(f"❌ perplexity_web_search_tool - API error: {response.status_code} - {response.text[:200]}")
            return f"Error: Perplexity API returned status {response.status_code}. Please try again later."

        result = response.json()

        if 'choices' in result and len(result['choices']) > 0:
            content = result['choices'][0]['message']['content']

            citations = []
            if 'citations' in result:
                citations = result['citations']
            elif 'citations' in result.get('choices', [{}])[0].get('message', {}):
                citations = result['choices'][0]['message'].get('citations', [])

            formatted_result = f"Web Search Results:\n\n{content}\n\n"

            if citations:
                formatted_result += "\nSources:\n"
                for i, citation in enumerate(citations[:10], 1):
                    if isinstance(citation, dict):
                        url = citation.get('url', citation.get('citation', ''))
                        title = citation.get('title', '')
                        if url:
                            formatted_result += f"{i}. {title}\n   {url}\n"
                    elif isinstance(citation, str):
                        formatted_result += f"{i}. {citation}\n"

            print(f"✅ perplexity_web_search_tool - Successfully retrieved search results")
            return formatted_result.strip()
        else:
            print(f"⚠️ perplexity_web_search_tool - Unexpected response format: {result}")
            return "Error: Unexpected response format from Perplexity API"

    except requests.exceptions.Timeout:
        print("❌ perplexity_web_search_tool - Request timeout")
        return "Error: Request to Perplexity API timed out. Please try again later."
    except requests.exceptions.RequestException as e:
        print(f"❌ perplexity_web_search_tool - Request error: {e}")
        return f"Error: Failed to connect to Perplexity API. {str(e)}"
    except Exception as e:
        print(f"❌ perplexity_web_search_tool - Unexpected error: {e}")
        return f"Error: An unexpected error occurred while searching: {str(e)}"
