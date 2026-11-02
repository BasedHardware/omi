"""User-reprocess result contract (summary/template UX).

Always on for ``POST /v1/conversations/{id}/reprocess``:

- a reprocess that loses the processing claim to another writer answers 409
  ``conversation_processing_in_progress`` instead of a 200 that echoes the
  stale conversation;
- a user reprocess replaces only the selected app's result, keeping other
  apps' results behind it (the fresh result first, because released clients
  display the first non-empty ``apps_results`` entry). An app that fails or
  answers nothing never evicts the results already stored;
- ``source=omi`` asks for Omi's own notes: no preferred or suggested app runs;
- a template-only reprocess (explicit app, transcript unchanged since the
  stored memories/tasks/goals were derived) does not re-derive them, and a
  failed explicit app never rewrites tasks or goal progress.

``CONVERSATION_REPROCESS_RESULT_CONTRACT_ENABLED`` (default off) now gates
only the error code of an explicit app selection that produced no result:
502 ``app_result_failed`` instead of the generic 500. Every released client
treats any non-200 reprocess answer as failure. The value is read at the call
boundary, never snapshotted at import.
"""

import os
from typing import Any, Iterable, Optional

from utils.conversations.transcript_hash import transcript_sha256

RESULT_CONTRACT_FLAG = 'CONVERSATION_REPROCESS_RESULT_CONTRACT_ENABLED'

# ``source`` query value that forces Omi's own summary on reprocess.
FIRST_PARTY_SUMMARY_SOURCE = 'omi'

# Server-only conversation field: transcript digest the stored memories,
# action items and goal progress were last derived from. Absent means
# unknown, so derived effects run.
DERIVED_EFFECTS_TRANSCRIPT_FIELD = 'derived_effects_transcript_sha256'


def reprocess_result_contract_enabled() -> bool:
    return os.getenv('CONVERSATION_REPROCESS_RESULT_CONTRACT_ENABLED', '').strip().casefold() in {
        '1',
        'true',
        'yes',
        'on',
    }


def derived_effects_transcript_digest(segments: Optional[Iterable[Any]]) -> str:
    return transcript_sha256(list(segments or []))
