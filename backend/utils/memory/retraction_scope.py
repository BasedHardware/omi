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

from typing import Any, Optional, Set, Tuple

from config.memory_rollout import MemoryRolloutMode, rollout_mode_env_value
from models.product_memory import MemoryItemStatus
from utils.memory.memory_service import MemoryService
from utils.memory.product_memory_read_service import fetch_authoritative_product_memory_items_for_source
from utils.memory.v3.account_generation_source import (
    V3AccountGenerationFailureReason,
    read_memory_v3_trusted_account_generation,
)


def canonical_intake_is_fenced() -> bool:
    """Whether the deployment-wide fence currently blocks canonical mutations."""
    try:
        return MemoryRolloutMode(rollout_mode_env_value()) not in {MemoryRolloutMode.write, MemoryRolloutMode.read}
    except ValueError:
        # A malformed mode fences intake too, so treat it as closed.
        return True


def historical_source_conversation_ids(uid: str, *, memory_service: MemoryService) -> Set[str]:
    """Conversation ids referenced by the user's live historical memories.

    One pass, reusable. Merge deletes several sources in a row and would
    otherwise rescan the whole history per source; the heavy cohort reaches
    ~6.3k live rows (13 pages), so that is 13 page reads per source instead of
    13 for the whole merge.
    """
    referenced: Set[str] = set()
    for record in memory_service.history.iter_all_live(uid):
        memory = record.memory
        if memory.conversation_id:
            referenced.add(memory.conversation_id)
        for evidence in memory.evidence:
            if evidence.source_type == "conversation" and evidence.source_id:
                referenced.add(evidence.source_id)
    return referenced


def source_retraction_is_a_noop(
    uid: str,
    conversation_id: str,
    *,
    memory_service: MemoryService,
    db_client: Any,
    historical_source_ids: Optional[Set[str]] = None,
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

    if historical_source_ids is not None:
        return conversation_id not in historical_source_ids

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


def canonical_commit_epoch(uid: str, *, db_client: Any) -> Optional[Tuple[Any, ...]]:
    """A value that changes whenever canonical state for ``uid`` advances.

    ``memory_state/head`` is written by the canonical apply boundary, so its
    generation/sequence/commit id move on every committed canonical write.

    Returns ``None`` when the epoch cannot be established. Only a *missing* head
    is a knowable stable state — that is the normal shape for an account with no
    canonical memories, which is the case this module exists to allow. Every
    other failure, a transient read error most of all, means the epoch is
    unknown: comparing two unknowns for equality would read as "nothing changed"
    and hand back a skip during exactly the outage where we can least justify
    one. Callers must treat ``None`` as "do not skip".
    """
    trusted = read_memory_v3_trusted_account_generation(uid=uid, db_client=db_client)
    if trusted.read_error_reason is not None:
        if trusted.read_error_reason is V3AccountGenerationFailureReason.MISSING_STATE_HEAD:
            return ("missing_state_head",)
        return None
    return (trusted.account_generation, trusted.commit_sequence, trusted.head_commit_id)


def retraction_can_be_skipped(
    uid: str,
    conversation_id: str,
    *,
    memory_service: MemoryService,
    db_client: Any,
    historical_source_ids: Optional[Set[str]] = None,
) -> bool:
    """Skip retraction only while the fence is closed and there is nothing to retract.

    With intake enabled, retraction works and a source write can land between
    this check and the delete, so the caller must always retract and let a real
    failure abort. The ``and`` short-circuits, so the history scan never runs on
    the healthy path.

    Two staleness guards around the scope reads, because "the scope is empty"
    is only safe if it was still empty when the decision was made:

    * the fence is re-read, so a fence that opened during the reads refuses the
      skip rather than acting on a snapshot taken under the old mode;
    * the canonical commit epoch is captured before and compared after, so a
      write that was already in flight against the pre-fence mode and commits
      during the reads is caught even though the fence never moved. An epoch
      that cannot be established at either end refuses the skip rather than
      comparing two unknowns and calling them equal.

    Neither makes check-and-delete atomic — that needs a transaction spanning
    the memory store and the conversation document. They bound the window to
    "nothing canonical committed while we looked".
    """
    if not canonical_intake_is_fenced():
        return False
    epoch_before = canonical_commit_epoch(uid, db_client=db_client)
    if epoch_before is None:
        return False
    is_noop = source_retraction_is_a_noop(
        uid,
        conversation_id,
        memory_service=memory_service,
        db_client=db_client,
        historical_source_ids=historical_source_ids,
    )
    if not is_noop or not canonical_intake_is_fenced():
        return False
    epoch_after = canonical_commit_epoch(uid, db_client=db_client)
    return epoch_after is not None and epoch_after == epoch_before
