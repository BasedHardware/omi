"""Versioned, privacy-safe cassette identity and request fingerprints."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Any, Mapping

from .redaction import redact_value

SCHEMA_VERSION = 1


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _canonical_request(value: Any) -> Any:
    """Canonicalize a request after recursively removing/redacting sensitive data.

    The resulting representation is only used transiently to calculate a
    one-way digest.  It is never written into a manifest or report.
    """
    return redact_value(value, drop_sensitive=True)


@dataclass(frozen=True)
class CassetteIdentity:
    """Identity tuple for an individual provider call.

    ``anon_session`` and ``parent_event_anon`` must already be anonymous,
    stable identifiers; raw user, device, and event IDs are not accepted here.
    """

    anon_session: str
    provider_lane: str
    route_or_model: str
    call_ordinal: int
    retry_attempt: int
    parent_event_anon: str

    def __post_init__(self) -> None:
        text_fields = (
            self.anon_session,
            self.provider_lane,
            self.route_or_model,
            self.parent_event_anon,
        )
        if any(not isinstance(value, str) or not value.strip() for value in text_fields):
            raise ValueError("cassette identity fields must be non-empty strings")
        if self.call_ordinal < 0 or self.retry_attempt < 0:
            raise ValueError("call_ordinal and retry_attempt must be non-negative")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def key(self) -> str:
        """Stable filesystem-safe key; does not include request content."""
        return sha256(_canonical_json(self.as_dict()).encode()).hexdigest()


@dataclass(frozen=True)
class RequestFingerprint:
    algorithm: str
    digest: str

    @classmethod
    def from_request(cls, request: Mapping[str, Any] | Any) -> "RequestFingerprint":
        canonical = _canonical_json(_canonical_request(request))
        return cls(algorithm="sha256-canonical-redacted-v1", digest=sha256(canonical.encode()).hexdigest())

    def as_dict(self) -> dict[str, str]:
        return {"algorithm": self.algorithm, "digest": self.digest}
