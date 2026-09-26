"""
World Bank Economic & Global Indicators Integration App for Omi.

Provides real-time macroeconomic indicators, GDP, inflation, population,
life expectancy, and cross-country comparisons using the public World Bank Open Data API.
"""

from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

try:
    from models import (
        ChatToolResponse,
        CompareIndicatorRequest,
        EconomicSnapshotRequest,
        IndicatorHistoryRequest,
    )
except ImportError:
    from .models import (
        ChatToolResponse,
        CompareIndicatorRequest,
        EconomicSnapshotRequest,
        IndicatorHistoryRequest,
    )

WORLD_BANK_BASE_URL = "https://api.worldbank.org/v2"
REQUEST_TIMEOUT_SECONDS = 10.0

INDICATOR_MAP: Dict[str, Dict[str, str]] = {
    "gdp": {
        "id": "NY.GDP.MKTP.CD",
        "name": "Gross Domestic Product (GDP)",
        "unit": "USD",
        "format": "currency",
    },
    "gdp_growth": {
        "id": "NY.GDP.MKTP.KD.ZG",
        "name": "GDP Growth Rate",
        "unit": "%",
        "format": "percent",
    },
    "inflation": {
        "id": "FP.CPI.TOTL.ZG",
        "name": "Inflation Rate (CPI)",
        "unit": "%",
        "format": "percent",
    },
    "population": {
        "id": "SP.POP.TOTL",
        "name": "Total Population",
        "unit": "people",
        "format": "number",
    },
    "life_expectancy": {
        "id": "SP.DYN.LE00.IN",
        "name": "Life Expectancy at Birth",
        "unit": "years",
        "format": "decimal",
    },
    "unemployment": {
        "id": "SL.UEM.TOTL.ZS",
        "name": "Unemployment Rate",
        "unit": "% of labor force",
        "format": "percent",
    },
    "co2": {
        "id": "EN.ATM.CO2E.PC",
        "name": "CO2 Emissions per Capita",
        "unit": "metric tons",
        "format": "decimal",
    },
}

COUNTRY_ALIASES: Dict[str, str] = {
    "united states": "USA",
    "usa": "USA",
    "us": "USA",
    "united kingdom": "GBR",
    "uk": "GBR",
    "china": "CHN",
    "india": "IND",
    "germany": "DEU",
    "japan": "JPN",
    "france": "FRA",
    "brazil": "BRA",
    "canada": "CAN",
    "russia": "RUS",
    "australia": "AUS",
    "south korea": "KOR",
    "korea": "KOR",
    "mexico": "MEX",
    "indonesia": "IDN",
    "saudi arabia": "SAU",
    "south africa": "ZAF",
    "world": "WLD",
}


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers={"User-Agent": "Omi-WorldBank-Plugin/1.0"},
    ) as client:
        app_instance.state.http_client = client
        yield


app = FastAPI(
    title="Omi World Bank Indicators Integration",
    description="Look up macroeconomic indicators, GDP, inflation, population, and global stats from World Bank Open Data.",
    version="1.0.0",
    lifespan=lifespan,
)


def _resolve_country_code(country_input: str) -> str:
    cleaned = country_input.strip()
    lowered = cleaned.lower()
    if lowered in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[lowered]
    if len(cleaned) in (2, 3) and cleaned.isalpha():
        return cleaned.upper()
    return cleaned


def _resolve_indicator(indicator_input: str) -> Tuple[str, Dict[str, str]]:
    cleaned = indicator_input.strip().lower().replace(" ", "_").replace("-", "_")
    if cleaned in INDICATOR_MAP:
        return cleaned, INDICATOR_MAP[cleaned]
    # Check by id match
    for key, info in INDICATOR_MAP.items():
        if info["id"].lower() == cleaned:
            return key, info
    # Default fallback to GDP
    return "gdp", INDICATOR_MAP["gdp"]


def _format_value(value: Any, format_type: str) -> str:
    if value is None:
        return "N/A"
    try:
        val = float(value)
    except (ValueError, TypeError):
        return str(value)

    if format_type == "currency":
        if abs(val) >= 1e12:
            return f"${val / 1e12:.2f} Trillion"
        elif abs(val) >= 1e9:
            return f"${val / 1e9:.2f} Billion"
        elif abs(val) >= 1e6:
            return f"${val / 1e6:.2f} Million"
        return f"${val:,.2f}"

    if format_type == "number":
        if abs(val) >= 1e9:
            return f"{val / 1e9:.2f} Billion"
        elif abs(val) >= 1e6:
            return f"{val / 1e6:.2f} Million"
        return f"{int(val):,}"

    if format_type == "percent":
        return f"{val:.2f}%"

    if format_type == "decimal":
        return f"{val:.2f}"

    return str(value)


async def _fetch_indicator_data(
    country_code: str,
    indicator_id: str,
    per_page: int = 5,
    client: Optional[httpx.AsyncClient] = None,
) -> Any:
    """Fetch indicator records from World Bank API."""
    url = f"{WORLD_BANK_BASE_URL}/country/{quote(country_code)}/indicator/{quote(indicator_id)}"
    params = {"format": "json", "per_page": per_page}
    should_close = False
    if client is None:
        client = getattr(app.state, "http_client", None)
    if client is None:
        client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS)
        should_close = True

    try:
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        return data
    except httpx.TimeoutException:
        return {"error": "World Bank request timed out. Please try again."}
    except httpx.HTTPStatusError as e:
        return {"error": f"World Bank API HTTP {e.response.status_code} error: {e.response.text[:200]}"}
    except Exception as e:
        return {"error": f"Failed to connect to World Bank API: {str(e)}"}
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
    <title>World Bank Economic Indicators for Omi</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; line-height: 1.6; color: #333; }
        h1 { color: #0072bc; }
        .card { background: #f0f7fc; border: 1px solid #d0e4f5; border-radius: 8px; padding: 20px; margin-bottom: 20px; }
        code { background: #e1effa; padding: 2px 6px; border-radius: 4px; font-size: 0.9em; }
        .endpoint { font-weight: bold; color: #005a9c; }
    </style>
</head>
<body>
    <h1>🌐 World Bank Economic Indicators for Omi</h1>
    <p>Provides macroeconomic data, GDP, inflation, population, and global stats directly to Omi chat tools.</p>

    <div class="card">
        <h3>Available Chat Tools</h3>
        <ul>
            <li><span class="endpoint">POST /tools/economic_snapshot</span> — Complete macroeconomic overview of a country.</li>
            <li><span class="endpoint">POST /tools/indicator_history</span> — Time-series history of a specific indicator.</li>
            <li><span class="endpoint">POST /tools/compare_indicator</span> — Side-by-side indicator comparison between two nations.</li>
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
    return {"status": "ok", "service": "omi-world-bank-app"}


@app.get("/privacy")
async def privacy():
    return {
        "privacy_policy": "Omi World Bank Integration does not collect, store, or share any personal user data."
    }


@app.get("/manifest.json")
@app.get("/.well-known/ai-plugin.json")
async def plugin_manifest():
    return {
        "schema_version": "v1",
        "name_for_human": "World Bank Global Indicators",
        "name_for_model": "world_bank_indicators",
        "description_for_human": "Macroeconomic statistics, GDP, inflation, demographics, and cross-country comparisons.",
        "description_for_model": "Look up macroeconomic indicators, GDP, inflation rates, population statistics, and country comparisons via World Bank Open Data.",
        "auth": {"type": "none"},
        "api": {
            "type": "openapi",
            "url": "/openapi.json"
        },
        "logo_url": "https://www.worldbank.org/content/dam/wbr/logo/logo-wb-header-en.svg",
        "contact_email": "support@omi.me",
        "legal_info_url": "/privacy"
    }


@app.post("/tools/economic_snapshot", response_model=ChatToolResponse)
async def economic_snapshot(req: EconomicSnapshotRequest):
    """Retrieve comprehensive economic profile for a country."""
    country_code = _resolve_country_code(req.country)
    # Query GDP as anchor
    gdp_data = await _fetch_indicator_data(country_code, INDICATOR_MAP["gdp"]["id"], per_page=3)
    if isinstance(gdp_data, dict) and gdp_data.get("error"):
        return ChatToolResponse(error=gdp_data["error"])

    if not isinstance(gdp_data, list) or len(gdp_data) < 2 or not gdp_data[1]:
        return ChatToolResponse(result=f"No economic data found for country '{req.country}'.")

    records = gdp_data[1]
    country_name = records[0].get("country", {}).get("value", req.country)

    # Extract latest valid GDP
    latest_gdp_entry = next((r for r in records if r.get("value") is not None), records[0])
    gdp_str = _format_value(latest_gdp_entry.get("value"), "currency")
    gdp_year = latest_gdp_entry.get("date", "Latest")

    # Fetch supplementary indicators in parallel
    pop_data = await _fetch_indicator_data(country_code, INDICATOR_MAP["population"]["id"], per_page=3)
    inf_data = await _fetch_indicator_data(country_code, INDICATOR_MAP["inflation"]["id"], per_page=3)
    life_data = await _fetch_indicator_data(country_code, INDICATOR_MAP["life_expectancy"]["id"], per_page=3)
    unemp_data = await _fetch_indicator_data(country_code, INDICATOR_MAP["unemployment"]["id"], per_page=3)

    def _extract_latest(data: Any, fmt: str) -> Tuple[str, str]:
        if isinstance(data, list) and len(data) >= 2 and data[1]:
            entry = next((r for r in data[1] if r.get("value") is not None), data[1][0])
            return _format_value(entry.get("value"), fmt), entry.get("date", "")
        return "N/A", ""

    pop_str, pop_year = _extract_latest(pop_data, "number")
    inf_str, inf_year = _extract_latest(inf_data, "percent")
    life_str, life_year = _extract_latest(life_data, "decimal")
    unemp_str, unemp_year = _extract_latest(unemp_data, "percent")

    lines = [
        f"### 📊 Economic Snapshot: {country_name} ({country_code})",
        "",
        f"- **GDP**: {gdp_str} ({gdp_year})",
        f"- **Population**: {pop_str} ({pop_year})",
        f"- **Inflation Rate**: {inf_str} ({inf_year})",
        f"- **Unemployment Rate**: {unemp_str} ({unemp_year})",
        f"- **Life Expectancy**: {life_str} years ({life_year})",
        "",
        "_Source: World Bank Open Data_",
    ]

    return ChatToolResponse(result="\n".join(lines))


@app.post("/tools/indicator_history", response_model=ChatToolResponse)
async def indicator_history(req: IndicatorHistoryRequest):
    """Retrieve historical time series for an economic indicator."""
    country_code = _resolve_country_code(req.country)
    key, meta = _resolve_indicator(req.indicator)
    years = req.years or 5

    data = await _fetch_indicator_data(country_code, meta["id"], per_page=years)
    if isinstance(data, dict) and data.get("error"):
        return ChatToolResponse(error=data["error"])

    if not isinstance(data, list) or len(data) < 2 or not data[1]:
        return ChatToolResponse(result=f"No {meta['name']} data found for country '{req.country}'.")

    records = data[1]
    country_name = records[0].get("country", {}).get("value", req.country)

    lines = [
        f"### {meta['name']} — {country_name} (Last {len(records)} recorded years)",
        "",
    ]
    for r in records:
        date = r.get("date", "Unknown")
        val = _format_value(r.get("value"), meta["format"])
        lines.append(f"- **{date}**: {val}")

    lines.extend(["", "_Source: World Bank Open Data_"])
    return ChatToolResponse(result="\n".join(lines))


@app.post("/tools/compare_indicator", response_model=ChatToolResponse)
async def compare_indicator(req: CompareIndicatorRequest):
    """Compare an indicator side-by-side between two countries."""
    code_a = _resolve_country_code(req.country_a)
    code_b = _resolve_country_code(req.country_b)
    key, meta = _resolve_indicator(req.indicator)

    data_a = await _fetch_indicator_data(code_a, meta["id"], per_page=3)
    data_b = await _fetch_indicator_data(code_b, meta["id"], per_page=3)

    if isinstance(data_a, dict) and data_a.get("error"):
        return ChatToolResponse(error=data_a["error"])
    if isinstance(data_b, dict) and data_b.get("error"):
        return ChatToolResponse(error=data_b["error"])

    def _get_latest_record(data: Any, fallback_code: str) -> Tuple[str, str, str]:
        if isinstance(data, list) and len(data) >= 2 and data[1]:
            entry = next((r for r in data[1] if r.get("value") is not None), data[1][0])
            name = entry.get("country", {}).get("value", fallback_code)
            val = _format_value(entry.get("value"), meta["format"])
            year = entry.get("date", "Latest")
            return name, val, year
        return fallback_code, "N/A", "Unknown"

    name_a, val_a, year_a = _get_latest_record(data_a, req.country_a)
    name_b, val_b, year_b = _get_latest_record(data_b, req.country_b)

    lines = [
        f"### ⚖️ Comparison: {meta['name']}",
        "",
        f"- **{name_a} ({code_a})**: {val_a} ({year_a})",
        f"- **{name_b} ({code_b})**: {val_b} ({year_b})",
        "",
        "_Source: World Bank Open Data_",
    ]

    return ChatToolResponse(result="\n".join(lines))
