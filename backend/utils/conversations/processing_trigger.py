"""Why a conversation is being processed, and everything that follows from it.

Callers of ``process_conversation`` name a ``ProcessingTrigger`` and nothing
else about mode. Each trigger's row in ``PROCESSING_MODES`` fixes whether
enrichment runs now, whether it is a reprocess, and whether relevance is
assessed. Independent booleans at call sites let "run now" silently imply
"skip discard" on first-processing paths; one row per reason makes every
combination a reviewed decision.

Stdlib-only: sync intake and several stubbed test harnesses import it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class ProcessingTrigger(str, Enum):
    CAPTURE_END = 'capture_end'  # listen finalization, developer/import create
    CLIENT_FINALIZE = 'client_finalize'  # a client ends the conversation
    SYNC_UPDATE = 'sync_update'  # offline sync created or appended to it
    FIRST_OPEN = 'first_open'  # deferred enrichment when the user opens it
    BACKLOG_CHOICE = 'backlog_choice'  # authenticated explicit funded-backlog consent
    USER_REPROCESS = 'user_reprocess'  # the user asked to reprocess it
    MERGE = 'merge'  # the user merged conversations into it
    SMART_MERGE = 'smart_merge'  # a finished conversation was folded into this survivor
    SERVER_RECOVERY = 'server_recovery'
    SILENT_BACKFILL = 'silent_backfill'  # operator-approved historical summary, no derived work


class RelevancePolicy(str, Enum):
    ASSESS = 'assess'
    KEEP = 'keep'


@dataclass(frozen=True)
class ProcessingMode:
    # Enrich now: never take the desktop capture-time deferral.
    run_now: bool
    # Regenerating an existing conversation: no created-side effects (folder
    # assignment, webhooks, first-completion telemetry), non-user app usage.
    reprocess: bool
    # KEEP for triggers that are themselves a user action on this row, plus
    # SERVER_RECOVERY: the repair run must never discard the recovered copy.
    relevance: RelevancePolicy


_ASSESS, _KEEP = RelevancePolicy.ASSESS, RelevancePolicy.KEEP

PROCESSING_MODES: Mapping[ProcessingTrigger, ProcessingMode] = MappingProxyType(
    {
        ProcessingTrigger.CAPTURE_END: ProcessingMode(False, False, _ASSESS),
        # Ending a capture is not a judgment about its content; a discard here
        # stays one tap from restore.
        ProcessingTrigger.CLIENT_FINALIZE: ProcessingMode(True, False, _ASSESS),
        # Reassessed over the whole merged transcript on every append, so a
        # fragment that later gains real speech is promoted automatically.
        ProcessingTrigger.SYNC_UPDATE: ProcessingMode(True, True, _ASSESS),
        ProcessingTrigger.FIRST_OPEN: ProcessingMode(True, False, _KEEP),
        ProcessingTrigger.BACKLOG_CHOICE: ProcessingMode(True, True, _KEEP),
        ProcessingTrigger.USER_REPROCESS: ProcessingMode(True, True, _KEEP),
        ProcessingTrigger.MERGE: ProcessingMode(True, False, _KEEP),
        # Regenerates an existing, already-kept survivor over its longer transcript:
        # no created-side effects, and relevance must not hide the whole occasion.
        ProcessingTrigger.SMART_MERGE: ProcessingMode(True, True, _KEEP),
        ProcessingTrigger.SERVER_RECOVERY: ProcessingMode(True, True, _KEEP),
        ProcessingTrigger.SILENT_BACKFILL: ProcessingMode(True, True, _KEEP),
    }
)


def is_recovery_trigger(trigger: ProcessingTrigger) -> bool:
    return trigger in {ProcessingTrigger.SERVER_RECOVERY, ProcessingTrigger.SILENT_BACKFILL}


def trigger_for_finalization_job(job: Mapping[str, object]) -> ProcessingTrigger:
    """The trigger a durable finalization job was enqueued with.

    Jobs written before ``processing_trigger`` existed carry only the legacy
    ``force_process`` bit, which only the client finalize route ever set.
    """
    stored = job.get('processing_trigger')
    policy = job.get('delivery_policy')
    if policy is not None or stored == ProcessingTrigger.SILENT_BACKFILL.value:
        if policy != 'silent_backfill_v1' or stored != ProcessingTrigger.SILENT_BACKFILL.value:
            raise ValueError('invalid historical delivery policy')
        return ProcessingTrigger.SILENT_BACKFILL
    if isinstance(stored, str):
        try:
            return ProcessingTrigger(stored)
        except ValueError:
            pass
    return ProcessingTrigger.CLIENT_FINALIZE if job.get('force_process') else ProcessingTrigger.CAPTURE_END
