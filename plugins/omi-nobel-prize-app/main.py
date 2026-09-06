"""Omi Nobel Prize Global Laureates & Human Discovery Integration App.

Provides voice-optimized chat tools for querying Nobel Prizes, discovering laureates,
and learning about seminal scientific, peace, and literary achievements using the
official Nobel Prize API (api.nobelprize.org).
"""

import html
from typing import Any, Dict, List, Optional
import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse

try:
    from .models import (
        CATEGORY_DISPLAY_NAMES,
        NOBEL_CATEGORY_MAP,
        CategoryPrizesRequest,
        ChatToolResponse,
        LaureateDetailsRequest,
        NobelPrizesRequest,
        SearchLaureatesRequest,
        resolve_nobel_category,
    )
except ImportError:
    from models import (
        CATEGORY_DISPLAY_NAMES,
        NOBEL_CATEGORY_MAP,
        CategoryPrizesRequest,
        ChatToolResponse,
        LaureateDetailsRequest,
        NobelPrizesRequest,
        SearchLaureatesRequest,
        resolve_nobel_category,
    )

BASE_API_URL = "https://api.nobelprize.org/2.1"
API_TIMEOUT = 10.0
USER_AGENT = "OmiNobelPrizeApp/1.0 (https://github.com/BasedHardware/omi)"

app = FastAPI(
    title="Omi Nobel Prize Global Laureates App",
    description="Explore Nobel Prizes, groundbreaking discoveries, and laureate profiles via voice for Omi AI wearable.",
    version="1.0.0",
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Intercept validation errors and return structured ChatToolResponse with error."""
    first_error = exc.errors()[0]
    msg = first_error.get("msg", "Invalid request parameters.")
    loc = first_error.get("loc", [])
    field = loc[-1] if loc else "field"
    clean_msg = f"Validation error on '{field}': {msg}"
    return JSONResponse(
        status_code=422,
        content={"error": clean_msg, "result": None},
    )


@app.get("/", response_class=HTMLResponse)
async def root():
    """Service landing page and capability summary."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Omi Nobel Prize Integration App</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 2rem; }
        .container { max-width: 800px; margin: 0 auto; background: #1e293b; border-radius: 12px; padding: 2rem; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.3); }
        h1 { color: #f59e0b; margin-top: 0; }
        .badge { display: inline-block; background: #10b981; color: white; padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.875rem; font-weight: 600; }
        .tools { margin-top: 1.5rem; }
        .tool-card { background: #334155; border-radius: 8px; padding: 1rem; margin-bottom: 1rem; }
        .tool-name { font-weight: bold; color: #38bdf8; font-family: monospace; }
        code { background: #0f172a; padding: 0.2rem 0.4rem; border-radius: 4px; font-family: monospace; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Omi Nobel Prize Integration App <span class="badge">Active</span></h1>
        <p>Zero-authentication global intelligence integration bringing world-changing discoveries, scientific breakthroughs, peace milestones, and laureate biographies to the Omi AI voice wearable.</p>
        
        <div class="tools">
            <h3>Registered Chat Tools:</h3>
            <div class="tool-card">
                <div class="tool-name">POST /tools/get_nobel_prizes</div>
                <p>Retrieves Nobel Prizes by year and/or category with winners, prize motivation, and affiliations.</p>
                <div><code>"Who won the Nobel Peace Prize this year?"</code></div>
            </div>
            <div class="tool-card">
                <div class="tool-name">POST /tools/search_nobel_laureates</div>
                <p>Searches laureates by name, returning birth data, prize year, discipline, and discovery rationale.</p>
                <div><code>"Tell me about Marie Curie's Nobel Prizes."</code></div>
            </div>
            <div class="tool-card">
                <div class="tool-name">POST /tools/get_nobel_prize_by_category</div>
                <p>Fetches the most recent prizes in Physics, Chemistry, Medicine, Literature, Peace, or Economics.</p>
                <div><code>"What are the latest discoveries in Medicine that won a Nobel Prize?"</code></div>
            </div>
            <div class="tool-card">
                <div class="tool-name">POST /tools/get_nobel_laureate_details</div>
                <p>Provides an in-depth biographical and historical dossier for a specific laureate.</p>
                <div><code>"Get full dossier for Albert Einstein."</code></div>
            </div>
        </div>

        <p><small>Powered by the official Nobel Prize API (api.nobelprize.org) &middot; Manifest at <code>/.well-known/omi-tools.json</code></small></p>
    </div>
</body>
</html>"""


@app.get("/health")
async def health_check():
    """Health check endpoint for container orchestrators."""
    return {"status": "ok", "service": "omi-nobel-prize-app"}


@app.get("/.well-known/omi-tools.json")
async def omi_tools_manifest():
    """Official Omi tools discovery manifest."""
    return {
        "schema_version": "v1",
        "name": "Nobel Prize Global Laureates & Human Discovery",
        "description": "Explore Nobel Prizes, groundbreaking discoveries, peace milestones, and laureate profiles via voice.",
        "tools": [
            {
                "name": "get_nobel_prizes",
                "description": "Query Nobel Prizes by year (e.g. 2023) and/or category (physics, chemistry, medicine, literature, peace, economics).",
                "endpoint": "/tools/get_nobel_prizes",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "year": {
                            "type": "integer",
                            "description": "Year awarded (1901 to current year). If omitted, returns recent prizes.",
                        },
                        "category": {
                            "type": "string",
                            "description": "Category: physics, chemistry, medicine, literature, peace, economics.",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Number of prizes to return (1-25, default 5).",
                        },
                    },
                },
            },
            {
                "name": "search_nobel_laureates",
                "description": "Search Nobel laureates by name or keyword to learn when they won, for what discovery, and their biography.",
                "endpoint": "/tools/search_nobel_laureates",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Name of the laureate (e.g. Einstein, Curie, Mandela, Feynman).",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max results to return (1-10, default 5).",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "get_nobel_prize_by_category",
                "description": "Browse recent Nobel Prizes awarded in a specific field: physics, chemistry, medicine, literature, peace, or economics.",
                "endpoint": "/tools/get_nobel_prize_by_category",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "description": "Nobel category: physics, chemistry, medicine, literature, peace, economics.",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Number of prizes to return (1-15, default 5).",
                        },
                    },
                    "required": ["category"],
                },
            },
            {
                "name": "get_nobel_laureate_details",
                "description": "Retrieve comprehensive biographical details, affiliations, and award history for a specific laureate.",
                "endpoint": "/tools/get_nobel_laureate_details",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "identifier": {
                            "type": "string",
                            "description": "Laureate ID (e.g. '1') or name (e.g. 'Albert Einstein').",
                        },
                    },
                    "required": ["identifier"],
                },
            },
        ],
    }


def _format_prize_block(p: Dict[str, Any]) -> str:
    """Format a single Nobel prize dictionary into clean voice-friendly markdown."""
    award_year = p.get("awardYear", "Unknown year")
    category_name = p.get("categoryFullName", {}).get("en") or p.get("category", {}).get("en", "Nobel Prize")
    lines = [f"### {category_name} ({award_year})"]

    laureates = p.get("laureates", [])
    if not laureates:
        lines.append("- *No prize was awarded this year or prize details unavailable.*")
        return "\n".join(lines)

    for l in laureates:
        name = l.get("knownName", {}).get("en") or l.get("orgName", {}).get("en", "Unknown Laureate")
        portion = l.get("portion", "1")
        portion_str = f" (Share: {portion})" if portion != "1" else ""
        motivation = l.get("motivation", {}).get("en", "No motivation text provided.")
        lines.append(f"- **{name}**{portion_str}: {motivation.strip()}")

    return "\n".join(lines)


@app.post("/tools/get_nobel_prizes", response_model=ChatToolResponse)
async def get_nobel_prizes(request: NobelPrizesRequest):
    """Retrieve Nobel Prizes filtered by year and/or category."""
    params: Dict[str, Any] = {"limit": request.limit, "sort": "desc"}
    if request.year:
        params["nobelPrizeYear"] = request.year
    if request.category:
        params["nobelPrizeCategory"] = request.category

    try:
        async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
            resp = await client.get(
                f"{BASE_API_URL}/nobelPrizes",
                params=params,
                headers={"User-Agent": USER_AGENT},
            )

        if resp.status_code != 200:
            return ChatToolResponse(
                error=f"Nobel Prize API error (HTTP {resp.status_code}). Please try again later."
            )

        data = resp.json()
        prizes = data.get("nobelPrizes", [])
        if not prizes:
            filter_desc = []
            if request.year:
                filter_desc.append(f"year {request.year}")
            if request.category:
                cat_name = CATEGORY_DISPLAY_NAMES.get(request.category, request.category)
                filter_desc.append(f"category '{cat_name}'")
            filter_str = " for " + " and ".join(filter_desc) if filter_desc else ""
            return ChatToolResponse(
                result=f"No Nobel Prize records found{filter_str}."
            )

        blocks = [_format_prize_block(p) for p in prizes]
        result_text = "\n\n".join(blocks)
        return ChatToolResponse(result=result_text)

    except httpx.RequestError as e:
        return ChatToolResponse(
            error=f"Failed to communicate with Nobel Prize API: {str(e)}"
        )
    except Exception as e:
        return ChatToolResponse(
            error=f"An unexpected error occurred while processing Nobel Prizes: {str(e)}"
        )


@app.post("/tools/search_nobel_laureates", response_model=ChatToolResponse)
async def search_nobel_laureates(request: SearchLaureatesRequest):
    """Search Nobel laureates by name or keyword."""
    params = {"name": request.query, "limit": request.limit}

    try:
        async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
            resp = await client.get(
                f"{BASE_API_URL}/laureates",
                params=params,
                headers={"User-Agent": USER_AGENT},
            )

        if resp.status_code != 200:
            return ChatToolResponse(
                error=f"Nobel Prize API error (HTTP {resp.status_code}). Please try again later."
            )

        data = resp.json()
        laureates = data.get("laureates", [])
        if not laureates:
            return ChatToolResponse(
                result=f"No Nobel laureates found matching '{request.query}'."
            )

        output_lines = [f"Found {len(laureates)} Nobel laureate(s) matching '{request.query}':\n"]
        for idx, l in enumerate(laureates, 1):
            name = l.get("knownName", {}).get("en") or l.get("orgName", {}).get("en", "Unknown")
            birth_info = []
            birth_date = l.get("birth", {}).get("date")
            birth_city = l.get("birth", {}).get("place", {}).get("city", {}).get("en")
            birth_country = l.get("birth", {}).get("place", {}).get("country", {}).get("en")
            if birth_date:
                birth_info.append(f"Born: {birth_date}")
            if birth_city or birth_country:
                place = ", ".join(filter(None, [birth_city, birth_country]))
                birth_info.append(place)
            birth_str = f" ({'; '.join(birth_info)})" if birth_info else ""

            output_lines.append(f"{idx}. **{name}**{birth_str}")
            prizes = l.get("nobelPrizes", [])
            for p in prizes:
                yr = p.get("awardYear", "N/A")
                cat = p.get("categoryFullName", {}).get("en") or p.get("category", {}).get("en", "Nobel Prize")
                mot = p.get("motivation", {}).get("en", "No motivation listed.")
                output_lines.append(f"   - **{yr} {cat}**: {mot.strip()}")
            output_lines.append("")

        return ChatToolResponse(result="\n".join(output_lines).strip())

    except httpx.RequestError as e:
        return ChatToolResponse(
            error=f"Failed to communicate with Nobel Prize API: {str(e)}"
        )
    except Exception as e:
        return ChatToolResponse(
            error=f"An unexpected error occurred while searching laureates: {str(e)}"
        )


@app.post("/tools/get_nobel_prize_by_category", response_model=ChatToolResponse)
async def get_nobel_prize_by_category(request: CategoryPrizesRequest):
    """Retrieve recent Nobel Prizes for a specific category."""
    cat_code = request.category
    cat_title = CATEGORY_DISPLAY_NAMES.get(cat_code, cat_code)

    params = {
        "nobelPrizeCategory": cat_code,
        "limit": request.limit,
        "sort": "desc",
    }

    try:
        async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
            resp = await client.get(
                f"{BASE_API_URL}/nobelPrizes",
                params=params,
                headers={"User-Agent": USER_AGENT},
            )

        if resp.status_code != 200:
            return ChatToolResponse(
                error=f"Nobel Prize API error (HTTP {resp.status_code}). Please try again later."
            )

        data = resp.json()
        prizes = data.get("nobelPrizes", [])
        if not prizes:
            return ChatToolResponse(
                result=f"No Nobel Prizes found for category '{cat_title}'."
            )

        header = f"## Recent Nobel Prizes in {cat_title}\n"
        blocks = [_format_prize_block(p) for p in prizes]
        return ChatToolResponse(result=header + "\n\n".join(blocks))

    except httpx.RequestError as e:
        return ChatToolResponse(
            error=f"Failed to communicate with Nobel Prize API: {str(e)}"
        )
    except Exception as e:
        return ChatToolResponse(
            error=f"An unexpected error occurred while retrieving prizes for {cat_title}: {str(e)}"
        )


@app.post("/tools/get_nobel_laureate_details", response_model=ChatToolResponse)
async def get_nobel_laureate_details(request: LaureateDetailsRequest):
    """Retrieve detailed dossier and biographical information for a laureate."""
    ident = request.identifier

    try:
        async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
            if ident.isdigit():
                resp = await client.get(
                    f"{BASE_API_URL}/laureate/{ident}",
                    headers={"User-Agent": USER_AGENT},
                )
                if resp.status_code == 404:
                    return ChatToolResponse(
                        error=f"No Nobel laureate found with ID '{ident}'."
                    )
                if resp.status_code != 200:
                    return ChatToolResponse(
                        error=f"Nobel Prize API error (HTTP {resp.status_code})."
                    )
                data = resp.json()
                laureate_list = data if isinstance(data, list) else data.get("laureates", [])
            else:
                resp = await client.get(
                    f"{BASE_API_URL}/laureates",
                    params={"name": ident, "limit": 1},
                    headers={"User-Agent": USER_AGENT},
                )
                if resp.status_code != 200:
                    return ChatToolResponse(
                        error=f"Nobel Prize API error (HTTP {resp.status_code})."
                    )
                data = resp.json()
                laureate_list = data.get("laureates", [])

        if not laureate_list:
            return ChatToolResponse(
                error=f"No Nobel laureate found matching '{ident}'."
            )

        l = laureate_list[0]
        name = l.get("knownName", {}).get("en") or l.get("orgName", {}).get("en", "Unknown Laureate")
        full_name = l.get("fullName", {}).get("en")
        gender = l.get("gender")

        details = [f"## {name}"]
        if full_name and full_name != name:
            details.append(f"**Full Name**: {full_name}")
        if gender:
            details.append(f"**Gender**: {gender.capitalize()}")

        # Birth & Death
        birth = l.get("birth", {})
        birth_date = birth.get("date")
        birth_city = birth.get("place", {}).get("city", {}).get("en")
        birth_country = birth.get("place", {}).get("country", {}).get("en")
        birth_loc = ", ".join(filter(None, [birth_city, birth_country]))
        if birth_date or birth_loc:
            details.append(f"**Birth**: {birth_date or 'Unknown'} {f'({birth_loc})' if birth_loc else ''}".strip())

        death = l.get("death", {})
        if death and death.get("date"):
            death_city = death.get("place", {}).get("city", {}).get("en")
            death_country = death.get("place", {}).get("country", {}).get("en")
            death_loc = ", ".join(filter(None, [death_city, death_country]))
            details.append(f"**Died**: {death.get('date')} {f'({death_loc})' if death_loc else ''}".strip())

        # Prizes
        details.append("\n### Nobel Prize Awards:")
        prizes = l.get("nobelPrizes", [])
        for p in prizes:
            yr = p.get("awardYear", "N/A")
            cat = p.get("categoryFullName", {}).get("en") or p.get("category", {}).get("en", "Nobel Prize")
            mot = p.get("motivation", {}).get("en", "No motivation listed.")
            portion = p.get("portion", "1")
            details.append(f"- **{yr} {cat}** (Share: {portion})")
            details.append(f"  *Motivation*: {mot.strip()}")

            affiliations = p.get("affiliations", [])
            for aff in affiliations:
                aff_name = aff.get("name", {}).get("en")
                aff_city = aff.get("city", {}).get("en")
                aff_country = aff.get("country", {}).get("en")
                loc = ", ".join(filter(None, [aff_city, aff_country]))
                if aff_name:
                    details.append(f"  *Affiliation*: {aff_name} {f'({loc})' if loc else ''}".strip())

        wiki = l.get("wikipedia", {}).get("english")
        if wiki:
            details.append(f"\n**Wikipedia**: {wiki}")

        return ChatToolResponse(result="\n".join(details))

    except httpx.RequestError as e:
        return ChatToolResponse(
            error=f"Failed to communicate with Nobel Prize API: {str(e)}"
        )
    except Exception as e:
        return ChatToolResponse(
            error=f"An unexpected error occurred: {str(e)}"
        )
