from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import quote


UBER_WEB_BASE_URL = "https://m.uber.com/ul/"
UBER_APP_BASE_URL = "uber://"

_LAT_MIN, _LAT_MAX = -90.0, 90.0
_LNG_MIN, _LNG_MAX = -180.0, 180.0


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


def _validate_coordinate(lat: float | None, lng: float | None) -> None:
    """Raise ValueError if either coordinate is non-finite or out of geographic range."""
    if lat is None and lng is None:
        return
    if lat is None or lng is None:
        raise ValueError("latitude and longitude must be provided together")
    if not math.isfinite(lat):
        raise ValueError(f"latitude must be a finite number, got {lat!r}")
    if not math.isfinite(lng):
        raise ValueError(f"longitude must be a finite number, got {lng!r}")
    if not (_LAT_MIN <= lat <= _LAT_MAX):
        raise ValueError(
            f"latitude {lat!r} is out of range [{_LAT_MIN}, {_LAT_MAX}]"
        )
    if not (_LNG_MIN <= lng <= _LNG_MAX):
        raise ValueError(
            f"longitude {lng!r} is out of range [{_LNG_MIN}, {_LNG_MAX}]"
        )


def build_location(
    *,
    latitude: float | int | str | None = None,
    longitude: float | int | str | None = None,
    nickname: str | None = None,
    formatted_address: str | None = None,
) -> UberLocation:
    lat = _normalize_float(latitude)
    lng = _normalize_float(longitude)
    _validate_coordinate(lat, lng)
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
