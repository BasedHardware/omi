"""
Open Food Facts chat tools for Omi.

This app gives Omi users a small set of read-only food lookup tools backed by
the public Open Food Facts API.
"""

import os
import re
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import requests
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

try:
    import httpx
except ImportError:  # pragma: no cover - defensive; httpx is in requirements.txt
    httpx = None

from models import (
    ChatToolResponse,
    CheckAllergensRequest,
    CompareFoodsRequest,
    LookupBarcodeRequest,
    SearchFoodsRequest,
)


OPENFOODFACTS_BASE_URL = os.getenv(
    "OPENFOODFACTS_BASE_URL", "https://world.openfoodfacts.org"
).rstrip("/")
OPENFOODFACTS_USER_AGENT = os.getenv(
    "OPENFOODFACTS_USER_AGENT",
    "OmiOpenFoodFactsApp/1.0 (https://github.com/BasedHardware/omi)",
)
REQUEST_TIMEOUT_SECONDS = float(os.getenv("OPENFOODFACTS_TIMEOUT_SECONDS", "8"))

PRODUCT_FIELDS = ",".join(
    [
        "code",
        "product_name",
        "generic_name",
        "brands",
        "quantity",
        "categories_tags",
        "labels_tags",
        "ingredients_text",
        "allergens_tags",
        "traces_tags",
        "nutriscore_grade",
        "nova_group",
        "ecoscore_grade",
        "nutriments",
        "image_front_small_url",
    ]
)


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    """Keep one pooled async HTTP client for the app's lifetime.

    Falls back to the synchronous ``requests`` path (run in a threadpool) when
    httpx is unavailable so the tools still work in lean environments.
    """
    if httpx is None:
        app_instance.state.http_client = None
        yield
        return
    async with httpx.AsyncClient(
        base_url=OPENFOODFACTS_BASE_URL,
        headers=_headers(),
        timeout=REQUEST_TIMEOUT_SECONDS,
    ) as client:
        app_instance.state.http_client = client
        yield


app = FastAPI(
    title="Open Food Facts Omi Integration",
    description="Food, nutrition, Nutri-Score, allergen, and barcode lookup tools for Omi.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Return validation failures as a 200 ChatToolResponse error envelope."""
    try:
        errors = exc.errors() or []
    except Exception:
        errors = []
    first = errors[0] if errors and isinstance(errors[0], dict) else {}
    location = ".".join(str(part) for part in first.get("loc", []) if part != "body")
    message = first.get("msg", "invalid request")
    detail = f"{location}: {message}" if location else str(message)
    response = ChatToolResponse.fail(f"invalid tool request: {detail}")
    return JSONResponse(status_code=200, content=response.as_dict())


def _headers() -> Dict[str, str]:
    return {
        "Accept": "application/json",
        "User-Agent": OPENFOODFACTS_USER_AGENT,
    }


def _as_str(value: Any) -> str:
    """Coerce an upstream API field to a string without crashing on odd types."""
    if not value:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _grade(value: Any) -> Optional[str]:
    """Normalize a Nutri-Score/Eco-Score grade to an uppercase letter or None."""
    if not isinstance(value, str):
        return None
    return value.strip().upper() or None


def _normalize_tag(tag: str) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.split(":", 1)[-1].replace("-", " ").strip()


def _normalize_tags(tags: Any) -> List[str]:
    if not isinstance(tags, list):
        return []
    return [item for item in (_normalize_tag(tag) for tag in tags) if item]


def _nutrient(product: Dict[str, Any], key: str) -> Optional[Any]:
    """Return the per-100g nutrient only.

    Unsuffixed nutriment keys depend on nutrition_data_per (often serving).
    Falling back to them and labeling the result per_100g is wrong.
    """
    nutriments = product.get("nutriments")
    if not isinstance(nutriments, dict):
        return None
    per_100g_key = f"{key}_100g"
    if per_100g_key in nutriments:
        return nutriments[per_100g_key]
    return None


def _summarize_product(product: Dict[str, Any]) -> Dict[str, Any]:
    name = product.get("product_name") or product.get("generic_name")
    return {
        "barcode": _as_str(product.get("code")),
        "name": _as_str(name) or "Unknown product",
        "brands": _as_str(product.get("brands")),
        "quantity": _as_str(product.get("quantity")),
        "nutri_score": _grade(product.get("nutriscore_grade")),
        "nova_group": product.get("nova_group"),
        "eco_score": _grade(product.get("ecoscore_grade")),
        "allergens": _normalize_tags(product.get("allergens_tags")),
        "traces": _normalize_tags(product.get("traces_tags")),
        "labels": _normalize_tags(product.get("labels_tags"))[:12],
        "categories": _normalize_tags(product.get("categories_tags"))[:12],
        "ingredients": _as_str(product.get("ingredients_text")),
        "nutrition_per_100g": {
            "energy_kcal": _nutrient(product, "energy-kcal"),
            "fat_g": _nutrient(product, "fat"),
            "saturated_fat_g": _nutrient(product, "saturated-fat"),
            "carbohydrates_g": _nutrient(product, "carbohydrates"),
            "sugars_g": _nutrient(product, "sugars"),
            "fiber_g": _nutrient(product, "fiber"),
            "proteins_g": _nutrient(product, "proteins"),
            "salt_g": _nutrient(product, "salt"),
        },
        "image_url": _as_str(product.get("image_front_small_url")),
        "data_note": "Open Food Facts data is community contributed and can be incomplete.",
    }


def _openfoodfacts_get(path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    try:
        response = requests.get(
            f"{OPENFOODFACTS_BASE_URL}{path}",
            params=params or {},
            headers=_headers(),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        return {"error": f"Open Food Facts request failed: {exc}"}
    except ValueError:
        return {"error": "Open Food Facts returned a non-JSON response"}


async def _openfoodfacts_get_async(
    path: str, params: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """GET through the pooled lifespan client, falling back to a threadpool."""
    client = getattr(app.state, "http_client", None)
    if client is not None:
        try:
            response = await client.get(path, params=params or {})
            response.raise_for_status()
        except Exception as exc:
            return {"error": f"Open Food Facts request failed: {exc}"}
        try:
            return response.json()
        except ValueError:
            return {"error": "Open Food Facts returned a non-JSON response"}
    return await run_in_threadpool(_openfoodfacts_get, path, params)


async def _lookup_barcode(barcode: str) -> Dict[str, Any]:
    cleaned = "".join(char for char in str(barcode or "") if char.isdigit())
    if not cleaned:
        return {"error": "barcode is required"}

    payload = await _openfoodfacts_get_async(
        f"/api/v2/product/{cleaned}.json",
        {"fields": PRODUCT_FIELDS},
    )
    if not isinstance(payload, dict):
        return {"error": "Open Food Facts returned an unexpected response"}
    if "error" in payload:
        return payload
    if payload.get("status") == 0 or not isinstance(payload.get("product"), dict):
        return {"error": f"no product found for barcode {cleaned}"}
    return {"product": _summarize_product(payload["product"])}


async def _search_foods(query: str, page_size: int) -> Dict[str, Any]:
    query = str(query or "").strip()
    if not query:
        return {"error": "query is required"}

    # CGI search is the full-text product search; /api/v2/search is not.
    payload = await _openfoodfacts_get_async(
        "/cgi/search.pl",
        {
            "action": "process",
            "search_terms": query,
            "search_simple": 1,
            "json": 1,
            "page_size": page_size,
            "fields": PRODUCT_FIELDS,
        },
    )
    if not isinstance(payload, dict):
        return {"error": "Open Food Facts returned an unexpected response"}
    if "error" in payload:
        return payload

    raw_products = payload.get("products")
    if not isinstance(raw_products, list):
        raw_products = []
    products = [
        _summarize_product(item) for item in raw_products if isinstance(item, dict)
    ]
    return {
        "query": query,
        "count": payload.get("count", 0),
        "products": products,
        "data_note": "Search is capped by this app to reduce API load.",
    }


async def _collect_foods(barcodes: List[Any]) -> Dict[str, Any]:
    products = []
    errors = []
    for barcode in barcodes[:5]:
        result = await _lookup_barcode(str(barcode))
        if "product" in result:
            products.append(result["product"])
        else:
            errors.append({"barcode": barcode, "error": result.get("error", "lookup failed")})

    if not products:
        return {"error": "no products found", "errors": errors}
    return {"products": products, "errors": errors}


def _ingredient_mentions_term(ingredients: str, term: str) -> bool:
    term = str(term or "").lower().strip()
    if not term:
        return False

    normalized = ingredients.lower()
    pattern = re.compile(rf"(?<![a-z]){re.escape(term)}(?![a-z])")
    for match in pattern.finditer(normalized):
        after = normalized[match.end() : match.end() + 8]
        before = normalized[max(0, match.start() - 8) : match.start()]
        if after.startswith("-free") or after.startswith(" free"):
            continue
        if before.endswith("no ") or before.endswith("non-"):
            continue
        return True
    return False


@app.get("/health")
async def health():
    return {"status": "ok", "service": "omi-openfoodfacts-app"}


@app.get("/.well-known/omi-tools.json")
async def get_omi_tools_manifest():
    return {
        "tools": [
            {
                "name": "search_foods",
                "description": "Search packaged foods by name and return nutrition, Nutri-Score, NOVA group, allergens, and labels. Use for questions like 'find oat milk' or 'show me low sugar cereal options'.",
                "endpoint": "/tools/search_foods",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Food or product name to search for.",
                        },
                        "page_size": {
                            "type": "integer",
                            "description": "Number of products to return. Defaults to 5 and is capped at 10.",
                        },
                    },
                    "required": ["query"],
                },
                "auth_required": False,
                "status_message": "Searching Open Food Facts...",
            },
            {
                "name": "lookup_barcode",
                "description": "Look up a packaged food by barcode and return nutrition per 100g, Nutri-Score, NOVA group, allergens, ingredients, and labels.",
                "endpoint": "/tools/lookup_barcode",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "barcode": {
                            "type": "string",
                            "description": "Product barcode, digits only or copied from packaging.",
                        }
                    },
                    "required": ["barcode"],
                },
                "auth_required": False,
                "status_message": "Looking up the barcode...",
            },
            {
                "name": "compare_foods",
                "description": "Compare up to five packaged foods by barcode using nutrition per 100g, Nutri-Score, NOVA group, allergens, and labels.",
                "endpoint": "/tools/compare_foods",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "barcodes": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "A list of up to five product barcodes.",
                        }
                    },
                    "required": ["barcodes"],
                },
                "auth_required": False,
                "status_message": "Comparing products...",
            },
            {
                "name": "check_allergens",
                "description": "Check whether a packaged food includes allergens or traces the user wants to avoid. Provide either a barcode or a search query.",
                "endpoint": "/tools/check_allergens",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "barcode": {
                            "type": "string",
                            "description": "Optional barcode to check directly.",
                        },
                        "query": {
                            "type": "string",
                            "description": "Optional product search query if no barcode is available.",
                        },
                        "avoid": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Allergens or ingredients to avoid, such as milk, peanuts, gluten, soy, or eggs.",
                        },
                    },
                    "required": ["avoid"],
                },
                "auth_required": False,
                "status_message": "Checking allergen information...",
            },
        ]
    }


@app.get("/manifest.json")
async def get_manifest_alias():
    return await get_omi_tools_manifest()


@app.post("/tools/search_foods", response_model=ChatToolResponse)
async def tool_search_foods(body: SearchFoodsRequest):
    result = await _search_foods(body.clean_query(), body.clamped_page_size())
    if "error" in result:
        return ChatToolResponse.fail(result["error"], data=result)

    products = result.get("products", [])
    if not products:
        return ChatToolResponse.ok(
            f"No Open Food Facts products found for '{result['query']}'.",
            data=result,
        )
    return ChatToolResponse.ok(
        f"Found {len(products)} product(s) for '{result['query']}'.",
        data=result,
    )


@app.post("/tools/lookup_barcode", response_model=ChatToolResponse)
async def tool_lookup_barcode(body: LookupBarcodeRequest):
    result = await _lookup_barcode(body.raw_barcode())
    if "error" in result:
        return ChatToolResponse.fail(result["error"], data=result)

    product = result["product"]
    return ChatToolResponse.ok(
        f"{product['name']} found in Open Food Facts.",
        data=result,
    )


@app.post("/tools/compare_foods", response_model=ChatToolResponse)
async def tool_compare_foods(body: CompareFoodsRequest):
    barcodes_error = body.barcodes_error()
    if barcodes_error:
        return ChatToolResponse.fail(barcodes_error)

    result = await _collect_foods(body.clean_barcodes())
    if "error" in result:
        return ChatToolResponse.fail(result["error"], data=result)

    products = result["products"]
    return ChatToolResponse.ok(
        f"Compared {len(products)} product(s).",
        data=result,
    )


@app.post("/tools/check_allergens", response_model=ChatToolResponse)
async def tool_check_allergens(body: CheckAllergensRequest):
    avoid_terms = {term.lower() for term in body.clean_avoid()}
    if not avoid_terms:
        return ChatToolResponse.fail("avoid must be a non-empty list")

    target_error = body.target_error()
    if target_error:
        return ChatToolResponse.fail(target_error)

    if body.has_barcode():
        lookup = await _lookup_barcode(body.raw_barcode())
        if "error" in lookup:
            return ChatToolResponse.fail(lookup["error"], data=lookup)
        product = lookup["product"]
    else:
        search = await _search_foods(body.clean_query(), 1)
        if "error" in search:
            return ChatToolResponse.fail(search["error"], data=search)
        products = search.get("products", [])
        if not products:
            return ChatToolResponse.fail("No product found to check", data=search)
        product = products[0]

    known_allergens = {item.lower() for item in product.get("allergens", [])}
    traces = {item.lower() for item in product.get("traces", [])}
    ingredients = (product.get("ingredients") or "").lower()

    matches = sorted(
        term
        for term in avoid_terms
        if term in known_allergens
        or term in traces
        or _ingredient_mentions_term(ingredients, term)
    )

    data = {
        "product": product,
        "avoid": sorted(avoid_terms),
        "matches": matches,
        "checked_sources": ["allergens", "traces", "ingredients text"],
        "data_note": "Missing Open Food Facts allergen data does not prove the food is safe.",
    }
    if matches:
        message = f"{product['name']} may include: {', '.join(matches)}."
    else:
        message = (
            f"No listed match found for {product['name']}, but verify the package label."
        )

    return ChatToolResponse.ok(message, data=data)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
