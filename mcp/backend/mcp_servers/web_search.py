"""
Fixed Wikipedia FastMCP Server with proper error handling and rate limiting.
"""

import asyncio
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
import time
from functools import wraps

import requests
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP("Wikipedia Search Server")

# Configuration
USER_AGENT = "WikipediaMCPServer/1.0 (fastmcp-bot; contact@example.com)"
RATE_LIMIT_DELAY = 1.0  # seconds between requests
MAX_RETRIES = 3
TIMEOUT = 10


class WikipediaConfig:
    """Configuration for Wikipedia API access"""
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': USER_AGENT,
            'Accept': 'application/json'
        })
        self.last_request_time = 0
        self.rate_limit_delay = RATE_LIMIT_DELAY


config = WikipediaConfig()


def rate_limited(func):
    """Decorator to enforce rate limiting"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        elapsed = time.time() - config.last_request_time
        if elapsed < config.rate_limit_delay:
            wait_time = config.rate_limit_delay - elapsed
            logger.debug(f"Rate limiting: waiting {wait_time:.2f}s")
            await asyncio.sleep(wait_time)
        
        result = await func(*args, **kwargs)
        config.last_request_time = time.time()
        return result
    
    return wrapper


class SearchResult(BaseModel):
    """Wikipedia search result model"""
    title: str = Field(description="Article title")
    url: str = Field(description="Article URL")
    snippet: Optional[str] = Field(None, description="Article snippet")


class ArticleSummary(BaseModel):
    """Wikipedia article summary model"""
    title: str = Field(description="Article title")
    extract: str = Field(description="Article summary/extract")
    url: str = Field(description="Article URL")
    thumbnail: Optional[str] = Field(None, description="Thumbnail image URL")


async def make_request_with_retry(
    url: str,
    params: Dict[str, Any],
    max_retries: int = MAX_RETRIES
) -> Optional[requests.Response]:
    """Make HTTP request with retry logic and exponential backoff"""
    
    for attempt in range(max_retries):
        try:
            # Use asyncio to run blocking requests call
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: config.session.get(
                    url,
                    params=params,
                    timeout=TIMEOUT
                )
            )
            
            if response.status_code == 200:
                return response
            elif response.status_code == 403:
                logger.warning(f"403 Forbidden on attempt {attempt + 1}/{max_retries}")
                if attempt < max_retries - 1:
                    backoff_time = 2 ** attempt
                    logger.info(f"Backing off for {backoff_time}s")
                    await asyncio.sleep(backoff_time)
            elif response.status_code == 429:  # Too Many Requests
                logger.warning(f"Rate limited (429) on attempt {attempt + 1}/{max_retries}")
                if attempt < max_retries - 1:
                    backoff_time = 5 * (2 ** attempt)
                    logger.info(f"Backing off for {backoff_time}s")
                    await asyncio.sleep(backoff_time)
            else:
                response.raise_for_status()
                
        except requests.exceptions.Timeout:
            logger.error(f"Request timeout on attempt {attempt + 1}/{max_retries}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
            else:
                raise
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed on attempt {attempt + 1}/{max_retries}: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
            else:
                raise
    
    return None


@mcp.tool()
@rate_limited
async def search_wikipedia(
    query: str,
    limit: int = 5
) -> List[SearchResult]:
    """
    Search Wikipedia articles by query.
    
    Args:
        query: Search query string
        limit: Maximum number of results (default: 5, max: 10)
    
    Returns:
        List of search results with titles and URLs
    """
    try:
        limit = min(limit, 10)  # Cap at 10 results
        
        logger.info(f"Searching Wikipedia for: {query}")
        
        # Use OpenSearch API
        params = {
            'action': 'opensearch',
            'search': query,
            'limit': limit,
            'namespace': 0,
            'format': 'json'
        }
        
        response = await make_request_with_retry(
            'https://en.wikipedia.org/w/api.php',
            params
        )
        
        if not response:
            raise Exception("Failed to get response after retries")
        
        data = response.json()
        
        # OpenSearch returns: [query, [titles], [descriptions], [urls]]
        if len(data) >= 4:
            titles = data[1]
            descriptions = data[2]
            urls = data[3]
            
            results = []
            for i in range(len(titles)):
                results.append(SearchResult(
                    title=titles[i],
                    url=urls[i],
                    snippet=descriptions[i] if i < len(descriptions) else None
                ))
            
            logger.info(f"Found {len(results)} results")
            return results
        else:
            logger.warning("Unexpected API response format")
            return []
            
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise Exception(f"Wikipedia search failed: {str(e)}")


@mcp.tool()
@rate_limited
async def get_article_summary(
    title: str
) -> ArticleSummary:
    """
    Get summary of a Wikipedia article.
    
    Args:
        title: Article title (can include spaces)
    
    Returns:
        Article summary with title, extract, URL, and thumbnail
    """
    try:
        logger.info(f"Getting summary for: {title}")
        
        # Use REST API v1 for better summary
        page_title = title.replace(' ', '_')
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{page_title}"
        
        response = await make_request_with_retry(url, params={})
        
        if not response:
            raise Exception("Failed to get response after retries")
        
        data = response.json()
        
        # Check if it's an error response
        if 'type' in data and data['type'] == 'https://mediawiki.org/wiki/HyperSwitch/errors/not_found':
            raise Exception(f"Article not found: {title}")
        
        thumbnail_url = None
        if 'thumbnail' in data and 'source' in data['thumbnail']:
            thumbnail_url = data['thumbnail']['source']
        
        summary = ArticleSummary(
            title=data.get('title', title),
            extract=data.get('extract', 'No summary available'),
            url=data.get('content_urls', {}).get('desktop', {}).get('page', ''),
            thumbnail=thumbnail_url
        )
        
        logger.info(f"Retrieved summary for: {summary.title}")
        return summary
        
    except Exception as e:
        logger.error(f"Failed to get article summary: {e}")
        raise Exception(f"Failed to get article summary: {str(e)}")


@mcp.tool()
@rate_limited
async def get_article_content(
    title: str,
    max_chars: int = 5000
) -> Dict[str, Any]:
    """
    Get full content of a Wikipedia article.
    
    Args:
        title: Article title
        max_chars: Maximum characters to return (default: 5000)
    
    Returns:
        Dictionary with title, content, url, and metadata
    """
    try:
        logger.info(f"Getting full content for: {title}")
        
        params = {
            'action': 'query',
            'format': 'json',
            'titles': title,
            'prop': 'extracts|info',
            'exintro': False,  # Get full content, not just intro
            'explaintext': True,  # Plain text
            'inprop': 'url',
            'redirects': 1
        }
        
        response = await make_request_with_retry(
            'https://en.wikipedia.org/w/api.php',
            params
        )
        
        if not response:
            raise Exception("Failed to get response after retries")
        
        data = response.json()
        
        pages = data.get('query', {}).get('pages', {})
        
        if not pages:
            raise Exception(f"No content found for: {title}")
        
        # Get first (and usually only) page
        page_id = list(pages.keys())[0]
        
        if page_id == '-1':
            raise Exception(f"Article not found: {title}")
        
        page = pages[page_id]
        
        content = page.get('extract', '')
        if len(content) > max_chars:
            content = content[:max_chars] + "... (truncated)"
        
        result = {
            'title': page.get('title', title),
            'content': content,
            'url': page.get('fullurl', ''),
            'page_id': page_id,
            'length': len(page.get('extract', '')),
            'truncated': len(page.get('extract', '')) > max_chars
        }
        
        logger.info(f"Retrieved content for: {result['title']} ({result['length']} chars)")
        return result
        
    except Exception as e:
        logger.error(f"Failed to get article content: {e}")
        raise Exception(f"Failed to get article content: {str(e)}")


@mcp.tool()
async def get_server_status() -> Dict[str, Any]:
    """
    Get Wikipedia MCP server status and configuration.
    
    Returns:
        Server status information
    """
    return {
        'status': 'running',
        'user_agent': USER_AGENT,
        'rate_limit_delay': config.rate_limit_delay,
        'max_retries': MAX_RETRIES,
        'timeout': TIMEOUT,
        'last_request': datetime.fromtimestamp(config.last_request_time).isoformat() if config.last_request_time > 0 else 'never',
        'session_headers': dict(config.session.headers)
    }


if __name__ == "__main__":
    # Run the MCP server
    logger.info("Starting Wikipedia FastMCP Server...")
    logger.info(f"User-Agent: {USER_AGENT}")
    logger.info(f"Rate limit: {RATE_LIMIT_DELAY}s between requests")
    
    mcp.run()