"""Prompt-only ``seg1..segN`` aliases for the notes prompt's turn headers, in place of stored segment UUIDs.

UUIDs cost ~20 tokens each as headers and citations; the model's ``source_segment_ids`` are mapped back to
stored ids before validation. Aliases are positional within one prompt and never stored; the ``seg`` prefix
keeps them out of ordinary prose, where citation repair matches known ids as whole words.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

PREFIX = 'seg'
_ALIAS = re.compile(rf'{PREFIX}\d+\Z')
# A turn header opens a line: ``[<segment-id> <speaker key>]`` or ``[<segment-id>]``.
_HEADER = re.compile(r'^\[(?P<id>[^\s\]]+)(?=[\s\]])', re.MULTILINE)


@dataclass(frozen=True)
class SegmentAliases:
    """``alias -> stored id`` for one prompt; empty means the prompt kept its stored ids."""

    to_id: Mapping[str, str] = field(default_factory=dict)

    def prompt_ids(self, segment_ids: Iterable[str]) -> list[str]:
        """The ids the prompt shows, in place of ``segment_ids``: aliases for the turns it numbered."""
        if not self.to_id:
            return [segment_id for segment_id in segment_ids if segment_id]
        return list(self.to_id)

    def restore(self, refs: Iterable[Any]) -> list[Any]:
        """Map cited aliases back to stored ids. Anything else passes through for the caller's validation."""
        return [self.to_id.get(ref, ref) if isinstance(ref, str) else ref for ref in refs]

    def restore_structured(self, structured: Any) -> Any:
        """Rewrite every section's and task's ``source_segment_ids`` in place; returns ``structured``."""
        if not self.to_id or structured is None:
            return structured
        for owner in [
            *(getattr(structured, 'sections', None) or ()),
            *(getattr(structured, 'action_items', None) or ()),
        ]:
            refs = getattr(owner, 'source_segment_ids', None)
            if refs:
                owner.source_segment_ids = self.restore(refs)
        return structured

    def speaker_map(self, speaker_map: Any) -> Any:
        """A copy whose rendered-id set is in alias space, where the renderer records one."""
        rendered = getattr(speaker_map, 'source_segment_ids', None)
        if not self.to_id or rendered is None:
            return speaker_map
        to_alias = {segment_id: alias for alias, segment_id in self.to_id.items()}
        aliased = copy.copy(speaker_map)
        aliased.source_segment_ids = frozenset(
            to_alias[segment_id] for segment_id in rendered if segment_id in to_alias
        )
        return aliased


def alias_transcript(transcript: str, segment_ids: Iterable[str]) -> tuple[str, SegmentAliases]:
    """Number the turn headers whose id is one of ``segment_ids``; other bracketed text is left alone.

    No-op when a stored id already looks like an alias, so a citation is never ambiguous.
    """
    known = {segment_id for segment_id in segment_ids if segment_id}
    if not known or any(_ALIAS.match(segment_id) for segment_id in known):
        return transcript, SegmentAliases()
    alias_of: dict[str, str] = {}

    def number(match: re.Match[str]) -> str:
        segment_id = match.group('id')
        if segment_id not in known:
            return match.group(0)
        alias = alias_of.get(segment_id)
        if alias is None:
            alias = alias_of[segment_id] = f'{PREFIX}{len(alias_of) + 1}'
        return f'[{alias}'

    aliased = _HEADER.sub(number, transcript)
    return aliased, SegmentAliases({alias: segment_id for segment_id, alias in alias_of.items()})
