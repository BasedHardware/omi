"""
Frankfurter Currency Integration App for Omi.

Provides chat tools for currency conversion, latest reference rates, and
supported-currency lookup through the public Frankfurter API.
"""

from contextlib import asynccontextmanager
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator


# The legacy .app host permanently redirects to the canonical v1 API.  Keep
# the version in the base URL so every request (including /currencies) avoids
# an extra redirect; HTTPX deliberately does not follow redirects by default.
FRANKFURTER_BASE_URL = "https://api.frankfurter.dev/v1"
REQUEST_TIMEOUT_SECONDS = 10
MAX_TARGET_CURRENCIES = 10


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        app_instance.state.http_client = client
        try:
            yield
        finally:
            if hasattr(app_instance.state, "http_client") and app_instance.state.http_client is not None:
                await app_instance.state.http_client.aclose()


app = FastAPI(
    title="Omi Frankfurter Currency Integration",
    description="Convert currencies and check reference exchange rates from Omi chat tools",
    version="1.0.0",
    lifespan=lifespan,
)


class ChatToolResponse(BaseModel):
    """Response model for Omi chat tool endpoints."""

    result: Optional[str] = None
    error: Optional[str] = None


class ConvertCurrencyRequest(BaseModel):
    amount: str | float | int = Field(..., description="Amount to convert, such as 50 or '19.95'.")
    from_currency: str = Field(..., min_length=3, max_length=3)
    to_currencies: list[str] = Field(..., min_length=1, max_length=MAX_TARGET_CURRENCIES)

    @field_validator("from_currency", mode="before")
    @classmethod
    def normalize_from_currency(cls, value: str) -> str:
        return _normalize_currency_code(value)

    @field_validator("to_currencies", mode="before")
    @classmethod
    def normalize_to_currencies(cls, values: list[str]) -> list[str]:
        return _coerce_currency_list(values, allow_null=False)


class LatestRatesRequest(BaseModel):
    base_currency: str = Field(..., min_length=3, max_length=3)
    to_currencies: list[str] = Field(default_factory=list, max_length=MAX_TARGET_CURRENCIES)

    @field_validator("base_currency", mode="before")
    @classmethod
    def normalize_base_currency(cls, value: str) -> str:
        return _normalize_currency_code(value)

    @field_validator("to_currencies", mode="before")
    @classmethod
    def normalize_to_currencies(cls, values: list[str]) -> list[str]:
        return _coerce_currency_list(values, allow_null=True)


def _normalize_currency_code(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("currency codes must be 3 letters, such as USD or EUR")
    code = value.strip().upper()
    if len(code) != 3 or not code.isalpha():
        raise ValueError("currency codes must be 3 letters, such as USD or EUR")
    return code


def _coerce_currency_list(values: Any, *, allow_null: bool) -> list[str]:
    """Accept a single code or a list of codes; tolerate JSON null for optional fields.

    Chat runners forward unprovided optional parameters as JSON ``null`` and
    sometimes collapse single-element lists to a bare string. Normalize both so
    an optional filter cannot turn into a rejected tool call.
    """
    if values is None:
        if allow_null:
            return []
        raise ValueError("to_currencies must be a list of 3-letter currency codes")
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple)):
        raise ValueError("to_currencies must be a list of 3-letter currency codes")
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        code = _normalize_currency_code(value)
        if code not in seen:
            seen.add(code)
            normalized.append(code)
    return normalized


def _parse_amount(value: str | float | int) -> Decimal:
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("amount must be a number") from exc

    if not amount.is_finite():
        raise ValueError("amount must be a finite number")

    if amount <= 0:
        raise ValueError("amount must be greater than 0")
    return amount


def _format_decimal(value: Decimal | float | int) -> str:
    """Render a finite API number without rounding meaningful small rates to 0."""
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("rate must be a number") from exc
    if not number.is_finite():
        raise ValueError("rate must be a finite number")
    if number == 0:
        return "0"

    # Do not quantize to a fixed four decimal places: rates such as
    # 0.000042 (IDR → GBP) are valid and would otherwise be displayed as 0.
    rendered = format(number.normalize(), "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


async def _request_json(path: str, params: dict[str, Any] | None = None) -> Any:
    client = getattr(app.state, "http_client", None)
    if client is None or getattr(client, "is_closed", False):
        client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS)
        app.state.http_client = client
    response = await client.get(f"{FRANKFURTER_BASE_URL}{path}", params=params)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Frankfurter returned a non-object response")
    return payload


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
    <html>
      <head><title>Omi Frankfurter Currency Integration</title></head>
      <body>
        <h1>Omi Frankfurter Currency Integration</h1>
        <p>Use Omi chat tools to convert currencies and check reference rates.</p>
        <p><a href="/.well-known/omi-tools.json">Tool manifest</a></p>
      </body>
    </html>
    """


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/.well-known/omi-tools.json")
async def omi_tools() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "name": "Frankfurter Currency",
        "description": "Convert currencies and check latest reference exchange rates from Omi.",
        "tools": [
            {
                "name": "convert_currency",
                "description": "Convert an amount from one currency into one or more target currencies.",
                "endpoint": "/tools/convert_currency",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "amount": {"type": "number", "exclusiveMinimum": 0},
                        "from_currency": {"type": "string", "description": "3-letter currency code, such as USD."},
                        "to_currencies": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 1,
                            "maxItems": MAX_TARGET_CURRENCIES,
                        },
                    },
                    "required": ["amount", "from_currency", "to_currencies"],
                },
            },
            {
                "name": "get_latest_rates",
                "description": "Get latest reference rates for a base currency.",
                "endpoint": "/tools/get_latest_rates",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "base_currency": {"type": "string", "description": "3-letter currency code, such as USD."},
                        "to_currencies": {
                            "type": "array",
                            "items": {"type": "string"},
                            "maxItems": MAX_TARGET_CURRENCIES,
                        },
                    },
                    "required": ["base_currency"],
                },
            },
            {
                "name": "list_supported_currencies",
                "description": "List currencies supported by Frankfurter.",
                "endpoint": "/tools/list_supported_currencies",
                "method": "POST",
                "parameters": {"type": "object", "properties": {}},
            },
        ],
    }


@app.post("/tools/convert_currency", response_model=ChatToolResponse)
async def convert_currency(request: ConvertCurrencyRequest) -> ChatToolResponse:
    try:
        amount = _parse_amount(request.amount)

        # Frankfurter rejects a target currency identical to the source (HTTP 422
        # "bad currency pair") and, in a mixed request, just omits it from the
        # response. Resolve same-currency targets locally as a 1:1 identity instead
        # of sending them upstream.
        same_currency_targets = [code for code in request.to_currencies if code == request.from_currency]
        other_targets = [code for code in request.to_currencies if code != request.from_currency]

        rates: dict[str, Any] = {}
        base_curr = request.from_currency
        date_val = "latest"

        if other_targets:
            payload = await _request_json(
                "/latest",
                {
                    "amount": str(amount),
                    "from": request.from_currency,
                    "to": ",".join(other_targets),
                },
            )
            if not isinstance(payload, dict):
                return ChatToolResponse(error="no rates returned for the requested currencies")
            rates = payload.get("rates") if isinstance(payload.get("rates"), dict) else {}
            base_curr = payload.get("base") or request.from_currency
            date_val = payload.get("date") or "latest"

        for code in same_currency_targets:
            rates[code] = amount

        if not rates:
            return ChatToolResponse(error="no rates returned for the requested currencies")

        lines = [f"{_format_decimal(amount)} {base_curr} on {date_val}:"]
        for code in request.to_currencies:
            if code in rates and rates[code] is not None:
                try:
                    lines.append(f"- {code}: {_format_decimal(rates[code])}")
                except (ValueError, InvalidOperation):
                    continue
        if len(lines) == 1:
            return ChatToolResponse(error="no rates returned for the requested currencies")
        return ChatToolResponse(result="\n".join(lines))
    except (httpx.HTTPError, ValueError) as exc:
        return ChatToolResponse(error=f"currency conversion failed: {exc}")
    except Exception as exc:
        return ChatToolResponse(error=f"currency conversion failed: {exc}")


@app.post("/tools/get_latest_rates", response_model=ChatToolResponse)
async def get_latest_rates(request: LatestRatesRequest) -> ChatToolResponse:
    try:
        # Frankfurter never includes the base currency in its own rates, so a
        # mixed request (base=USD, to=[USD, EUR]) silently drops the USD line.
        # Resolve it locally as a 1:1 identity instead.
        wants_base = request.base_currency in request.to_currencies
        other_targets = [code for code in request.to_currencies if code != request.base_currency]

        rates: dict[str, Any] = {}
        base_curr = request.base_currency
        date_val = "latest"

        if not request.to_currencies or other_targets:
            params: dict[str, Any] = {"from": request.base_currency}
            if other_targets:
                params["to"] = ",".join(other_targets)
            payload = await _request_json("/latest", params)
            if not isinstance(payload, dict):
                return ChatToolResponse(error="no rates returned")
            rates = payload.get("rates") if isinstance(payload.get("rates"), dict) else {}
            base_curr = payload.get("base") or request.base_currency
            date_val = payload.get("date") or "latest"

        if wants_base:
            rates = dict(rates)
            rates[request.base_currency] = Decimal("1")

        if not rates:
            return ChatToolResponse(error="no rates returned")

        codes = request.to_currencies or sorted(rates.keys())
        lines = [f"Latest {base_curr} reference rates for {date_val}:"]
        for code in codes[:MAX_TARGET_CURRENCIES]:
            if code in rates and rates[code] is not None:
                try:
                    lines.append(f"- 1 {base_curr} = {_format_decimal(rates[code])} {code}")
                except (ValueError, InvalidOperation):
                    continue
        if len(lines) == 1:
            return ChatToolResponse(error="no rates returned")
        return ChatToolResponse(result="\n".join(lines))
    except (httpx.HTTPError, ValueError) as exc:
        return ChatToolResponse(error=f"latest rates request failed: {exc}")
    except Exception as exc:
        return ChatToolResponse(error=f"latest rates request failed: {exc}")


@app.post("/tools/list_supported_currencies", response_model=ChatToolResponse)
async def list_supported_currencies() -> ChatToolResponse:
    try:
        currencies = await _request_json("/currencies")
        if not isinstance(currencies, dict) or not currencies:
            return ChatToolResponse(error="currency list request returned no currencies")
        lines = ["Frankfurter supported currencies:"]
        for code, name in sorted(currencies.items()):
            lines.append(f"- {code}: {name}")
        return ChatToolResponse(result="\n".join(lines))
    except (httpx.HTTPError, ValueError) as exc:
        return ChatToolResponse(error=f"currency list request failed: {exc}")
    except Exception as exc:
        return ChatToolResponse(error=f"currency list request failed: {exc}")
