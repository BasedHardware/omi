"""On-disk manifest contract for a restricted local parity pack."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .schema import CassetteIdentity, RequestFingerprint


def sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class PackCase:
    case_id: str
    inputs_ref: str
    cassette_refs: tuple[str, ...]
    expected_outcomes: Mapping[str, Any]
    invariant_ids: tuple[str, ...]
    identity: CassetteIdentity
    request_fingerprint: RequestFingerprint

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "inputs_ref": self.inputs_ref,
            "cassette_refs": list(self.cassette_refs),
            "expected_outcomes": dict(self.expected_outcomes),
            "invariant_ids": list(self.invariant_ids),
            "identity": self.identity.as_dict(),
            "request_fingerprint": self.request_fingerprint.as_dict(),
        }


def build_manifest(*, pack_id: str, cases: Sequence[PackCase], artifact_hashes: Mapping[str, str]) -> dict[str, Any]:
    if not pack_id or not cases:
        raise ValueError("pack_id and at least one case are required")
    return {
        "schema_version": 1,
        "pack_id": pack_id,
        "cases": [case.as_dict() for case in cases],
        "artifact_hashes": dict(sorted(artifact_hashes.items())),
    }


def write_manifest(path: Path, manifest: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
