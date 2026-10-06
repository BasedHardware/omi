"""REST Countries & Global Geographic Intelligence Integration App for Omi.

Provides comprehensive country profiles, capital lookups, border analyses,
currency/language discovery, and demographic comparisons for Omi AI wearable users.
Operates with zero external tokens, OAuth, or API keys required.
"""

from collections import OrderedDict
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse

from data import (
    BY_CCA3,
    COUNTRIES_DB,
    find_country,
    search_by_capital_city,
    search_by_currency_code,
    search_by_language_name,
)
from models import (
    ChatToolResponse,
    CompareCountriesRequest,
    GetBorderCountriesRequest,
    GetCountryInfoRequest,
    SearchByCapitalRequest,
    SearchByCurrencyRequest,
    SearchByLanguageRequest,
)

logger = logging.getLogger("omi-restcountries-app")


# ---------------------------------------------------------------------------
# In-Memory Bounded LRU Cache with TTL
# ---------------------------------------------------------------------------
class SimpleTTLCache:
    """Thread-safe, bounded LRU cache with expiration."""

    def __init__(self, maxsize: int = 512, ttl_seconds: int = 3600):
        self.maxsize = maxsize
        self.ttl = ttl_seconds
        self._cache: OrderedDict[str, Tuple[float, Any]] = OrderedDict()

    def get(self, key: str) -> Optional[Any]:
        if key not in self._cache:
            return None
        created_at, value = self._cache[key]
        if time.time() - created_at > self.ttl:
            del self._cache[key]
            return None
        self._cache.move_to_end(key)
        return value

    def set(self, key: str, value: Any) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = (time.time(), value)
        if len(self._cache) > self.maxsize:
            self._cache.popitem(last=False)

    def clear(self) -> None:
        self._cache.clear()


app_cache = SimpleTTLCache(maxsize=512, ttl_seconds=3600)


# ---------------------------------------------------------------------------
# FastAPI App Setup
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Omi REST Countries & Geographic Intelligence",
    description="Global country profiles, capitals, currencies, and border intelligence for Omi AI wearables.",
    version="1.0.0",
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    first_error = exc.errors()[0] if exc.errors() else {}
    location = ".".join(str(part) for part in first_error.get("loc", []) if part != "body")
    message = first_error.get("msg", "invalid request")
    detail = f"{location}: {message}" if location else message
    response = ChatToolResponse(error=f"Invalid tool request: {detail}")
    return JSONResponse(status_code=200, content=response.model_dump(exclude_none=True))


# ---------------------------------------------------------------------------
# Voice-Friendly Formatting Helpers
# ---------------------------------------------------------------------------
def _format_country_profile(c: Dict[str, Any]) -> str:
    """Format a country dict into a concise wearable prompt."""
    name = c["name"]
    official = c.get("official_name", name)
    flag = c.get("flag", "🌐")
    capital = c.get("capital", "N/A")
    region = c.get("region", "Global")
    subregion = c.get("subregion", "")
    pop = f"{c.get('population', 0):,}"
    area = f"{c.get('area_sq_km', 0):,} km²"
    cca2 = c.get("cca2", "")
    cca3 = c.get("cca3", "")

    # Currencies
    curr_items = []
    for code, info in c.get("currencies", {}).items():
        sym = f" ({info.get('symbol', '')})" if info.get("symbol") else ""
        curr_items.append(f"{info.get('name', code)}{sym} [{code}]")
    currencies_str = ", ".join(curr_items) or "None"

    # Languages
    langs_str = ", ".join(c.get("languages", {}).values()) or "None"

    # Borders
    border_codes = c.get("borders", [])
    if border_codes:
        border_names = [BY_CCA3[b]["name"] for b in border_codes if b in BY_CCA3]
        borders_str = f"{len(border_codes)} neighboring countries: {', '.join(border_names[:6])}"
        if len(border_names) > 6:
            borders_str += f" and {len(border_names) - 6} more"
    else:
        borders_str = "Island / no land borders"

    demonym = c.get("demonym", "Resident")

    lines = [
        f"{flag} **{name}** ({official})",
        f"• **Capital:** {capital}",
        f"• **Region:** {region} ({subregion})",
        f"• **Population:** {pop} (Demonym: {demonym})",
        f"• **Area:** {area}",
        f"• **Currency:** {currencies_str}",
        f"• **Languages:** {langs_str}",
        f"• **Borders:** {borders_str}",
        f"• **ISO Codes:** {cca2} / {cca3}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool Endpoints
# ---------------------------------------------------------------------------
@app.post("/tools/get_country_info", response_model=ChatToolResponse, response_model_exclude_none=True)
async def get_country_info(request: GetCountryInfoRequest) -> ChatToolResponse:
    """Retrieve detailed country facts including capital, population, currency, languages, and region."""
    cache_key = f"country:{request.country.lower()}"
    cached = app_cache.get(cache_key)
    if cached:
        return ChatToolResponse(result=cached)

    country = find_country(request.country)
    if not country:
        return ChatToolResponse(
            error=f"Country '{request.country}' not found. Please check the spelling or provide an ISO code (e.g. 'FR', 'USA', 'Japan')."
        )

    formatted = _format_country_profile(country)
    app_cache.set(cache_key, formatted)
    return ChatToolResponse(result=formatted)


@app.post("/tools/search_by_capital", response_model=ChatToolResponse, response_model_exclude_none=True)
async def search_by_capital(request: SearchByCapitalRequest) -> ChatToolResponse:
    """Look up which country has a specific capital city (e.g. 'Paris', 'Canberra', 'Tokyo')."""
    cache_key = f"capital:{request.capital.lower()}"
    cached = app_cache.get(cache_key)
    if cached:
        return ChatToolResponse(result=cached)

    matches = search_by_capital_city(request.capital)
    if not matches:
        return ChatToolResponse(
            error=f"No country found with capital city matching '{request.capital}'. Please verify spelling."
        )

    results_lines = []
    for c in matches:
        flag = c.get("flag", "🌐")
        name = c.get("name", "")
        cap = c.get("capital", "")
        region = c.get("region", "")
        pop = f"{c.get('population', 0):,}"
        results_lines.append(f"{flag} **{cap}** is the capital of **{name}** ({region}, population {pop}).")

    result_str = "\n".join(results_lines)
    app_cache.set(cache_key, result_str)
    return ChatToolResponse(result=result_str)


@app.post("/tools/get_border_countries", response_model=ChatToolResponse, response_model_exclude_none=True)
async def get_border_countries(request: GetBorderCountriesRequest) -> ChatToolResponse:
    """Discover neighboring countries sharing land borders with a specific country."""
    cache_key = f"borders:{request.country.lower()}"
    cached = app_cache.get(cache_key)
    if cached:
        return ChatToolResponse(result=cached)

    country = find_country(request.country)
    if not country:
        return ChatToolResponse(
            error=f"Country '{request.country}' not found. Please verify spelling or ISO code."
        )

    name = country["name"]
    flag = country.get("flag", "🌐")
    border_codes = country.get("borders", [])

    if not border_codes:
        result_str = f"{flag} **{name}** has no land borders (island nation or territory)."
        app_cache.set(cache_key, result_str)
        return ChatToolResponse(result=result_str)

    neighbor_profiles = []
    for b in border_codes:
        neighbor = BY_CCA3.get(b)
        if neighbor:
            n_flag = neighbor.get("flag", "")
            n_name = neighbor["name"]
            n_cap = neighbor.get("capital", "N/A")
            neighbor_profiles.append(f"• {n_flag} **{n_name}** (Capital: {n_cap}, Code: {b})")
        else:
            neighbor_profiles.append(f"• Code: {b}")

    result_str = (
        f"{flag} **{name}** shares land borders with {len(border_codes)} countries:\n"
        + "\n".join(neighbor_profiles)
    )
    app_cache.set(cache_key, result_str)
    return ChatToolResponse(result=result_str)


@app.post("/tools/search_by_currency", response_model=ChatToolResponse, response_model_exclude_none=True)
async def search_by_currency(request: SearchByCurrencyRequest) -> ChatToolResponse:
    """Find countries that use a specific currency (e.g. 'EUR', 'USD', 'Pound', 'Yen', 'Franc')."""
    cache_key = f"curr:{request.currency.lower()}"
    cached = app_cache.get(cache_key)
    if cached:
        return ChatToolResponse(result=cached)

    matches = search_by_currency_code(request.currency)
    if not matches:
        return ChatToolResponse(
            error=f"No countries found using currency '{request.currency}'. Try standard codes like EUR, USD, JPY, GBP, or CAD."
        )

    lines = [f"💰 Found {len(matches)} countries using currency matching '{request.currency}':"]
    for c in matches:
        flag = c.get("flag", "🌐")
        name = c.get("name", "")
        curr_details = []
        for code, details in c.get("currencies", {}).items():
            sym = details.get("symbol", "")
            curr_details.append(f"{code} ({sym})" if sym else code)
        lines.append(f"• {flag} **{name}** — {', '.join(curr_details)}")

    result_str = "\n".join(lines)
    app_cache.set(cache_key, result_str)
    return ChatToolResponse(result=result_str)


@app.post("/tools/search_by_language", response_model=ChatToolResponse, response_model_exclude_none=True)
async def search_by_language(request: SearchByLanguageRequest) -> ChatToolResponse:
    """Find countries where a specific language is spoken (e.g. 'Spanish', 'French', 'Arabic', 'German')."""
    cache_key = f"lang:{request.language.lower()}"
    cached = app_cache.get(cache_key)
    if cached:
        return ChatToolResponse(result=cached)

    matches = search_by_language_name(request.language)
    if not matches:
        return ChatToolResponse(
            error=f"No countries found where '{request.language}' is registered as an official or major language."
        )

    lines = [f"🗣️ Found {len(matches)} countries where '{request.language}' is spoken:"]
    for c in matches:
        flag = c.get("flag", "🌐")
        name = c.get("name", "")
        region = c.get("region", "")
        cap = c.get("capital", "")
        lines.append(f"• {flag} **{name}** ({region}, Capital: {cap})")

    result_str = "\n".join(lines)
    app_cache.set(cache_key, result_str)
    return ChatToolResponse(result=result_str)


@app.post("/tools/compare_countries", response_model=ChatToolResponse, response_model_exclude_none=True)
async def compare_countries(request: CompareCountriesRequest) -> ChatToolResponse:
    """Compare population, area, region, and capitals between two nations."""
    ca = find_country(request.country_a)
    if not ca:
        return ChatToolResponse(error=f"First country '{request.country_a}' not found.")

    cb = find_country(request.country_b)
    if not cb:
        return ChatToolResponse(error=f"Second country '{request.country_b}' not found.")

    name_a, name_b = ca["name"], cb["name"]
    flag_a, flag_b = ca.get("flag", "🌐"), cb.get("flag", "🌐")
    pop_a, pop_b = ca.get("population", 0), cb.get("population", 0)
    area_a, area_b = ca.get("area_sq_km", 0), cb.get("area_sq_km", 0)

    # Population comparison
    if pop_a > pop_b:
        pop_line = f"  ↳ {name_a} has {pop_a - pop_b:,} more residents."
    elif pop_b > pop_a:
        pop_line = f"  ↳ {name_b} has {pop_b - pop_a:,} more residents."
    else:
        pop_line = f"  ↳ Both countries have equal population ({pop_a:,})."

    # Area comparison
    if area_a > area_b:
        area_line = f"  ↳ {name_a} is larger by {area_a - area_b:,.1f} km²."
    elif area_b > area_a:
        area_line = f"  ↳ {name_b} is larger by {area_b - area_a:,.1f} km²."
    else:
        area_line = f"  ↳ Both countries have equal land area ({area_a:,.1f} km²)."

    comparison_lines = [
        f"📊 **Comparison: {flag_a} {name_a} vs {flag_b} {name_b}**\n",
        f"• **Population:** {pop_a:,} vs {pop_b:,}",
        pop_line,
        f"• **Area:** {area_a:,} km² vs {area_b:,} km²",
        area_line,
        f"• **Capital:** {ca.get('capital', 'N/A')} vs {cb.get('capital', 'N/A')}",
        f"• **Region:** {ca.get('region')} ({ca.get('subregion')}) vs {cb.get('region')} ({cb.get('subregion')})",
        f"• **Languages:** {', '.join(ca.get('languages', {}).values())} vs {', '.join(cb.get('languages', {}).values())}",
    ]
    return ChatToolResponse(result="\n".join(comparison_lines))


# ---------------------------------------------------------------------------
# Health & Manifest Endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
async def health() -> Dict[str, Any]:
    """Health check endpoint."""
    return {"status": "ok", "service": "omi-restcountries-app", "version": "1.0.0"}


@app.get("/.well-known/omi-tools.json")
async def omi_tools() -> Dict[str, Any]:
    """Omi Function Calling Chat Tools Manifest."""
    return {
        "schema_version": "1.0",
        "auth": {"type": "none"},
        "tools": [
            {
                "name": "get_country_info",
                "description": "Look up comprehensive country profile including capital, population, currency, languages, and ISO codes.",
                "endpoint": "/tools/get_country_info",
                "method": "POST",
                "auth_required": False,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "country": {
                            "type": "string",
                            "description": "Country name, common alias, or ISO 2/3-letter code (e.g. 'France', 'USA', 'Japan', 'DEU').",
                        },
                    },
                    "required": ["country"],
                },
            },
            {
                "name": "search_by_capital",
                "description": "Find which country has a specific capital city (e.g. 'Paris', 'Canberra', 'Tokyo', 'Ottawa').",
                "endpoint": "/tools/search_by_capital",
                "method": "POST",
                "auth_required": False,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "capital": {
                            "type": "string",
                            "description": "Capital city name (e.g. 'Tokyo', 'Berlin', 'Buenos Aires').",
                        },
                    },
                    "required": ["capital"],
                },
            },
            {
                "name": "get_border_countries",
                "description": "Discover all neighboring countries sharing land borders with a given country.",
                "endpoint": "/tools/get_border_countries",
                "method": "POST",
                "auth_required": False,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "country": {
                            "type": "string",
                            "description": "Country name or ISO code (e.g. 'Germany', 'Brazil', 'Switzerland').",
                        },
                    },
                    "required": ["country"],
                },
            },
            {
                "name": "search_by_currency",
                "description": "Find all countries that use a specific currency (e.g. 'EUR', 'USD', 'Pound', 'Yen').",
                "endpoint": "/tools/search_by_currency",
                "method": "POST",
                "auth_required": False,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "currency": {
                            "type": "string",
                            "description": "Currency code or name (e.g. 'EUR', 'USD', 'Yen', 'Peso').",
                        },
                    },
                    "required": ["currency"],
                },
            },
            {
                "name": "search_by_language",
                "description": "Find all countries where a specific language is officially or widely spoken.",
                "endpoint": "/tools/search_by_language",
                "method": "POST",
                "auth_required": False,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "language": {
                            "type": "string",
                            "description": "Language name or code (e.g. 'Spanish', 'French', 'Arabic', 'Portuguese').",
                        },
                    },
                    "required": ["language"],
                },
            },
            {
                "name": "compare_countries",
                "description": "Compare population, geographic area, and key statistics between two countries.",
                "endpoint": "/tools/compare_countries",
                "method": "POST",
                "auth_required": False,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "country_a": {
                            "type": "string",
                            "description": "First country name or code (e.g. 'France').",
                        },
                        "country_b": {
                            "type": "string",
                            "description": "Second country name or code (e.g. 'Germany').",
                        },
                    },
                    "required": ["country_a", "country_b"],
                },
            },
        ],
    }


@app.get("/", response_class=HTMLResponse)
async def root():
    """Service landing page."""
    return HTMLResponse(
        """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Omi REST Countries & Geographic Intelligence App</title>
            <style>
                body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 720px; margin: 48px auto; padding: 0 16px; line-height: 1.6; color: #24292f; }
                h1 { font-size: 24px; color: #0969da; }
                code { background: #f6f8fa; padding: 2px 6px; border-radius: 4px; font-size: 14px; }
                ul { padding-left: 20px; }
            </style>
        </head>
        <body>
            <h1>🌍 Omi REST Countries & Geographic Intelligence</h1>
            <p>Instant world country profiles, capitals, currencies, languages, and border analysis for Omi AI wearables.</p>
            <h3>Registered Chat Tools:</h3>
            <ul>
                <li><code>get_country_info</code>: Detailed country facts and demographics.</li>
                <li><code>search_by_capital</code>: Look up country by capital city.</li>
                <li><code>get_border_countries</code>: Discover neighboring border nations.</li>
                <li><code>search_by_currency</code>: Find countries using a currency.</li>
                <li><code>search_by_language</code>: Find countries speaking a language.</li>
                <li><code>compare_countries</code>: Side-by-side demographic and geographic comparison.</li>
            </ul>
            <h3>Endpoints:</h3>
            <ul>
                <li><a href="/health"><code>GET /health</code></a>: Health check</li>
                <li><a href="/.well-known/omi-tools.json"><code>GET /.well-known/omi-tools.json</code></a>: Chat tools manifest</li>
            </ul>
        </body>
        </html>
        """
    )
