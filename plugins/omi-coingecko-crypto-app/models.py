"""Pydantic models for Omi CoinGecko Crypto Integration App."""

from typing import List, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator


class ChatToolResponse(BaseModel):
    """Standard response model for Omi chat tool endpoints."""

    result: Optional[str] = None
    error: Optional[str] = None

    @model_validator(mode="after")
    def validate_result_or_error(self):
        if (self.result is None) == (self.error is None):
            raise ValueError("Exactly one of 'result' or 'error' must be provided.")
        return self


class GetCryptoPriceRequest(BaseModel):
    """Request model for getting cryptocurrency prices."""

    coin_ids: Union[List[str], str] = Field(
        ...,
        description="One or more CoinGecko coin IDs or comma-separated string, e.g. ['bitcoin', 'ethereum'] or 'solana'.",
    )
    vs_currency: str = Field(
        default="usd",
        min_length=2,
        max_length=10,
        description="Target currency code (e.g., 'usd', 'eur', 'gbp', 'jpy').",
    )

    @field_validator("vs_currency")
    @classmethod
    def normalize_vs_currency(cls, v: str) -> str:
        cleaned = v.strip().lower()
        if len(cleaned) < 2:
            raise ValueError("vs_currency must contain at least 2 non-whitespace characters (e.g. 'usd').")
        return cleaned

    @field_validator("coin_ids")
    @classmethod
    def normalize_coin_ids(cls, v: Union[List[str], str]) -> List[str]:
        if isinstance(v, str):
            ids = [i.strip().lower() for i in v.split(",") if i.strip()]
        else:
            ids = [i.strip().lower() for i in v if isinstance(i, str) and i.strip()]
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


class SearchCryptoCoinsRequest(BaseModel):
    """Request model for searching cryptocurrency coins."""

    query: str = Field(..., min_length=1, max_length=100, description="Coin name, ticker symbol, or keyword.")
    max_results: int = Field(default=5, ge=1, le=15, description="Maximum number of search results to return.")

    @field_validator("query")
    @classmethod
    def normalize_query(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Query string cannot be empty.")
        return cleaned


class GetTrendingCryptoRequest(BaseModel):
    """Request model for fetching top trending cryptocurrencies."""

    limit: int = Field(default=5, ge=1, le=15, description="Number of trending coins to return (1-15).")


class GetCryptoMarketOverviewRequest(BaseModel):
    """Request model for getting global crypto market overview."""

    limit: int = Field(default=10, ge=1, le=20, description="Number of top market cap coins to return.")
    vs_currency: str = Field(
        default="usd",
        min_length=2,
        max_length=10,
        description="Target currency code, e.g. 'usd'.",
    )

    @field_validator("vs_currency")
    @classmethod
    def normalize_vs_currency(cls, v: str) -> str:
        cleaned = v.strip().lower()
        if len(cleaned) < 2:
            raise ValueError("vs_currency must contain at least 2 non-whitespace characters (e.g. 'usd').")
        return cleaned
