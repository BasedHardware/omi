"""Read an existing STT classification; never infer language from short/noisy text."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def in_profile_segments(segments: Sequence[Any]) -> list[Any]:
    """Keep undetermined speech; suppress only an explicit out_of_profile decision."""

    def conformance(segment: Any) -> Any:
        if isinstance(segment, Mapping):
            return segment.get('language_conformance', segment.get('_language_conformance'))
        return getattr(segment, 'language_conformance', getattr(segment, '_language_conformance', None))

    return [segment for segment in segments if conformance(segment) != 'out_of_profile']
