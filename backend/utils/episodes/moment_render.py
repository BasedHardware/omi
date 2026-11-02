"""Shared, owner-safe cluster rendering for episode moments (L3 contract for L4)."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from config.refactor_modes import serving_for, shadow_or_serve
from utils.llm.notes_refactor_metrics import shadow
from utils.conversations.transcript_for_llm import owner_safe_transcript_segments, render_cluster_transcript
from utils.llm.notes_language_inputs import in_profile_segments


def name_segments(segments: Sequence[Mapping[str, Any]], names: Mapping[str, str]) -> list[dict[str, Any]]:
    """Prepare prompt-only copies using the notes owner gate. Keep this cross-lane signature."""
    safe = list(segments)
    if shadow_or_serve('NOTES_PACKET_V2_MODE'):
        safe, _note = owner_safe_transcript_segments(segments)
        cleared = sum(
            bool(original.get('is_user')) != bool(copy.get('is_user')) for original, copy in zip(segments, safe)
        )
        shadow('moment_owner_gate', 'disagree' if cleared else 'agree', cleared=cleared)
    serve = serving_for('NOTES_PACKET_V2_MODE', None)
    # Per-user admission happens in incremental.render_moment(uid=...). This
    # signature has no uid, so shadow returns the original name-only projection.
    if not serve:
        safe = list(segments)
    out = []
    for segment in safe:
        item = dict(segment)
        # A stale display name cannot restore a claim the owner gate just cleared.
        if serve:
            item.pop('person_name', None)
            item.pop('speaker_name', None)
        if item.get('person_id') and names.get(str(item['person_id'])):
            item['person_name'] = names[str(item['person_id'])]
        out.append(item)
    return out


def render_segments(
    segments: Sequence[Mapping[str, Any]],
    *,
    evidence: Any = None,
    owner_name: str | None = None,
) -> tuple[str, int]:
    """Same voice-key map as notes. No copyable Speaker N:/Owner: dialogue labels."""
    selected = in_profile_segments(segments)
    names = {
        str(row['person_id']): str(row['person_name'])
        for row in selected
        if row.get('person_id') and row.get('person_name')
    }
    text, _map = render_cluster_transcript(selected, names=names, owner_name=owner_name, evidence=evidence)
    return text, sum(len(str(row.get('text') or '').split()) for row in selected)
