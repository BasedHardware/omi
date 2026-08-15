"""Whether a source's canonical retraction is currently required and possible.

Retraction runs through the canonical replace boundary, which
``_require_canonical_intake_enabled()`` fences whenever ``MEMORY_MODE`` is not
write/read. Callers that must delete a conversation therefore have to tell
"there is nothing to retract" apart from "retraction is broken": the first is
safe to skip, the second must abort so live memories are never left pointing at
a deleted conversation.

The fence closes *intake*, so a conversation ingested while it was closed has
nothing to retract in the first place. These are the unfenced reads that decide.
"""

from __future__ import annotations

from typing import Any

from config.memory_rollout import MemoryRolloutMode, rollout_mode_env_value
from models.product_memory import MemoryItemStatus
from utils.memory.memory_service import MemoryService
from utils.memory.product_memory_read_service import fetch_authoritative_product_memory_items_for_source


def canonical_intake_is_fenced() -> bool:
    """Whether the deployment-wide fence currently blocks canonical mutations."""
    try:
        return MemoryRolloutMode(rollout_mode_env_value()) not in {MemoryRolloutMode.write, MemoryRolloutMode.read}
    except ValueError:
        # A malformed mode fences intake too, so treat it as closed.
        return True


def source_retraction_is_a_noop(
    uid: str, conversation_id: str, *, memory_service: MemoryService, db_client: Any
) -> bool:
    """Whether retracting this source would tombstone nothing at all.

    Covers everything ``MemoryService.retract_conversation_memories`` touches,
    not just the canonical cohort: it also tombstones historical live records
    whose ``conversation_id`` or evidence names the source. A source with
    historical rows but no canonical items still has evidence that would be left
    dangling, so it is not a no-op.

    Streams the history with ``iter_all_live`` rather than ``all_live``: the
    latter is documented for explicit export and materializes and sorts every
    live row. Only the first match matters here.
    """
    canonical_items = fetch_authoritative_product_memory_items_for_source(
        uid,
        conversation_id,
        db_client=db_client,
    )
    if any(item.status != MemoryItemStatus.tombstoned for item in canonical_items):
        return False

    for record in memory_service.history.iter_all_live(uid):
        memory = record.memory
        if memory.conversation_id == conversation_id:
            return False
        if any(
            evidence.source_type == "conversation" and evidence.source_id == conversation_id
            for evidence in memory.evidence
        ):
            return False
    return True


def retraction_can_be_skipped(uid: str, conversation_id: str, *, memory_service: MemoryService, db_client: Any) -> bool:
    """Skip retraction only while the fence is closed and there is nothing to retract.

    With intake enabled, retraction works and a source write can land between
    this check and the delete, so the caller must always retract and let a real
    failure abort. The ``and`` short-circuits, so the history scan never runs on
    the healthy path.
    """
    return canonical_intake_is_fenced() and source_retraction_is_a_noop(
        uid,
        conversation_id,
        memory_service=memory_service,
        db_client=db_client,
    )
