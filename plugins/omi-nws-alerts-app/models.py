"""Data models and validation schemas for NWS Severe Weather Alerts Omi App.

Defines Pydantic v2 schemas for location queries, state alert lookups, national
weather hazard summaries, and standardized Omi ChatToolResponse envelopes.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

US_STATES_MAP: Dict[str, str] = {
    "AL": "ALABAMA",
    "AK": "ALASKA",
    "AZ": "ARIZONA",
    "AR": "ARKANSAS",
    "CA": "CALIFORNIA",
    "CO": "COLORADO",
    "CT": "CONNECTICUT",
    "DE": "DELAWARE",
    "FL": "FLORIDA",
    "GA": "GEORGIA",
    "HI": "HAWAII",
    "ID": "IDAHO",
    "IL": "ILLINOIS",
    "IN": "INDIANA",
    "IA": "IOWA",
    "KS": "KANSAS",
    "KY": "KENTUCKY",
    "LA": "LOUISIANA",
    "ME": "MAINE",
    "MD": "MARYLAND",
    "MA": "MASSACHUSETTS",
    "MI": "MICHIGAN",
    "MN": "MINNESOTA",
    "MS": "MISSISSIPPI",
    "MO": "MISSOURI",
    "MT": "MONTANA",
    "NE": "NEBRASKA",
    "NV": "NEVADA",
    "NH": "NEW HAMPSHIRE",
    "NJ": "NEW JERSEY",
    "NM": "NEW MEXICO",
    "NY": "NEW YORK",
    "NC": "NORTH CAROLINA",
    "ND": "NORTH DAKOTA",
    "OH": "OHIO",
    "OK": "OKLAHOMA",
    "OR": "OREGON",
    "PA": "PENNSYLVANIA",
    "RI": "RHODE ISLAND",
    "SC": "SOUTH CAROLINA",
    "SD": "SOUTH DAKOTA",
    "TN": "TENNESSEE",
    "TX": "TEXAS",
    "UT": "UTAH",
    "VT": "VERMONT",
    "VA": "VIRGINIA",
    "WA": "WASHINGTON",
    "WV": "WEST VIRGINIA",
    "WI": "WISCONSIN",
    "WY": "WYOMING",
    "DC": "DISTRICT OF COLUMBIA",
    "PR": "PUERTO RICO",
    "VI": "VIRGIN ISLANDS",
    "GU": "GUAM",
    "AS": "AMERICAN SAMOA",
    "MP": "NORTHERN MARIANA ISLANDS",
}

# Reverse mapping for full state names to 2-letter codes
NAME_TO_CODE: Dict[str, str] = {v.upper(): k for k, v in US_STATES_MAP.items()}


class LocationAlertRequest(BaseModel):
    """Request payload for GPS coordinate weather alert lookups."""

    model_config = ConfigDict(str_strip_whitespace=True)

    latitude: float = Field(
        ...,
        ge=-90.0,
        le=90.0,
        allow_inf_nan=False,
        description="WGS84 Latitude coordinate (e.g. 32.7767 for Dallas, TX).",
    )
    longitude: float = Field(
        ...,
        ge=-180.0,
        le=180.0,
        allow_inf_nan=False,
        description="WGS84 Longitude coordinate (e.g. -96.7970 for Dallas, TX).",
    )
    severity: Optional[str] = Field(
        default=None,
        description="Optional severity filter: 'Extreme', 'Severe', 'Moderate', 'Minor', or 'Unknown'.",
    )

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip().title()
        valid = {"Extreme", "Severe", "Moderate", "Minor", "Unknown"}
        if cleaned not in valid:
            raise ValueError(
                f"Invalid severity '{v}'. Allowed values: {', '.join(sorted(valid))}"
            )
        return cleaned


class StateAlertRequest(BaseModel):
    """Request payload for state-wide weather alert lookups."""

    model_config = ConfigDict(str_strip_whitespace=True)

    state: str = Field(
        ...,
        min_length=2,
        max_length=50,
        description="US state code (e.g. 'TX', 'CA') or full state name (e.g. 'Texas', 'California').",
    )
    severity: Optional[str] = Field(
        default=None,
        description="Optional severity filter: 'Extreme', 'Severe', 'Moderate', 'Minor', or 'Unknown'.",
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum number of alerts to return (1-10, default 5).",
    )

    @field_validator("state")
    @classmethod
    def normalize_state(cls, v: str) -> str:
        cleaned = v.strip().upper()
        if cleaned in US_STATES_MAP:
            return cleaned
        if cleaned in NAME_TO_CODE:
            return NAME_TO_CODE[cleaned]
        raise ValueError(
            f"Invalid US state or territory '{v}'. Please provide a valid 2-letter postal code (e.g. 'TX', 'FL') or full name."
        )

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip().title()
        valid = {"Extreme", "Severe", "Moderate", "Minor", "Unknown"}
        if cleaned not in valid:
            raise ValueError(
                f"Invalid severity '{v}'. Allowed values: {', '.join(sorted(valid))}"
            )
        return cleaned


class NationalSummaryRequest(BaseModel):
    """Request payload for nationwide severe weather emergency summary."""

    model_config = ConfigDict(str_strip_whitespace=True)

    severity_threshold: Optional[str] = Field(
        default="Severe",
        description="Minimum severity threshold to include in detailed summary ('Extreme' or 'Severe', default 'Severe').",
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum number of critical warnings to highlight (1-10, default 5).",
    )

    @field_validator("severity_threshold")
    @classmethod
    def validate_threshold(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return "Severe"
        cleaned = v.strip().title()
        if cleaned not in {"Extreme", "Severe"}:
            raise ValueError("severity_threshold must be either 'Extreme' or 'Severe'")
        return cleaned


class WeatherAlertItem(BaseModel):
    """Normalized representation of an active National Weather Service hazard alert."""

    id: str
    event: str
    severity: str
    urgency: str
    certainty: str
    headline: str
    description: Optional[str] = None
    instruction: Optional[str] = None
    onset: Optional[datetime] = None
    expires: Optional[datetime] = None
    area_desc: Optional[str] = None
    sender_name: Optional[str] = None


class ChatToolResponse(BaseModel):
    """Standardized response envelope for Omi Chat Tools."""

    result: Optional[str] = None
    error: Optional[str] = None

    def __init__(self, **data: Any):
        # Backward-compatibility alias shim for legacy plugin callers passing 'response' instead of 'result' (e.g. plugins/basic conventions)
        if "response" in data and "result" not in data:
            data["result"] = data.pop("response")
        super().__init__(**data)
