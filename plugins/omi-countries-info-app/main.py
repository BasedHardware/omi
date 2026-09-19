"""
REST Countries & Global World Info Integration App for Omi.

Provides real-time country profiles, demographics, capitals, currencies,
official languages, timezones, and borders via the public REST Countries v3.1 API.
"""

from contextlib import asynccontextmanager
import html
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

try:
    from models import (
        CapitalSearchRequest,
        ChatToolResponse,
        CountryOverviewRequest,
        CurrencySearchRequest,
        LanguageSearchRequest,
    )
except ImportError:
    from .models import (
        CapitalSearchRequest,
        ChatToolResponse,
        CountryOverviewRequest,
        CurrencySearchRequest,
        LanguageSearchRequest,
    )

REST_COUNTRIES_BASE_URL = "https://restcountries.com/v3.1"
REQUEST_TIMEOUT_SECONDS = 10.0


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers={"User-Agent": "Omi-Countries-Plugin/1.0"},
    ) as client:
        app_instance.state.http_client = client
        yield


app = FastAPI(
    title="Omi REST Countries Integration",
    description="Look up country profiles, capitals, currencies, demographics, and languages in Omi chat.",
    version="1.0.0",
    lifespan=lifespan,
)


def _format_population(pop: Any) -> str:
    if isinstance(pop, (int, float)):
        return f"{int(pop):,}"
    return "Unknown"


def _format_currencies(currencies_dict: Any) -> str:
    if not isinstance(currencies_dict, dict) or not currencies_dict:
        return "Not available"
    formatted = []
    for code, details in currencies_dict.items():
        if isinstance(details, dict):
            name = details.get("name", code)
            symbol = details.get("symbol")
            if symbol:
                formatted.append(f"{name} ({symbol}, {code})")
            else:
                formatted.append(f"{name} ({code})")
        else:
            formatted.append(str(code))
    return ", ".join(formatted)


def _format_languages(lang_dict: Any) -> str:
    if not isinstance(lang_dict, dict) or not lang_dict:
        return "Not available"
    return ", ".join(str(v) for v in lang_dict.values() if v)


def _format_country_profile(c: Dict[str, Any]) -> str:
    """Format a detailed country dictionary into clean Markdown."""
    name_obj = c.get("name") if isinstance(c.get("name"), dict) else {}
    common_name = name_obj.get("common") or "Unknown Country"
    official_name = name_obj.get("official") or common_name
    flag = c.get("flag", "🌐")

    capitals = c.get("capital")
    if isinstance(capitals, list) and capitals:
        capital_str = ", ".join(str(cap) for cap in capitals)
    else:
        capital_str = "None"

    region = c.get("region", "Unknown")
    subregion = c.get("subregion", "")
    region_str = f"{region} ({subregion})" if subregion else region

    population_str = _format_population(c.get("population"))
    currencies_str = _format_currencies(c.get("currencies"))
    languages_str = _format_languages(c.get("languages"))

    timezones = c.get("timezones")
    if isinstance(timezones, list) and timezones:
        tz_str = ", ".join(str(tz) for tz in timezones[:4])
        if len(timezones) > 4:
            tz_str += f" (+{len(timezones) - 4} more)"
    else:
        tz_str = "Unknown"

    borders = c.get("borders")
    if isinstance(borders, list) and borders:
        borders_str = ", ".join(str(b) for b in borders)
    else:
        borders_str = "None (Island / Territory)"

    maps = c.get("maps") if isinstance(c.get("maps"), dict) else {}
    google_maps = maps.get("googleMaps", "")

    lines = [
        f"### {flag} {common_name}",
        f"**Official Name**: {official_name}",
        f"- **Capital**: {capital_str}",
        f"- **Region**: {region_str}",
        f"- **Population**: {population_str}",
        f"- **Currencies**: {currencies_str}",
        f"- **Official Languages**: {languages_str}",
        f"- **Borders**: {borders_str}",
        f"- **Timezones**: {tz_str}",
    ]

    if google_maps:
        lines.append(f"- **Map**: [Google Maps]({google_maps})")

    return "\n".join(lines)


async def _query_rest_countries(
    endpoint_path: str,
    client: Optional[httpx.AsyncClient] = None,
) -> Any:
    """Execute async request against REST Countries API."""
    url = f"{REST_COUNTRIES_BASE_URL}/{endpoint_path.lstrip('/')}"
    should_close = False
    if client is None:
        client = getattr(app.state, "http_client", None)
    if client is None:
        client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS)
        should_close = True

    try:
        response = await client.get(url)
        if response.status_code == 404:
            return {"not_found": True, "status_code": 404}
        response.raise_for_status()
        data = response.json()
        return data
    except httpx.TimeoutException:
        return {"error": "REST Countries request timed out. Please try again."}
    except httpx.HTTPStatusError as e:
        return {"error": f"REST Countries API error (HTTP {e.response.status_code}): {e.response.text[:200]}"}
    except Exception as e:
        return {"error": f"Failed to connect to REST Countries service: {str(e)}"}
    finally:
        if should_close:
            await client.aclose()


@app.get("/", response_class=HTMLResponse)
async def index():
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>REST Countries & World Info for Omi</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; line-height: 1.6; color: #333; }
        h1 { color: #0284c7; }
        .card { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; margin-bottom: 20px; }
        code { background: #e2e8f0; padding: 2px 6px; border-radius: 4px; font-size: 0.9em; }
        .endpoint { font-weight: bold; color: #0369a1; }
    </style>
</head>
<body>
    <h1>🌍 REST Countries & World Info for Omi</h1>
    <p>Provides country profiles, capitals, demographics, currencies, languages, timezones, and borders to Omi chat.</p>

    <div class="card">
        <h3>Available Chat Tools</h3>
        <ul>
            <li><span class="endpoint">POST /tools/country_overview</span> — Full country profile by name or code.</li>
            <li><span class="endpoint">POST /tools/search_by_capital</span> — Identify country by capital city.</li>
            <li><span class="endpoint">POST /tools/search_by_currency</span> — List countries using a currency.</li>
            <li><span class="endpoint">POST /tools/search_by_language</span> — List countries speaking a language.</li>
        </ul>
    </div>

    <div class="card">
        <h3>Metadata & Setup</h3>
        <p><a href="/manifest.json">Omi App Manifest</a> | <a href="/.well-known/ai-plugin.json">AI Plugin Spec</a> | <a href="/health">Health Check</a> | <a href="/privacy">Privacy</a></p>
    </div>
</body>
</html>"""


@app.get("/health")
async def health():
    return {"status": "ok", "service": "omi-countries-info-app"}


@app.get("/privacy")
async def privacy():
    return {
        "privacy_policy": "Omi REST Countries Integration does not collect, store, or log any personal user information."
    }


@app.get("/manifest.json")
@app.get("/.well-known/ai-plugin.json")
async def plugin_manifest():
    return {
        "schema_version": "v1",
        "name_for_human": "Countries & World Info",
        "name_for_model": "countries_world_info",
        "description_for_human": "Instant country profiles, capitals, currencies, demographics, and languages.",
        "description_for_model": "Look up comprehensive facts on world countries, capitals, populations, currencies, and official languages.",
        "auth": {"type": "none"},
        "api": {
            "type": "openapi",
            "url": "/openapi.json"
        },
        "logo_url": "https://restcountries.com/assets/world.svg",
        "contact_email": "support@omi.me",
        "legal_info_url": "/privacy"
    }


@app.post("/tools/country_overview", response_model=ChatToolResponse)
async def country_overview(req: CountryOverviewRequest):
    """Retrieve detailed country profile by name or ISO code."""
    query = req.country.strip()
    # If 2 or 3 letters, try alpha code first
    if len(query) in (2, 3) and query.isalpha():
        data = await _query_rest_countries(f"alpha/{quote(query)}")
        if isinstance(data, list) and data:
            return ChatToolResponse(result=_format_country_profile(data[0]))
        elif isinstance(data, dict) and data.get("name"):
            return ChatToolResponse(result=_format_country_profile(data))

    # Name search
    data = await _query_rest_countries(f"name/{quote(query)}")
    if isinstance(data, dict) and data.get("error"):
        return ChatToolResponse(error=data["error"])
    if (isinstance(data, dict) and data.get("not_found")) or not isinstance(data, list) or not data:
        return ChatToolResponse(result=f"No country found matching '{req.country}'.")

    return ChatToolResponse(result=_format_country_profile(data[0]))


@app.post("/tools/search_by_capital", response_model=ChatToolResponse)
async def search_by_capital(req: CapitalSearchRequest):
    """Find country associated with a capital city."""
    capital = req.capital.strip()
    data = await _query_rest_countries(f"capital/{quote(capital)}")
    if isinstance(data, dict) and data.get("error"):
        return ChatToolResponse(error=data["error"])
    if (isinstance(data, dict) and data.get("not_found")) or not isinstance(data, list) or not data:
        return ChatToolResponse(result=f"No country found with capital city '{req.capital}'.")

    results = []
    for c in data[:3]:
        results.append(_format_country_profile(c))

    return ChatToolResponse(result="\n\n---\n\n".join(results))


@app.post("/tools/search_by_currency", response_model=ChatToolResponse)
async def search_by_currency(req: CurrencySearchRequest):
    """List countries using a specific currency."""
    currency = req.currency.strip()
    data = await _query_rest_countries(f"currency/{quote(currency)}")
    if isinstance(data, dict) and data.get("error"):
        return ChatToolResponse(error=data["error"])
    if (isinstance(data, dict) and data.get("not_found")) or not isinstance(data, list) or not data:
        return ChatToolResponse(result=f"No countries found using currency '{req.currency}'.")

    limit = req.limit or 10
    countries = data[:limit]
    lines = [f"### Countries using currency '{req.currency}' ({len(data)} total):", ""]
    for c in countries:
        name_obj = c.get("name") if isinstance(c.get("name"), dict) else {}
        name = name_obj.get("common", "Unknown")
        flag = c.get("flag", "🌐")
        pop = _format_population(c.get("population"))
        region = c.get("region", "")
        lines.append(f"- {flag} **{name}** ({region}) — Pop: {pop}")

    if len(data) > limit:
        lines.append(f"\n_...and {len(data) - limit} more countries._")

    return ChatToolResponse(result="\n".join(lines))


@app.post("/tools/search_by_language", response_model=ChatToolResponse)
async def search_by_language(req: LanguageSearchRequest):
    """List countries where a specific language is officially spoken."""
    language = req.language.strip()
    data = await _query_rest_countries(f"lang/{quote(language)}")
    if isinstance(data, dict) and data.get("error"):
        return ChatToolResponse(error=data["error"])
    if (isinstance(data, dict) and data.get("not_found")) or not isinstance(data, list) or not data:
        return ChatToolResponse(result=f"No countries found with official language '{req.language}'.")

    limit = req.limit or 10
    countries = data[:limit]
    lines = [f"### Countries speaking '{req.language}' ({len(data)} total):", ""]
    for c in countries:
        name_obj = c.get("name") if isinstance(c.get("name"), dict) else {}
        name = name_obj.get("common", "Unknown")
        flag = c.get("flag", "🌐")
        capitals = c.get("capital")
        cap_str = capitals[0] if (isinstance(capitals, list) and capitals) else "N/A"
        pop = _format_population(c.get("population"))
        lines.append(f"- {flag} **{name}** (Capital: {cap_str}) — Pop: {pop}")

    if len(data) > limit:
        lines.append(f"\n_...and {len(data) - limit} more countries._")

    return ChatToolResponse(result="\n".join(lines))
