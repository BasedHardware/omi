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


FRANKFURTER_BASE_URL = "https://api.frankfurter.app"
REQUEST_TIMEOUT_SECONDS = 10
MAX_TARGET_CURRENCIES = 10


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        app_instance.state.http_client = client
        yield


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

    @field_validator("from_currency")
    @classmethod
    def normalize_from_currency(cls, value: str) -> str:
        return _normalize_currency_code(value)

    @field_validator("to_currencies")
    @classmethod
    def normalize_to_currencies(cls, values: list[str]) -> list[str]:
        seen: set[str] = set()
        normalized: list[str] = []
        for value in values:
            code = _normalize_currency_code(value)
            if code not in seen:
                normalized.append(code)
                seen.add(code)
        return normalized


class LatestRatesRequest(BaseModel):
    base_currency: str = Field(..., min_length=3, max_length=3)
    to_currencies: list[str] = Field(default_factory=list, max_length=MAX_TARGET_CURRENCIES)

    @field_validator("base_currency")
    @classmethod
    def normalize_base_currency(cls, value: str) -> str:
        return _normalize_currency_code(value)

    @field_validator("to_currencies")
    @classmethod
    def normalize_to_currencies(cls, values: list[str]) -> list[str]:
        seen: set[str] = set()
        normalized: list[str] = []
        for value in values:
            code = _normalize_currency_code(value)
            if code not in seen:
                normalized.append(code)
                seen.add(code)
        return normalized


def _normalize_currency_code(value: str) -> str:
    code = value.strip().upper()
    if len(code) != 3 or not code.isalpha():
        raise ValueError("currency codes must be 3 letters, such as USD or EUR")
    return code


def _parse_amount(value: str | float | int) -> Decimal:
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("amount must be a number") from exc

    if amount <= 0:
        raise ValueError("amount must be greater than 0")
    return amount


def _format_decimal(value: Decimal | float | int) -> str:
    number = Decimal(str(value)).quantize(Decimal("0.0001")).normalize()
    return format(number, "f")


async def _request_json(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    client: httpx.AsyncClient = app.state.http_client
    response = await client.get(f"{FRANKFURTER_BASE_URL}{path}", params=params)
    response.raise_for_status()
    return response.json()


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
        payload = await _request_json(
            "/latest",
            {
                "amount": str(amount),
                "from": request.from_currency,
                "to": ",".join(request.to_currencies),
            },
        )
        rates = payload.get("rates") or {}
        if not rates:
            return ChatToolResponse(error="no rates returned for the requested currencies")

        lines = [
            f"{_format_decimal(amount)} {payload.get('base', request.from_currency)} on {payload.get('date', 'latest')}:"
        ]
        for code in request.to_currencies:
            if code in rates:
                lines.append(f"- {code}: {_format_decimal(rates[code])}")
        return ChatToolResponse(result="\n".join(lines))
    except (httpx.HTTPError, ValueError) as exc:
        return ChatToolResponse(error=f"currency conversion failed: {exc}")


@app.post("/tools/get_latest_rates", response_model=ChatToolResponse)
async def get_latest_rates(request: LatestRatesRequest) -> ChatToolResponse:
    try:
        params: dict[str, Any] = {"from": request.base_currency}
        if request.to_currencies:
            params["to"] = ",".join(request.to_currencies)

        payload = await _request_json("/latest", params)
        rates = payload.get("rates") or {}
        if not rates:
            return ChatToolResponse(error="no rates returned")

        codes = request.to_currencies or sorted(rates.keys())
        lines = [f"Latest {payload.get('base', request.base_currency)} reference rates for {payload.get('date', 'latest')}:"]
        for code in codes[:MAX_TARGET_CURRENCIES]:
            if code in rates:
                lines.append(f"- 1 {payload.get('base', request.base_currency)} = {_format_decimal(rates[code])} {code}")
        return ChatToolResponse(result="\n".join(lines))
    except (httpx.HTTPError, ValueError) as exc:
        return ChatToolResponse(error=f"latest rates request failed: {exc}")


@app.post("/tools/list_supported_currencies", response_model=ChatToolResponse)
async def list_supported_currencies() -> ChatToolResponse:
    try:
        currencies = await _request_json("/currencies")
        lines = ["Frankfurter supported currencies:"]
        for code, name in sorted(currencies.items()):
            lines.append(f"- {code}: {name}")
        return ChatToolResponse(result="\n".join(lines))
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"currency list request failed: {exc}")
