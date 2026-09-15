"""Pydantic models for Omi CoinGecko Crypto Integration App."""

from typing import Any, List, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator


class _NullMeansDefault(BaseModel):
    """The Omi backend sends every optional tool parameter the model did not
    supply as JSON null (langchain-core 1.3.3 forwards defaulted fields), so a
    null must mean "use the default", not "invalid request"."""

    @model_validator(mode="before")
    @classmethod
    def drop_nulls(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if v is not None}
        return data


class ChatToolResponse(BaseModel):
    """Standard response model for Omi chat tool endpoints."""

    result: Optional[str] = None
    error: Optional[str] = None

    @model_validator(mode="after")
    def validate_result_or_error(self):
        if (self.result is None) == (self.error is None):
            raise ValueError("Exactly one of 'result' or 'error' must be provided.")
        return self


class GetCryptoPriceRequest(_NullMeansDefault):
    """Request model for getting cryptocurrency prices."""

    coin_ids: Union[List[str], str] = Field(
        ...,
        description="One or more CoinGecko coin IDs or comma-separated string, e.g. ['bitcoin', 'ethereum'] or 'solana'.",
    )
    vs_currency: Optional[str] = Field(
        default="usd",
        max_length=10,
        description="Target currency code (e.g., 'usd', 'eur', 'gbp', 'jpy').",
    )

    @field_validator("vs_currency", mode="before")
    @classmethod
    def coerce_vs_currency(cls, v: Optional[str]) -> str:
        if v is None:
            return "usd"
        cleaned = str(v).strip().lower()
        if len(cleaned) < 2:
            raise ValueError("vs_currency must contain at least 2 non-whitespace characters (e.g. 'usd').")
        return cleaned

    @field_validator("coin_ids", mode="before")
    @classmethod
    def normalize_coin_ids(cls, v: Union[List[str], str]) -> List[str]:
        if isinstance(v, str):
            ids = [i.strip().lower() for i in v.split(",") if i.strip()]
        elif isinstance(v, (list, tuple)):
            ids = [i.strip().lower() for i in v if isinstance(i, str) and i.strip()]
        else:
            ids = []
        if not ids:
            raise ValueError("At least one valid coin ID must be provided.")
        # Deduplicate while preserving order, max 10
        seen = set()
        deduped = []
        for coin_id in ids:
            if coin_id not in seen:
                deduped.append(coin_id)
                seen.add(coin_id)
        return deduped[:10]


class SearchCryptoCoinsRequest(_NullMeansDefault):
    """Request model for searching cryptocurrency coins."""

    query: str = Field(..., min_length=1, max_length=100, description="Coin name, ticker symbol, or keyword.")
    max_results: Optional[int] = Field(default=5, ge=1, le=15, description="Maximum number of search results to return.")

    @field_validator("max_results", mode="before")
    @classmethod
    def coerce_max_results(cls, v: Optional[int]) -> int:
        if v is None:
            return 5
        return int(v)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Query string cannot be empty.")
        return cleaned


class GetTrendingCryptoRequest(_NullMeansDefault):
    """Request model for fetching top trending cryptocurrencies."""

    limit: Optional[int] = Field(default=5, ge=1, le=15, description="Number of trending coins to return (1-15).")

    @field_validator("limit", mode="before")
    @classmethod
    def coerce_limit(cls, v: Optional[int]) -> int:
        if v is None:
            return 5
        return int(v)


class GetCryptoMarketOverviewRequest(_NullMeansDefault):
    """Request model for getting global crypto market overview."""

    limit: Optional[int] = Field(default=10, ge=1, le=20, description="Number of top market cap coins to return.")
    vs_currency: Optional[str] = Field(
        default="usd",
        max_length=10,
        description="Target currency code, e.g. 'usd'.",
    )

    @field_validator("limit", mode="before")
    @classmethod
    def coerce_limit(cls, v: Optional[int]) -> int:
        if v is None:
            return 10
        return int(v)

    @field_validator("vs_currency", mode="before")
    @classmethod
    def coerce_vs_currency(cls, v: Optional[str]) -> str:
        if v is None:
            return "usd"
        cleaned = str(v).strip().lower()
        if len(cleaned) < 2:
            raise ValueError("vs_currency must contain at least 2 non-whitespace characters (e.g. 'usd').")
        return cleaned
