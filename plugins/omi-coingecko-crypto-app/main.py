"""CoinGecko Cryptocurrency & Market Intelligence Integration App for Omi.

Provides real-time cryptocurrency prices, search, trending assets, and market
rankings through CoinGecko's public REST API for Omi AI wearable users.
"""

from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional
import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse

from models import (
    ChatToolResponse,
    GetCryptoPriceRequest,
    GetCryptoMarketOverviewRequest,
    GetTrendingCryptoRequest,
    SearchCryptoCoinsRequest,
)

COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"
REQUEST_TIMEOUT_SECONDS = 15.0
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 (Omi-Crypto-Integration/1.0)"
)


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    headers = {"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, headers=headers) as client:
        app_instance.state.http_client = client
        yield


app = FastAPI(
    title="Omi CoinGecko Crypto Integration",
    description="Real-time cryptocurrency quotes, search, market overview, and trending coins for Omi chat tools.",
    version="1.0.0",
    lifespan=lifespan,
)


def _get_currency_symbol(currency_code: str) -> str:
    """Return appropriate currency symbol or prefix."""
    code = currency_code.lower()
    symbols = {
        "usd": "$",
        "eur": "EUR ",
        "gbp": "GBP ",
        "jpy": "JPY ",
        "cad": "CAD ",
        "aud": "AUD ",
        "chf": "CHF ",
        "cny": "CNY ",
        "inr": "INR ",
    }
    return symbols.get(code, f"{code.upper()} ")


def _format_currency(amount: Optional[float], currency_symbol: str = "$", decimals: int = 2) -> str:
    """Format numerical prices cleanly with precision preservation for micro-values."""
    if amount is None:
        return "N/A"
    if amount == 0:
        return f"{currency_symbol}0.00"
    if amount >= 1.0:
        return f"{currency_symbol}{amount:,.{decimals}f}"
    if amount >= 0.0001:
        return f"{currency_symbol}{amount:,.4f}"
    if amount >= 1e-8:
        return f"{currency_symbol}{amount:,.8f}"
    return f"{currency_symbol}{amount:.4e}"


def _format_compact(value: Optional[float], currency_symbol: str = "$") -> str:
    """Format large numbers into human-readable compact units (e.g. $1.25B, EUR 500M)."""
    if value is None or value == 0:
        return "N/A"
    abs_v = abs(value)
    if abs_v >= 1e12:
        return f"{currency_symbol}{value / 1e12:.2f}T"
    if abs_v >= 1e9:
        return f"{currency_symbol}{value / 1e9:.2f}B"
    if abs_v >= 1e6:
        return f"{currency_symbol}{value / 1e6:.2f}M"
    if abs_v >= 1e3:
        return f"{currency_symbol}{value / 1e3:.2f}K"
    return f"{currency_symbol}{value:,.2f}"


def _format_percentage(change: Optional[float]) -> str:
    """Format percentage with +/- sign."""
    if change is None:
        return "N/A"
    return f"{change:+.2f}%"


async def _fetch_coingecko(endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
    """Execute asynchronous GET request against CoinGecko with error handling."""
    client: httpx.AsyncClient = app.state.http_client
    url = f"{COINGECKO_BASE_URL}{endpoint}"
    try:
        response = await client.get(url, params=params)
        if response.status_code == 429:
            raise ValueError("CoinGecko API rate limit reached. Please wait a moment before trying again.")
        if response.status_code == 404:
            raise ValueError(f"Resource not found at {endpoint}.")
        response.raise_for_status()
        return response.json()
    except httpx.TimeoutException:
        raise ValueError("Request to CoinGecko timed out. Please try again.")
    except httpx.HTTPError as exc:
        raise ValueError(f"CoinGecko network error: {exc}")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    first_error = exc.errors()[0] if exc.errors() else {}
    location = ".".join(str(part) for part in first_error.get("loc", []) if part != "body")
    message = first_error.get("msg", "invalid request")
    detail = f"{location}: {message}" if location else message
    response = ChatToolResponse(error=f"invalid tool request: {detail}")
    return JSONResponse(status_code=200, content=response.model_dump())


@app.get("/", response_class=HTMLResponse)
async def root() -> str:
    return """
    <!DOCTYPE html>
    <html>
      <head>
        <title>Omi CoinGecko Crypto Integration</title>
        <style>
          body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 720px; margin: 40px auto; padding: 0 20px; line-height: 1.6; color: #1e293b; }
          h1 { color: #0f172a; margin-bottom: 8px; }
          code { background: #f1f5f9; padding: 2px 6px; border-radius: 4px; font-size: 0.9em; }
          .badge { display: inline-block; background: #22c55e; color: white; padding: 3px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: bold; }
          ul { padding-left: 20px; }
          li { margin-bottom: 8px; }
          a { color: #2563eb; text-decoration: none; }
          a:hover { text-decoration: underline; }
        </style>
      </head>
      <body>
        <h1>Omi CoinGecko Crypto Integration <span class="badge">ONLINE</span></h1>
        <p>Real-time digital currency quotes, trending coin tracking, and crypto market analytics for Omi voice assistants.</p>
        <h2>Available Tools</h2>
        <ul>
          <li><code>/tools/get_crypto_price</code> — Live price, 24h change, volume, and market cap for requested assets.</li>
          <li><code>/tools/search_crypto_coins</code> — Search CoinGecko's global database by ticker or name.</li>
          <li><code>/tools/get_trending_crypto</code> — Discover the most searched cryptocurrencies worldwide.</li>
          <li><code>/tools/get_crypto_market_overview</code> — Top coins ranked by global market capitalization.</li>
        </ul>
        <p><a href="/.well-known/omi-tools.json">View Omi Tool Manifest</a> | <a href="/health">Health Check</a></p>
      </body>
    </html>
    """


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok", "service": "omi-coingecko-crypto-app"}


@app.get("/.well-known/omi-tools.json")
async def omi_tools() -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "name": "CoinGecko Crypto & Market Intelligence",
        "description": "Live cryptocurrency prices, token searches, trending coins, and market analytics for Omi.",
        "tools": [
            {
                "name": "get_crypto_price",
                "description": "Get current price, 24-hour percentage change, 24-hour volume, and market cap for one or more cryptocurrencies (e.g. bitcoin, ethereum, solana).",
                "endpoint": "/tools/get_crypto_price",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "coin_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of CoinGecko coin IDs (e.g. ['bitcoin', 'ethereum', 'solana']).",
                        },
                        "vs_currency": {
                            "type": "string",
                            "default": "usd",
                            "description": "Currency to price against (e.g. 'usd', 'eur', 'gbp', 'jpy').",
                        },
                    },
                    "required": ["coin_ids"],
                },
            },
            {
                "name": "search_crypto_coins",
                "description": "Search for cryptocurrency coins by name, symbol, or keyword to find their CoinGecko ID and market rank.",
                "endpoint": "/tools/search_crypto_coins",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Coin ticker symbol or name to search (e.g. 'sol', 'pepe', 'doge').",
                        },
                        "max_results": {
                            "type": "integer",
                            "default": 5,
                            "minimum": 1,
                            "maximum": 15,
                            "description": "Maximum number of results to return.",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "get_trending_crypto",
                "description": "Fetch top trending search cryptocurrencies globally on CoinGecko over the last 24 hours.",
                "endpoint": "/tools/get_trending_crypto",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "default": 5,
                            "minimum": 1,
                            "maximum": 15,
                            "description": "Number of trending coins to return.",
                        }
                    },
                },
            },
            {
                "name": "get_crypto_market_overview",
                "description": "Get an overview of top global cryptocurrencies ordered by market capitalization.",
                "endpoint": "/tools/get_crypto_market_overview",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "default": 10,
                            "minimum": 1,
                            "maximum": 20,
                            "description": "Number of top coins to return.",
                        },
                        "vs_currency": {
                            "type": "string",
                            "default": "usd",
                            "description": "Fiat currency to display (default: 'usd').",
                        },
                    },
                },
            },
        ],
    }


@app.post("/tools/get_crypto_price", response_model=ChatToolResponse)
async def get_crypto_price(req: GetCryptoPriceRequest) -> ChatToolResponse:
    try:
        vs = req.vs_currency
        coin_ids_str = ",".join(req.coin_ids)
        params = {
            "ids": coin_ids_str,
            "vs_currencies": vs,
            "include_market_cap": "true",
            "include_24hr_vol": "true",
            "include_24hr_change": "true",
        }
        data = await _fetch_coingecko("/simple/price", params=params)

        if not data:
            return ChatToolResponse(
                error=f"No pricing data found for '{coin_ids_str}'. Please verify the coin IDs using the search tool."
            )

        currency_symbol = _get_currency_symbol(vs)
        lines = [f"Cryptocurrency Prices ({vs.upper()}):"]

        for coin_id in req.coin_ids:
            coin_data = data.get(coin_id)
            if not coin_data:
                lines.append(f"- {coin_id}: Not found (try searching with search_crypto_coins)")
                continue

            price = coin_data.get(vs)
            change_24h = coin_data.get(f"{vs}_24h_change")
            mcap = coin_data.get(f"{vs}_market_cap")
            vol_24h = coin_data.get(f"{vs}_24h_vol")

            formatted_price = _format_currency(price, currency_symbol)
            formatted_change = _format_percentage(change_24h)
            formatted_mcap = _format_compact(mcap, currency_symbol)
            formatted_vol = _format_compact(vol_24h, currency_symbol)

            display_name = coin_id.replace("-", " ").title()
            lines.append(
                f"- {display_name} ({coin_id}): {formatted_price} | 24h: {formatted_change} | "
                f"24h Vol: {formatted_vol} | MCap: {formatted_mcap}"
            )

        return ChatToolResponse(result="\n".join(lines))
    except ValueError as exc:
        return ChatToolResponse(error=str(exc))
    except Exception as exc:
        return ChatToolResponse(error=f"Unexpected error fetching crypto prices: {exc}")


@app.post("/tools/search_crypto_coins", response_model=ChatToolResponse)
async def search_crypto_coins(req: SearchCryptoCoinsRequest) -> ChatToolResponse:
    try:
        data = await _fetch_coingecko("/search", params={"query": req.query})
        coins = data.get("coins", [])

        if not coins:
            return ChatToolResponse(result=f"No cryptocurrency coins matched query '{req.query}'.")

        selected = coins[: req.max_results]
        lines = [f"Cryptocurrency search results for '{req.query}':"]

        for idx, coin in enumerate(selected, 1):
            name = coin.get("name", "Unknown")
            symbol = coin.get("symbol", "").upper()
            coin_id = coin.get("id", "")
            rank = coin.get("market_cap_rank")
            rank_str = f"Rank #{rank}" if rank else "Unranked"

            lines.append(f"{idx}. {name} ({symbol}) - {rank_str} | ID: {coin_id}")

        return ChatToolResponse(result="\n".join(lines))
    except ValueError as exc:
        return ChatToolResponse(error=str(exc))
    except Exception as exc:
        return ChatToolResponse(error=f"Unexpected error searching crypto coins: {exc}")


@app.post("/tools/get_trending_crypto", response_model=ChatToolResponse)
async def get_trending_crypto(req: GetTrendingCryptoRequest) -> ChatToolResponse:
    try:
        data = await _fetch_coingecko("/search/trending")
        trending_items = data.get("coins", [])

        if not trending_items:
            return ChatToolResponse(result="No trending coins available right now.")

        selected = trending_items[: req.limit]
        lines = ["Top Trending Cryptocurrencies on CoinGecko:"]

        for idx, item_wrapper in enumerate(selected, 1):
            item = item_wrapper.get("item", {})
            name = item.get("name", "Unknown")
            symbol = item.get("symbol", "").upper()
            coin_id = item.get("id", "")
            rank = item.get("market_cap_rank")
            rank_str = f"Rank #{rank}" if rank else "Unranked"

            # Check price in BTC if available
            price_btc = item.get("price_btc")
            btc_str = f" | {price_btc:.8f} BTC" if price_btc else ""

            lines.append(f"{idx}. {name} ({symbol}) - {rank_str}{btc_str} | ID: {coin_id}")

        return ChatToolResponse(result="\n".join(lines))
    except ValueError as exc:
        return ChatToolResponse(error=str(exc))
    except Exception as exc:
        return ChatToolResponse(error=f"Unexpected error retrieving trending crypto: {exc}")


@app.post("/tools/get_crypto_market_overview", response_model=ChatToolResponse)
async def get_crypto_market_overview(req: GetCryptoMarketOverviewRequest) -> ChatToolResponse:
    try:
        vs = req.vs_currency
        params = {
            "vs_currency": vs,
            "order": "market_cap_desc",
            "per_page": req.limit,
            "page": 1,
            "sparkline": "false",
            "price_change_percentage": "24h",
        }
        markets = await _fetch_coingecko("/coins/markets", params=params)

        if not markets:
            return ChatToolResponse(error="Failed to retrieve cryptocurrency market rankings.")

        currency_symbol = _get_currency_symbol(vs)
        lines = [f"Top {len(markets)} Cryptocurrencies by Market Cap ({vs.upper()}):"]

        for coin in markets:
            rank = coin.get("market_cap_rank", "-")
            name = coin.get("name", "Unknown")
            symbol = coin.get("symbol", "").upper()
            price = coin.get("current_price")
            change = coin.get("price_change_percentage_24h")
            mcap = coin.get("market_cap")

            formatted_price = _format_currency(price, currency_symbol)
            formatted_change = _format_percentage(change)
            formatted_mcap = _format_compact(mcap, currency_symbol)

            lines.append(f"{rank}. {name} ({symbol}): {formatted_price} (24h: {formatted_change}) | MCap: {formatted_mcap}")

        return ChatToolResponse(result="\n".join(lines))
    except ValueError as exc:
        return ChatToolResponse(error=str(exc))
    except Exception as exc:
        return ChatToolResponse(error=f"Unexpected error retrieving market overview: {exc}")
