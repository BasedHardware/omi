"""Load the smart-merge worker only for an owed survivor refresh.

Decode/admission also import the enrichment callback. Those lightweight paths
must not acquire the donor cleanup, task integration and storage dependencies.
"""

import importlib


def settle_survivor(uid: str, conversation_id: str, *, owner: str, skip_processing: bool = False) -> None:
    worker = importlib.import_module('utils.conversations.smart_merge')
    worker.refresh_survivor(uid, conversation_id, owner=owner, settled=True, skip_processing=skip_processing)
