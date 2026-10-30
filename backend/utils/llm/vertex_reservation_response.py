"""Bounded, content-free proof of a completed Vertex provisioned response."""

import json
from collections.abc import Mapping
from typing import Any


class ReservationResponseEvidence:
    """Accumulate completion and traffic metadata, never generated content.

    A stream must end at an SSE frame boundary, with every seen candidate
    finished and no contradictory traffic metadata. EOF alone is not success.
    """

    def __init__(self) -> None:
        self._buffer = b''
        self._invalid = False
        self._traffic: set[str] = set()
        self._candidates: set[int] = set()
        self._content: set[int] = set()
        self._finished: set[int] = set()

    def observe(self, payload: Any) -> None:
        if not isinstance(payload, Mapping) or 'error' in payload:
            self._invalid = True
            return
        usage = payload.get('usageMetadata', {})
        if not isinstance(usage, Mapping):
            self._invalid = True
            return
        if 'trafficType' in usage:
            traffic = usage['trafficType']
            self._traffic.add('PROVISIONED_THROUGHPUT' if traffic == 'PROVISIONED_THROUGHPUT' else 'invalid')
        candidates = payload.get('candidates', [])
        if not isinstance(candidates, list) or len(candidates) > 16:
            self._invalid = True
            return
        for offset, candidate in enumerate(candidates):
            if not isinstance(candidate, Mapping):
                self._invalid = True
                continue
            index = candidate.get('index', offset)
            if type(index) is not int or not 0 <= index < 16:
                self._invalid = True
                continue
            self._candidates.add(index)
            content = candidate.get('content', {})
            parts = content.get('parts', []) if isinstance(content, Mapping) else []
            if isinstance(parts, list) and any(
                isinstance(part, Mapping)
                and (
                    isinstance(part.get('text'), str)
                    and bool(part['text'])
                    or isinstance(part.get('functionCall'), Mapping)
                    and bool(part['functionCall'].get('name'))
                )
                for part in parts
            ):
                self._content.add(index)
            finish = candidate.get('finishReason')
            if isinstance(finish, str) and finish in {'STOP', 'MAX_TOKENS', 'SAFETY', 'RECITATION', 'OTHER'}:
                self._finished.add(index)

    def feed(self, chunk: bytes) -> None:
        if self._invalid:
            return
        self._buffer += chunk
        self._buffer = self._buffer.replace(b'\r\n', b'\n')
        while b'\n\n' in self._buffer:
            frame, self._buffer = self._buffer.split(b'\n\n', 1)
            data = b'\n'.join(line[5:].lstrip() for line in frame.splitlines() if line.startswith(b'data:'))
            if not data or data == b'[DONE]':
                continue
            try:
                self.observe(json.loads(data))
            except (TypeError, ValueError):
                self._invalid = True
        if len(self._buffer) > 1024 * 1024:
            self._buffer = b''
            self._invalid = True

    def traffic_type(self) -> str | None:
        if (
            not self._invalid
            and not self._buffer.strip()
            and self._candidates
            and self._candidates <= self._content & self._finished
            and self._traffic == {'PROVISIONED_THROUGHPUT'}
        ):
            return 'PROVISIONED_THROUGHPUT'
        return None


def completed_provisioned_traffic(payload: Any) -> str | None:
    evidence = ReservationResponseEvidence()
    evidence.observe(payload)
    return evidence.traffic_type()
