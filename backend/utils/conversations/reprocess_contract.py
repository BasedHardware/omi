"""User-reprocess result contract (summary/template UX). Absent flag keeps legacy behavior.

``CONVERSATION_REPROCESS_RESULT_CONTRACT_ENABLED`` (default off) gates the
wire-visible half of the reprocess contract:

- a reprocess that loses the processing claim to another writer answers 409
  instead of a 200 that echoes the stale conversation;
- a user reprocess replaces only the selected app's result, keeping other
  apps' results behind it (the fresh result first, because released clients
  display the first non-empty ``apps_results`` entry);
- an explicit app selection that produced no result answers 502
  ``app_result_failed`` instead of the generic 500.

Every released client already treats any non-200 reprocess answer as failure,
so the gate is rollout hygiene, not a compatibility shim. The value is read at
the call boundary, never snapshotted at import.
"""

import os

RESULT_CONTRACT_FLAG = 'CONVERSATION_REPROCESS_RESULT_CONTRACT_ENABLED'


def reprocess_result_contract_enabled() -> bool:
    return os.getenv('CONVERSATION_REPROCESS_RESULT_CONTRACT_ENABLED', '').strip().casefold() in {
        '1',
        'true',
        'yes',
        'on',
    }
