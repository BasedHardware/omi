"""Occasion step 2: decide automatic absorption before buying full notes.

Independent default-on kill switch; stored obligations still drain on rollback.
Owner rollout-meetings; review 2026-11-28.
"""

import os
from collections.abc import Mapping
from typing import Any


def enabled() -> bool:
    return os.getenv('CONVERSATION_MERGE_BEFORE_PROCESSING', 'true').strip().lower() not in {'false', '0', 'off', 'no'}


def already_processed(row: Mapping[str, Any]) -> bool:
    """Metadata-only donor fence; old rows fall back to their stored structure.

    A server-minimum title is not full processing. Prefer the explicit receipt
    when available; never decrypt or load member content to decide ownership.
    """
    if (
        row.get('summary_completed_at')
        or row.get('summary_output_present')
        or row.get('notes_llm_input_hash')
        or row.get('notes_llm_output_hash')
    ):
        return True
    structured = row.get('structured') or {}
    if isinstance(structured, Mapping) and (structured.get('action_items') or structured.get('events')):
        return True
    if (
        isinstance(structured, Mapping)
        and structured.get('title')
        and not (
            structured.get('title_provenance') == 'server_minimum'
            or row.get('summary_title_provenance') == 'server_minimum'
        )
    ):
        # Old title-only results may lack summary/hash receipts. Preserve their
        # identity conservatively; only proven server-minimum titles are raw.
        return True
    if row.get('summary_output_present') is False:
        return False
    return isinstance(structured, Mapping) and bool(structured.get('overview') or structured.get('sections'))
