from typing import List, Optional, Union
from pydantic import BaseModel, Field, field_validator


class GetCryptoPriceRequest(BaseModel):
    coin_ids: Union[str, List[str]] = Field(
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
    def normalize_coin_ids(cls, v: Union[str, List[str]]) -> List[str]:
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
                seen.add(coin_id)
                deduped.append(coin_id)
            if len(deduped) >= 10:
                break
        return deduped


class SearchCryptoCoinsRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Search query string (coin name, symbol, or token contract hint).",
    )
    max_results: int = Field(
        default=5,
        ge=1,
        le=15,
        description="Maximum number of search results to return (default 5, max 15).",
    )

    @field_validator("query")
    @classmethod
    def clean_query(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("query cannot be empty or whitespace only.")
        return cleaned


class GetTrendingCryptoRequest(BaseModel):
    limit: int = Field(
        default=5,
        ge=1,
        le=15,
        description="Number of trending coins to return (default 5, max 15).",
    )


class GetCryptoMarketOverviewRequest(BaseModel):
    vs_currency: str = Field(
        default="usd",
        min_length=2,
        max_length=10,
        description="Target currency for market cap and volume display (e.g. 'usd').",
    )
    limit: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Number of top market-cap coins to include (default 10, max 50).",
    )

    @field_validator("vs_currency")
    @classmethod
    def normalize_vs_currency(cls, v: str) -> str:
        cleaned = v.strip().lower()
        if len(cleaned) < 2:
            raise ValueError("vs_currency must contain at least 2 non-whitespace characters.")
        return cleaned
