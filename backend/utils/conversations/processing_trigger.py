"""Why a conversation is being processed, and everything that follows from it.

Callers of ``process_conversation`` name a ``ProcessingTrigger`` and nothing
else about mode. Each trigger's row in ``PROCESSING_MODES`` fixes whether
enrichment runs now, whether it is a reprocess, whether JIT first-open may
defer derived work, and whether relevance is assessed. Independent booleans
at call sites let "run now" silently imply "skip discard" on four
first-processing paths; one row per reason makes every combination a
reviewed decision.

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
    USER_REPROCESS = 'user_reprocess'  # the user asked to reprocess it
    MERGE = 'merge'  # the user merged conversations into it
    SERVER_RECOVERY = 'server_recovery'


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
    # Run derived work eagerly even when JIT first-open would defer it.
    bypass_jit_first_open: bool
    # KEEP for triggers that are themselves a user action on this row, plus
    # SERVER_RECOVERY: the repair run must never discard the recovered copy.
    relevance: RelevancePolicy


_ASSESS, _KEEP = RelevancePolicy.ASSESS, RelevancePolicy.KEEP

PROCESSING_MODES: Mapping[ProcessingTrigger, ProcessingMode] = MappingProxyType(
    {
        ProcessingTrigger.CAPTURE_END: ProcessingMode(False, False, False, _ASSESS),
        # Ending a capture is not a judgment about its content; a discard here
        # stays one tap from restore.
        ProcessingTrigger.CLIENT_FINALIZE: ProcessingMode(True, False, False, _ASSESS),
        # Reassessed over the whole merged transcript on every append, so a
        # fragment that later gains real speech is promoted automatically.
        ProcessingTrigger.SYNC_UPDATE: ProcessingMode(True, True, True, _ASSESS),
        ProcessingTrigger.FIRST_OPEN: ProcessingMode(True, False, False, _KEEP),
        ProcessingTrigger.USER_REPROCESS: ProcessingMode(True, True, True, _KEEP),
        ProcessingTrigger.MERGE: ProcessingMode(True, False, False, _KEEP),
        ProcessingTrigger.SERVER_RECOVERY: ProcessingMode(True, True, True, _KEEP),
    }
)


def trigger_for_finalization_job(job: Mapping[str, object]) -> ProcessingTrigger:
    """The trigger a durable finalization job was enqueued with.

    Jobs written before ``processing_trigger`` existed carry only the legacy
    ``force_process`` bit, which only the client finalize route ever set.
    """
    stored = job.get('processing_trigger')
    if isinstance(stored, str):
        try:
            return ProcessingTrigger(stored)
        except ValueError:
            pass
    return ProcessingTrigger.CLIENT_FINALIZE if job.get('force_process') else ProcessingTrigger.CAPTURE_END
