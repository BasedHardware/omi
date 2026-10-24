"""World Bank Global Economic & Country Intelligence Integration App for Omi.

Provides real-time macroeconomic indicators, national profiles, comparative economics,
and geopolitical discovery using the official World Bank Open Data API for Omi AI wearable users.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Tuple
import urllib.parse
import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse

from models import (
    COMMON_COUNTRY_ALIASES,
    INDICATOR_MAP,
    ChatToolResponse,
    CompareEconomiesRequest,
    CountryProfileRequest,
    EconomicIndicatorRequest,
    SearchCountriesRequest,
)

WORLD_BANK_BASE_URL = "https://api.worldbank.org/v2"
REQUEST_TIMEOUT_SECONDS = 15.0
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 (Omi-WorldBank-Integration/1.0)"
)

# Canonical country aliases derived from models as single source of truth
STATIC_COUNTRY_ALIASES: Dict[str, str] = COMMON_COUNTRY_ALIASES


# Map ISO-3 codes to canonical country display names
ISO3_TO_NAME: Dict[str, str] = {
    "USA": "United States",
    "GBR": "United Kingdom",
    "DEU": "Germany",
    "FRA": "France",
    "IND": "India",
    "CHN": "China",
    "JPN": "Japan",
    "KOR": "South Korea",
    "PRK": "North Korea",
    "RUS": "Russian Federation",
    "BRA": "Brazil",
    "CAN": "Canada",
    "AUS": "Australia",
    "MEX": "Mexico",
    "ITA": "Italy",
    "ESP": "Spain",
    "IDN": "Indonesia",
    "SAU": "Saudi Arabia",
    "TUR": "Turkiye",
    "TWN": "Taiwan",
    "NLD": "Netherlands",
    "CHE": "Switzerland",
    "SGP": "Singapore",
    "ARE": "United Arab Emirates",
    "ZAF": "South Africa",
    "ARG": "Argentina",
    "SWE": "Sweden",
    "POL": "Poland",
    "BEL": "Belgium",
    "NOR": "Norway",
    "IRL": "Ireland",
    "ISR": "Israel",
    "AUT": "Austria",
    "NGA": "Nigeria",
    "EGY": "Egypt",
    "VNM": "Vietnam",
    "PAK": "Pakistan",
    "BGD": "Bangladesh",
    "PHL": "Philippines",
    "MYS": "Malaysia",
    "THA": "Thailand",
    "NZL": "New Zealand",
    "CHL": "Chile",
    "COL": "Colombia",
    "PRT": "Portugal",
    "GRC": "Greece",
    "UKR": "Ukraine",
    "WLD": "World",
}


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    headers = {"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, headers=headers) as client:
        app_instance.state.http_client = client
        app_instance.state.country_cache = []
        try:
            # Pre-load country index from World Bank
            resp = await client.get(f"{WORLD_BANK_BASE_URL}/country?format=json&per_page=300")
            if resp.status_code == 200:
                data = resp.json()
                if len(data) > 1 and isinstance(data[1], list):
                    app_instance.state.country_cache = data[1]
        except Exception:
            # Fallback to static aliases if network fails at cold start
            pass
        yield


app = FastAPI(
    title="Omi World Bank Economic Intelligence",
    description="Real-time global macroeconomic data, country profiles, and comparative economic intelligence for Omi.",
    version="1.0.0",
    lifespan=lifespan,
)


def _format_compact(value: Optional[float], currency_prefix: str = "$") -> str:
    """Format large numbers into human-readable compact units (e.g. $30.77T, $4.20B, 1.43B)."""
    if value is None:
        return "N/A"
    abs_v = abs(value)
    if abs_v >= 1e12:
        return f"{currency_prefix}{value / 1e12:.2f}T"
    if abs_v >= 1e9:
        return f"{currency_prefix}{value / 1e9:.2f}B"
    if abs_v >= 1e6:
        return f"{currency_prefix}{value / 1e6:.2f}M"
    if abs_v >= 1e3:
        return f"{currency_prefix}{value / 1e3:.2f}K"
    return f"{currency_prefix}{value:,.2f}"


def _format_percent(value: Optional[float]) -> str:
    """Format percentage values."""
    if value is None:
        return "N/A"
    return f"{value:+.2f}%" if abs(value) >= 0.01 else f"{value:.2f}%"


def _get_http_client() -> httpx.AsyncClient:
    """Get persistent client from app.state or fallback client if invoked outside lifespan."""
    client = getattr(getattr(app, "state", None), "http_client", None)
    if client is None:
        client = httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json"},
        )
    return client


async def _resolve_country_code(query: str) -> Tuple[str, str]:
    """Resolve user input to canonical ISO-3 code and formal country name."""
    clean = query.strip().lower()
    if clean in STATIC_COUNTRY_ALIASES:
        iso3 = STATIC_COUNTRY_ALIASES[clean]
        name = ISO3_TO_NAME.get(iso3, iso3)
        return iso3, name

    # Check cached country list from World Bank if populated
    cached_countries: List[Dict[str, Any]] = getattr(getattr(app, "state", None), "country_cache", [])
    if cached_countries:
        # Pass 1: exact matches on ID, ISO-2, or full country name
        for c in cached_countries:
            c_id = c.get("id", "").strip().lower()
            c_iso2 = c.get("iso2Code", "").strip().lower()
            c_name = c.get("name", "").strip().lower()
            if clean in (c_id, c_iso2, c_name):
                iso3 = c.get("id", "").strip().upper()
                return iso3, c.get("name", iso3)

        # Pass 2: substring matches on non-aggregate countries
        matches = [
            c for c in cached_countries
            if clean in c.get("name", "").strip().lower()
            and c.get("region", {}).get("value") != "Aggregates"
        ]
        if len(matches) == 1:
            iso3 = matches[0].get("id", "").strip().upper()
            return iso3, matches[0].get("name", iso3)
        elif len(matches) > 1:
            match_names = ", ".join(m.get("name", "") for m in matches[:5])
            raise ValueError(
                f"Ambiguous country query '{query}'. Matches multiple countries: {match_names}. Please specify the full country name or ISO code."
            )

    # Fallback to direct World Bank API query for unmapped/uncached country codes
    client = _get_http_client()
    try:
        clean_encoded = urllib.parse.quote(clean)
        resp = await client.get(f"{WORLD_BANK_BASE_URL}/country/{clean_encoded}?format=json")
        if resp.status_code == 200:
            data = resp.json()
            if len(data) > 1 and isinstance(data[1], list) and len(data[1]) > 0:
                first = data[1][0]
                resolved_id = first.get("id", "").strip().upper()
                resolved_name = first.get("name", resolved_id)
                if resolved_id:
                    return resolved_id, resolved_name
    except Exception:
        pass

    # Check known ISO-3 codes
    clean_upper = clean.upper()
    if clean_upper in ISO3_TO_NAME:
        return clean_upper, ISO3_TO_NAME[clean_upper]

    raise ValueError(f"Could not resolve '{query}' to a recognized World Bank country or economic entity.")


async def _fetch_country_metadata(iso3: str) -> Dict[str, Any]:
    """Fetch country metadata (capital, region, income level, coordinates)."""
    client = _get_http_client()
    url = f"{WORLD_BANK_BASE_URL}/country/{iso3}?format=json"
    resp = await client.get(url)
    if resp.status_code == 200:
        data = resp.json()
        if len(data) > 1 and isinstance(data[1], list) and len(data[1]) > 0:
            return data[1][0]
    return {}


async def _fetch_indicator_value(iso3: str, indicator_code: str, mrv: int = 1) -> List[Dict[str, Any]]:
    """Fetch recent measurements for an indicator."""
    client = _get_http_client()
    url = f"{WORLD_BANK_BASE_URL}/country/{iso3}/indicator/{indicator_code}?format=json&mrv={mrv}"
    resp = await client.get(url)
    if resp.status_code == 200:
        data = resp.json()
        if len(data) > 1 and isinstance(data[1], list):
            # Filter valid measurements with non-null values
            return [d for d in data[1] if d.get("value") is not None]
    return []


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [f"{err['loc'][-1]}: {err['msg']}" for err in exc.errors()]
    return JSONResponse(
        status_code=200,
        content={"result": None, "error": f"Invalid request parameters: {'; '.join(errors)}"},
    )


@app.exception_handler(Exception)
async def global_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=200,
        content={"result": None, "error": f"Internal server error: {str(exc)}"},
    )


@app.get("/.well-known/omi-tools.json")
async def get_manifest():
    """Return Omi chat tool manifest for discovery and registration."""
    return {
        "schema_version": "v1",
        "name_for_model": "world_bank_economic_intelligence",
        "name_for_human": "World Bank Global Economic Intelligence",
        "description_for_model": (
            "Access real-time macroeconomic indicators, national economic profiles, comparative economic analyses, "
            "and country demographics directly from the official World Bank Open Data API. Supports GDP, GDP per capita, "
            "inflation, population, life expectancy, unemployment, and CO2 emissions across 200+ countries."
        ),
        "description_for_human": "Ask Omi about any country's GDP, inflation, population, economic profile, or compare national economies.",
        "contact_email": "support@omi.me",
        "legal_info_url": "https://www.worldbank.org/en/about/legal/terms-of-use-for-datasets",
        "tools": [
            {
                "name": "get_country_profile",
                "description": (
                    "Get a comprehensive macroeconomic and demographic profile for any country. Returns capital, "
                    "geographic region, World Bank income level classification, coordinates, latest GDP, GDP per capita, "
                    "annual inflation rate, total population, and life expectancy."
                ),
                "endpoint": "/tools/country-profile",
                "method": "POST",
                "auth_required": False,
                "status_message": "Fetching World Bank country economic profile...",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "country": {
                            "type": "string",
                            "description": "Country name, common alias, ISO-2, or ISO-3 code (e.g., 'United States', 'Germany', 'USA', 'DEU', 'India', 'Japan').",
                        }
                    },
                    "required": ["country"],
                },
            },
            {
                "name": "get_economic_indicator",
                "description": (
                    "Query a specific macroeconomic indicator for a nation, including optional multi-year trend history. "
                    "Supported indicators: 'gdp', 'gdp_per_capita', 'inflation', 'population', 'life_expectancy', 'unemployment', 'co2_emissions'."
                ),
                "endpoint": "/tools/economic-indicator",
                "method": "POST",
                "auth_required": False,
                "status_message": "Retrieving macroeconomic indicator from World Bank...",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "country": {
                            "type": "string",
                            "description": "Country name or ISO code (e.g. 'United States', 'Brazil', 'Germany').",
                        },
                        "indicator": {
                            "type": "string",
                            "description": "Economic indicator: 'gdp', 'gdp_per_capita', 'inflation', 'population', 'life_expectancy', 'unemployment', or 'co2_emissions'.",
                            "default": "gdp",
                        },
                        "years": {
                            "type": "integer",
                            "description": "Number of recent annual data points to show trajectory (1 to 10, default is 1).",
                            "default": 1,
                        },
                    },
                    "required": ["country"],
                },
            },
            {
                "name": "compare_country_economies",
                "description": (
                    "Perform a direct side-by-side comparative economic analysis between two countries. "
                    "Compares GDP, GDP per capita, population, inflation, life expectancy, and income bracket."
                ),
                "endpoint": "/tools/compare-economies",
                "method": "POST",
                "auth_required": False,
                "status_message": "Comparing national economies via World Bank...",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "country_a": {
                            "type": "string",
                            "description": "First country name or code (e.g., 'United States', 'USA').",
                        },
                        "country_b": {
                            "type": "string",
                            "description": "Second country name or code (e.g., 'China', 'CHN').",
                        },
                    },
                    "required": ["country_a", "country_b"],
                },
            },
            {
                "name": "search_countries_by_region",
                "description": (
                    "Discover and list countries belonging to a specific geographic region (e.g., 'Europe', 'East Asia', 'Latin America', 'South Asia') "
                    "or World Bank income bracket (e.g., 'High income', 'Upper middle income', 'Lower middle income')."
                ),
                "endpoint": "/tools/search-countries",
                "method": "POST",
                "auth_required": False,
                "status_message": "Searching World Bank country database...",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Optional search term for country name or capital city.",
                        },
                        "region": {
                            "type": "string",
                            "description": "Optional geographic region name.",
                        },
                        "income_level": {
                            "type": "string",
                            "description": "Optional income level classification ('High income', 'Upper middle income', etc.).",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of results to return (1-30, default 10).",
                            "default": 10,
                        },
                    },
                },
            },
        ],
    }


@app.post("/tools/country-profile", response_model=ChatToolResponse)
async def get_country_profile(payload: CountryProfileRequest) -> ChatToolResponse:
    """Fetch comprehensive country economic and demographic profile."""
    try:
        iso3, country_name = await _resolve_country_code(payload.country)

        # Run concurrent queries for metadata and core economic indicators
        meta_task = _fetch_country_metadata(iso3)
        gdp_task = _fetch_indicator_value(iso3, INDICATOR_MAP["gdp"], mrv=1)
        gdp_pc_task = _fetch_indicator_value(iso3, INDICATOR_MAP["gdp_per_capita"], mrv=1)
        inflation_task = _fetch_indicator_value(iso3, INDICATOR_MAP["inflation"], mrv=1)
        pop_task = _fetch_indicator_value(iso3, INDICATOR_MAP["population"], mrv=1)
        life_task = _fetch_indicator_value(iso3, INDICATOR_MAP["life_expectancy"], mrv=1)

        meta, gdp_data, gdp_pc_data, inf_data, pop_data, life_data = await asyncio.gather(
            meta_task, gdp_task, gdp_pc_task, inflation_task, pop_task, life_task
        )

        display_name = meta.get("name", country_name)
        capital = meta.get("capitalCity") or "N/A"
        region = meta.get("region", {}).get("value", "N/A").strip()
        income_level = meta.get("incomeLevel", {}).get("value", "N/A").strip()

        # Extract coordinates
        lat = str(meta.get("latitude") or "").strip()
        lon = str(meta.get("longitude") or "").strip()
        if lat and lon and lat.lower() != "n/a" and lon.lower() != "n/a":
            try:
                coords_str = f"Lat {float(lat):.2f}, Lon {float(lon):.2f}"
            except (ValueError, TypeError):
                coords_str = f"Lat {lat}, Lon {lon}"
        else:
            coords_str = "N/A"

        # Format indicator metrics
        gdp_str = f"{_format_compact(gdp_data[0]['value'])} ({gdp_data[0]['date']})" if gdp_data else "N/A"
        gdp_pc_str = f"{_format_compact(gdp_pc_data[0]['value'])} ({gdp_pc_data[0]['date']})" if gdp_pc_data else "N/A"
        inf_str = f"{_format_percent(inf_data[0]['value'])} ({inf_data[0]['date']})" if inf_data else "N/A"
        pop_str = f"{_format_compact(pop_data[0]['value'], '')} people ({pop_data[0]['date']})" if pop_data else "N/A"
        life_str = f"{life_data[0]['value']:.1f} years ({life_data[0]['date']})" if life_data else "N/A"

        lines = [
            f"🌍 Economic Profile: {display_name} ({iso3})",
            f"• Capital: {capital}",
            f"• Region: {region}",
            f"• Income Classification: {income_level}",
            f"• Coordinates: {coords_str}",
            "",
            "📊 Core Macroeconomic Indicators:",
            f"• GDP: {gdp_str}",
            f"• GDP Per Capita: {gdp_pc_str}",
            f"• Inflation Rate: {inf_str}",
            f"• Total Population: {pop_str}",
            f"• Life Expectancy: {life_str}",
        ]

        return ChatToolResponse(result="\n".join(lines))
    except ValueError as val_err:
        return ChatToolResponse(error=str(val_err))
    except Exception as exc:
        return ChatToolResponse(error=f"Failed to retrieve country profile: {str(exc)}")


@app.post("/tools/economic-indicator", response_model=ChatToolResponse)
async def get_economic_indicator(payload: EconomicIndicatorRequest) -> ChatToolResponse:
    """Fetch single indicator with optional historical trajectory."""
    try:
        iso3, country_name = await _resolve_country_code(payload.country)
        code = INDICATOR_MAP[payload.indicator]
        records = await _fetch_indicator_value(iso3, code, mrv=payload.years)

        if not records:
            return ChatToolResponse(
                error=f"No data available from the World Bank for indicator '{payload.indicator}' in {country_name} ({iso3})."
            )

        indicator_title = records[0].get("indicator", {}).get("value", payload.indicator.upper())
        lines = [f"📈 {indicator_title} for {country_name} ({iso3}):"]

        # Sort chronologically for trend display
        records_sorted = sorted(records, key=lambda x: str(x.get("date", "")), reverse=True)

        for rec in records_sorted:
            year = rec.get("date")
            val = rec.get("value")
            if "GDP (current US$)" in indicator_title or payload.indicator in ("gdp", "gdp_usd"):
                formatted = _format_compact(val, "$")
            elif "per capita" in indicator_title.lower() or payload.indicator == "gdp_per_capita":
                formatted = f"${val:,.2f}"
            elif "inflation" in indicator_title.lower() or "unemployment" in indicator_title.lower() or payload.indicator in ("inflation", "unemployment"):
                formatted = _format_percent(val)
            elif "population" in indicator_title.lower() or payload.indicator == "population":
                formatted = f"{_format_compact(val, '')} people"
            elif "life expectancy" in indicator_title.lower() or payload.indicator == "life_expectancy":
                formatted = f"{val:.1f} years"
            else:
                formatted = f"{val:,.2f}"

            lines.append(f"• {year}: {formatted}")

        # If multi-year, append trajectory summary
        if len(records_sorted) >= 2:
            latest = records_sorted[0].get("value")
            prior = records_sorted[1].get("value")
            if latest is not None and prior is not None and prior != 0:
                delta = ((latest - prior) / abs(prior)) * 100
                trend_arrow = "🔺 Up" if delta > 0 else "🔻 Down" if delta < 0 else "➡️ Flat"
                lines.append(f"\nRecent Annual Change: {trend_arrow} {abs(delta):.2f}% from {records_sorted[1]['date']} to {records_sorted[0]['date']}")

        return ChatToolResponse(result="\n".join(lines))
    except ValueError as val_err:
        return ChatToolResponse(error=str(val_err))
    except Exception as exc:
        return ChatToolResponse(error=f"Failed to retrieve economic indicator: {str(exc)}")


@app.post("/tools/compare-economies", response_model=ChatToolResponse)
async def compare_country_economies(payload: CompareEconomiesRequest) -> ChatToolResponse:
    """Compare two nations side-by-side across major economic pillars."""
    try:
        if not getattr(payload, "country_a", None) or not getattr(payload, "country_b", None):
            return ChatToolResponse(error="Both 'country_a' and 'country_b' must be provided.")
        if payload.country_a.strip().lower() == payload.country_b.strip().lower():
            return ChatToolResponse(error="Cannot compare a country to itself. Please provide two distinct countries.")

        iso_a, name_a = await _resolve_country_code(payload.country_a)
        iso_b, name_b = await _resolve_country_code(payload.country_b)

        if iso_a == iso_b:
            return ChatToolResponse(
                error=f"Cannot compare a country to itself ('{payload.country_a}' and '{payload.country_b}' both resolve to {name_a} [{iso_a}]). Please provide two distinct countries."
            )

        # Concurrently fetch metadata and indicators for both countries
        task_meta_a = _fetch_country_metadata(iso_a)
        task_meta_b = _fetch_country_metadata(iso_b)

        task_gdp_a = _fetch_indicator_value(iso_a, INDICATOR_MAP["gdp"], mrv=1)
        task_gdp_b = _fetch_indicator_value(iso_b, INDICATOR_MAP["gdp"], mrv=1)

        task_gdp_pc_a = _fetch_indicator_value(iso_a, INDICATOR_MAP["gdp_per_capita"], mrv=1)
        task_gdp_pc_b = _fetch_indicator_value(iso_b, INDICATOR_MAP["gdp_per_capita"], mrv=1)

        task_pop_a = _fetch_indicator_value(iso_a, INDICATOR_MAP["population"], mrv=1)
        task_pop_b = _fetch_indicator_value(iso_b, INDICATOR_MAP["population"], mrv=1)

        task_inf_a = _fetch_indicator_value(iso_a, INDICATOR_MAP["inflation"], mrv=1)
        task_inf_b = _fetch_indicator_value(iso_b, INDICATOR_MAP["inflation"], mrv=1)

        task_life_a = _fetch_indicator_value(iso_a, INDICATOR_MAP["life_expectancy"], mrv=1)
        task_life_b = _fetch_indicator_value(iso_b, INDICATOR_MAP["life_expectancy"], mrv=1)

        (
            meta_a,
            meta_b,
            gdp_a,
            gdp_b,
            gdp_pc_a,
            gdp_pc_b,
            pop_a,
            pop_b,
            inf_a,
            inf_b,
            life_a,
            life_b,
        ) = await asyncio.gather(
            task_meta_a,
            task_meta_b,
            task_gdp_a,
            task_gdp_b,
            task_gdp_pc_a,
            task_gdp_pc_b,
            task_pop_a,
            task_pop_b,
            task_inf_a,
            task_inf_b,
            task_life_a,
            task_life_b,
        )

        display_a = meta_a.get("name", name_a)
        display_b = meta_b.get("name", name_b)

        gdp_val_a = gdp_a[0]["value"] if gdp_a else None
        gdp_val_b = gdp_b[0]["value"] if gdp_b else None

        gdp_pc_val_a = gdp_pc_a[0]["value"] if gdp_pc_a else None
        gdp_pc_val_b = gdp_pc_b[0]["value"] if gdp_pc_b else None

        pop_val_a = pop_a[0]["value"] if pop_a else None
        pop_val_b = pop_b[0]["value"] if pop_b else None

        inf_val_a = inf_a[0]["value"] if inf_a else None
        inf_val_b = inf_b[0]["value"] if inf_b else None

        life_val_a = f"{life_a[0]['value']:.1f} yrs" if life_a else "N/A"
        life_val_b = f"{life_b[0]['value']:.1f} yrs" if life_b else "N/A"

        lines = [
            f"⚖️ Economic Comparison: {display_a} vs {display_b}",
            f"{'Metric':<25} | {display_a[:15]:<15} | {display_b[:15]:<15}",
            f"{'-'*25}-|-{'-'*15}-|-{'-'*15}",
            f"{'Income Level':<25} | {meta_a.get('incomeLevel', {}).get('value', 'N/A')[:15]:<15} | {meta_b.get('incomeLevel', {}).get('value', 'N/A')[:15]:<15}",
            f"{'Region':<25} | {meta_a.get('region', {}).get('value', 'N/A')[:15]:<15} | {meta_b.get('region', {}).get('value', 'N/A')[:15]:<15}",
            f"{'GDP (Total)':<25} | {_format_compact(gdp_val_a):<15} | {_format_compact(gdp_val_b):<15}",
            f"{'GDP Per Capita':<25} | {_format_compact(gdp_pc_val_a):<15} | {_format_compact(gdp_pc_val_b):<15}",
            f"{'Population':<25} | {_format_compact(pop_val_a, ''):<15} | {_format_compact(pop_val_b, ''):<15}",
            f"{'Inflation Rate':<25} | {_format_percent(inf_val_a):<15} | {_format_percent(inf_val_b):<15}",
            f"{'Life Expectancy':<25} | {life_val_a:<15} | {life_val_b:<15}",
        ]

        if gdp_val_a and gdp_val_b and gdp_val_b > 0:
            ratio = gdp_val_a / gdp_val_b
            if ratio >= 1:
                lines.append(f"\n📌 Insight: {display_a}'s economy is {ratio:.1f}x the size of {display_b}'s economy.")
            else:
                lines.append(f"\n📌 Insight: {display_b}'s economy is {1/ratio:.1f}x the size of {display_a}'s economy.")

        return ChatToolResponse(result="\n".join(lines))
    except ValueError as val_err:
        return ChatToolResponse(error=str(val_err))
    except Exception as exc:
        return ChatToolResponse(error=f"Failed to compare economies: {str(exc)}")


@app.post("/tools/search-countries", response_model=ChatToolResponse)
async def search_countries(payload: SearchCountriesRequest) -> ChatToolResponse:
    """Discover countries matching geographic or economic criteria."""
    try:
        cached_countries: List[Dict[str, Any]] = getattr(getattr(app, "state", None), "country_cache", [])
        if not cached_countries:
            client = _get_http_client()
            resp = await client.get(f"{WORLD_BANK_BASE_URL}/country?format=json&per_page=300")
            if resp.status_code == 200:
                data = resp.json()
                if len(data) > 1 and isinstance(data[1], list):
                    cached_countries = data[1]
                    if hasattr(app, "state"):
                        app.state.country_cache = cached_countries

        matches = []
        for c in cached_countries:
            # Filter out aggregate groups like 'World', 'Africa', etc.
            if c.get("region", {}).get("value") == "Aggregates":
                continue

            name = c.get("name", "")
            capital = c.get("capitalCity", "")
            region = c.get("region", {}).get("value", "")
            income = c.get("incomeLevel", {}).get("value", "")

            if payload.query:
                q = payload.query.lower()
                if q not in name.lower() and q not in capital.lower() and q not in c.get("id", "").lower():
                    continue

            if payload.region:
                if payload.region.lower() not in region.lower():
                    continue

            if payload.income_level:
                if payload.income_level.lower() not in income.lower():
                    continue

            matches.append(c)

        if not matches:
            return ChatToolResponse(result="No countries found matching the specified search criteria.")

        matches_limited = matches[: payload.limit]
        lines = [f"🌐 Matching Countries ({len(matches_limited)} of {len(matches)}):"]
        for c in matches_limited:
            c_name = c.get("name", "Unknown")
            c_iso = c.get("id", "")
            c_cap = c.get("capitalCity") or "N/A"
            c_reg = c.get("region", {}).get("value", "N/A")
            c_inc = c.get("incomeLevel", {}).get("value", "N/A")
            lines.append(f"• {c_name} ({c_iso}) | Capital: {c_cap} | Region: {c_reg} | {c_inc}")

        return ChatToolResponse(result="\n".join(lines))
    except Exception as exc:
        return ChatToolResponse(error=f"Country search failed: {str(exc)}")


@app.get("/health")
async def health_check():
    """Health check probe."""
    return {"status": "healthy", "service": "omi-worldbank-app", "version": "1.0.0"}


@app.get("/", response_class=HTMLResponse)
async def landing_page():
    """Landing and documentation page for the World Bank Omi Integration."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Omi World Bank Economic Intelligence</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0c0d0e; color: #e1e4e8; margin: 0; padding: 40px 20px; line-height: 1.6; }
        .container { max-width: 820px; margin: 0 auto; background: #16181d; border-radius: 12px; border: 1px solid #2d333b; padding: 36px; box-shadow: 0 8px 30px rgba(0,0,0,0.5); }
        h1 { color: #58a6ff; margin-top: 0; font-size: 2rem; display: flex; align-items: center; gap: 10px; }
        .badge { background: #238636; color: #fff; padding: 4px 10px; border-radius: 20px; font-size: 0.8rem; font-weight: bold; }
        .card { background: #0d1117; border: 1px solid #30363d; border-radius: 8px; padding: 18px; margin: 16px 0; }
        .card h3 { margin-top: 0; color: #79c0ff; }
        code { background: #21262d; padding: 2px 6px; border-radius: 4px; font-size: 0.9em; color: #f0883e; }
        pre { background: #0d1117; border: 1px solid #30363d; padding: 14px; border-radius: 6px; overflow-x: auto; }
        a { color: #58a6ff; text-decoration: none; }
        a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🌐 World Bank Economic Intelligence <span class="badge">Active</span></h1>
        <p>A production-ready integration app connecting Omi AI wearable devices with the <strong>World Bank Open Data API</strong>.</p>

        <h2>Available Omi Chat Tools</h2>
        <div class="card">
            <h3>1. <code>get_country_profile</code></h3>
            <p>Retrieve a full macroeconomic and demographic briefing for any nation (GDP, GDP per capita, inflation, population, life expectancy, capital, income classification).</p>
        </div>
        <div class="card">
            <h3>2. <code>get_economic_indicator</code></h3>
            <p>Query specific macroeconomic indicators (GDP, inflation, population, unemployment, CO2 emissions) with multi-year annual trend trajectories.</p>
        </div>
        <div class="card">
            <h3>3. <code>compare_country_economies</code></h3>
            <p>Direct side-by-side comparative analysis of two nations with automatic GDP size ratio insights.</p>
        </div>
        <div class="card">
            <h3>4. <code>search_countries_by_region</code></h3>
            <p>Filter and explore countries by geographic region or World Bank income level classification.</p>
        </div>

        <h2>Manifest & Configuration</h2>
        <p>View the machine-readable Omi tools manifest at <a href="/.well-known/omi-tools.json"><code>/.well-known/omi-tools.json</code></a>.</p>
    </div>
</body>
</html>"""
