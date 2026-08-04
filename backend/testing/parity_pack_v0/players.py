"""Cassette-backed STT/LLM loopback adapters with strict invocation accounting."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from .schema import CassetteIdentity, RequestFingerprint


class CassetteTopologyError(AssertionError):
    pass


@dataclass(frozen=True)
class PlayedEvent:
    direction: str
    dt_ms: int
    payload: Mapping[str, Any]


class InvocationTopology:
    """Consumes an ordered cassette plan and rejects every topology mismatch."""

    def __init__(self, paths: tuple[Path, ...]) -> None:
        self._documents = tuple(_read(path) for path in paths)
        self._position = 0

    def consume(self, identity: CassetteIdentity, request: Mapping[str, Any]) -> tuple[PlayedEvent, ...]:
        if self._position == len(self._documents):
            raise CassetteTopologyError(f"extra invocation: {identity.key()}")
        document = self._documents[self._position]
        if document["identity"] != identity.as_dict():
            raise CassetteTopologyError(
                f"out-of-order cassette: expected={document['identity']}, actual={identity.as_dict()}"
            )
        if document["request_fingerprint"] != RequestFingerprint.from_request(request).as_dict():
            raise CassetteTopologyError("cassette request fingerprint mismatch")
        self._position += 1
        return tuple(PlayedEvent(**event) for event in document["events"])

    def assert_complete(self) -> None:
        if self._position != len(self._documents):
            raise CassetteTopologyError(f"unused cassettes: {len(self._documents) - self._position}")


class _CassettePlayer:
    lane: str

    def __init__(self, topology: InvocationTopology) -> None:
        self._topology = topology

    def play(self, identity: CassetteIdentity, request: Mapping[str, Any], emit: Callable[[PlayedEvent], None]) -> None:
        if identity.provider_lane != self.lane:
            raise CassetteTopologyError(f"{self.lane} player cannot play {identity.provider_lane}")
        for event in self._topology.consume(identity, request):
            emit(event)


class STTCassettePlayer(_CassettePlayer):
    """Drop-in loopback callback adapter for streaming STT fake observations."""

    lane = "stt"


class LLMCassettePlayer(_CassettePlayer):
    """Drop-in loopback callback adapter for outbound LLM fake observations."""

    lane = "llm"


def _read(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema_version") != 1:
        raise ValueError(f"unsupported cassette schema: {path}")
    return document
