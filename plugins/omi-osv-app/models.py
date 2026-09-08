"""Public package lookup inputs; Omi identity/location metadata is ignored."""

from typing import Annotated, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

Ecosystem = Literal["PyPI", "npm", "Go", "Maven", "RubyGems", "crates.io", "NuGet", "Packagist", "Pub"]
PackageName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=200, pattern=r"^[A-Za-z0-9@][A-Za-z0-9._:/@+-]*$"
    ),
]
Version = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._+!~:-]*$"),
]
VulnerabilityID = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$"),
]


class QueryPackageRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ecosystem: Ecosystem
    package_name: PackageName
    version: Version
    limit: int = Field(default=5, ge=1, le=10, strict=True)

    @field_validator("ecosystem", mode="before")
    @classmethod
    def normalize_ecosystem(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        names = get_args(Ecosystem)
        return next((name for name in names if name.casefold() == value.strip().casefold()), value)


class VulnerabilityRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    vulnerability_id: VulnerabilityID
