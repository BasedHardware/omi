import os
from typing import List, Dict, Optional

try:
    from tavily import TavilyClient
except ImportError:
    print("Warning: tavily-python not installed. Web search functionality will not work.")
    TavilyClient = None


class WebSearchResult:
    """Web search result structure for consistent handling."""

    def __init__(self, title: str, url: str, content: str, score: float = 0.0):
        self.title = title
        self.url = url
        self.content = content
        self.score = score

    def to_dict(self) -> dict:
        return {'title': self.title, 'url': self.url, 'content': self.content, 'score': self.score}


def perform_web_search(query: str, max_results: int = 5) -> List[WebSearchResult]:
    """
    Perform web search using Tavily API.

    Args:
        query: Search query string
        max_results: Maximum number of results to return

    Returns:
        List of WebSearchResult objects
    """
    try:
        # Check if Tavily is available
        if TavilyClient is None:
            print("Error: tavily-python not installed")
            return []

        # Initialize Tavily client
        api_key = os.environ.get('TAVILY_API_KEY')
        if not api_key:
            print("Warning: TAVILY_API_KEY not found in environment variables")
            return []

        client = TavilyClient(api_key=api_key)

        # Perform search with optimized parameters for v0.7.11
        response = client.search(
            query=query,
            max_results=max_results,
            search_depth="basic",  # Fast search for chat responsiveness
            include_domains=None,  # No domain restrictions
            exclude_domains=["facebook.com", "twitter.com", "instagram.com"],  # Exclude social media noise
            include_answer=True,  # Get direct answer if available
            include_raw_content=False,  # Keep response size manageable
        )

        # Convert to WebSearchResult objects
        results = []
        for result in response.get('results', []):
            web_result = WebSearchResult(
                title=result.get('title', ''),
                url=result.get('url', ''),
                content=result.get('content', ''),
                score=result.get('score', 0.0),
            )
            results.append(web_result)

        print(f"Web search completed: {len(results)} results for query '{query}'")
        return results

    except Exception as e:
        print(f"Error performing web search: {e}")
        return []


def format_web_search_context(results: List[WebSearchResult]) -> str:
    """
    Format web search results into a context string for LLM processing.

    Args:
        results: List of WebSearchResult objects

    Returns:
        Formatted context string with sources
    """
    if not results:
        return "No web search results found."

    context = "Web Search Results:\n\n"

    for i, result in enumerate(results, 1):
        context += f"[{i}] {result.title}\n"
        context += f"Source: {result.url}\n"
        context += f"Content: {result.content[:500]}{'...' if len(result.content) > 500 else ''}\n\n"

    return context


def extract_search_citations(response: str, results: List[WebSearchResult]) -> str:
    """
    Add proper citations to response based on search results referenced.

    Args:
        response: LLM response text
        results: Web search results used

    Returns:
        Response with formatted citations
    """
    if not results:
        return response

    # Add sources section at the end
    sources_section = "\n\nSources:\n"
    for i, result in enumerate(results, 1):
        sources_section += f"[{i}] {result.title} - {result.url}\n"

    return response + sources_section


def create_structured_citations(web_results: List[WebSearchResult]) -> List[dict]:
    """
    Convert WebSearchResult objects to structured citations for frontend.

    Args:
        web_results: List of WebSearchResult objects from search

    Returns:
        List of citation dictionaries for ResponseMessage
    """
    citations = []
    for i, result in enumerate(web_results, 1):
        citation = {
            'title': result.title,
            'url': result.url,
            'snippet': result.content[:200] + "..." if len(result.content) > 200 else result.content,
            'index': i,
        }
        citations.append(citation)

    return citations


def test_web_search():
    """Test function to verify Tavily integration is working."""
    try:
        results = perform_web_search("What is the weather like today?", max_results=3)
        print(f"✅ Web search test successful: Found {len(results)} results")
        if results:
            print(f"✅ Sample result: {results[0].title}")
            # Test structured citations
            citations = create_structured_citations(results)
            print(f"✅ Structured citations created: {len(citations)} citations")
        return True
    except Exception as e:
        print(f"❌ Web search test failed: {e}")
        return False
