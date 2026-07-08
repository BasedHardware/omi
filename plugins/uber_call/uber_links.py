from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
from urllib.parse import quote


UBER_WEB_BASE_URL = "https://m.uber.com/ul/"
UBER_APP_BASE_URL = "uber://"


@dataclass(frozen=True)
class UberLocation:
    latitude: float | None = None
    longitude: float | None = None
    nickname: str | None = None
    formatted_address: str | None = None

    def has_coordinates(self) -> bool:
        return self.latitude is not None and self.longitude is not None

    def has_label(self) -> bool:
        return bool(self.nickname or self.formatted_address)


@dataclass(frozen=True)
class UberDeepLinks:
    web_link: str
    app_link: str


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    return cleaned or None


def _normalize_float(value: float | int | str | None) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def build_location(
    *,
    latitude: float | int | str | None = None,
    longitude: float | int | str | None = None,
    nickname: str | None = None,
    formatted_address: str | None = None,
) -> UberLocation:
    lat = _normalize_float(latitude)
    lng = _normalize_float(longitude)
    return UberLocation(
        latitude=lat,
        longitude=lng,
        nickname=_clean_text(nickname),
        formatted_address=_clean_text(formatted_address),
    )


def _append_location_params(params: list[tuple[str, str]], prefix: str, location: UberLocation) -> None:
    if location.has_coordinates():
        params.append((f"{prefix}[latitude]", str(location.latitude)))
        params.append((f"{prefix}[longitude]", str(location.longitude)))
    if location.nickname:
        params.append((f"{prefix}[nickname]", location.nickname))
    if location.formatted_address:
        params.append((f"{prefix}[formatted_address]", location.formatted_address))


def _encode_query(params: Iterable[tuple[str, str]]) -> str:
    return "&".join(f"{quote(key, safe='[]')}={quote(value, safe='')}" for key, value in params)


def build_uber_deep_links(
    *,
    destination: str | None = None,
    pickup: UberLocation | None = None,
    dropoff: UberLocation | None = None,
    product_id: str | None = None,
) -> UberDeepLinks:
    destination_label = _clean_text(destination)
    pickup_location = pickup or UberLocation()
    dropoff_location = dropoff or UberLocation()

    if destination_label and not dropoff_location.has_label():
        dropoff_location = UberLocation(
            latitude=dropoff_location.latitude,
            longitude=dropoff_location.longitude,
            nickname=destination_label,
            formatted_address=destination_label,
        )

    if not destination_label and not dropoff_location.has_label() and not dropoff_location.has_coordinates():
        raise ValueError("A destination or dropoff location is required")

    params: list[tuple[str, str]] = [("action", "setPickup")]

    if pickup_location.has_coordinates() or pickup_location.has_label():
        _append_location_params(params, "pickup", pickup_location)
    else:
        params.append(("pickup", "my_location"))

    _append_location_params(params, "dropoff", dropoff_location)

    cleaned_product_id = _clean_text(product_id)
    if cleaned_product_id:
        params.append(("product_id", cleaned_product_id))

    query = _encode_query(params)
    return UberDeepLinks(
        web_link=f"{UBER_WEB_BASE_URL}?{query}",
        app_link=f"{UBER_APP_BASE_URL}?{query}",
    )

