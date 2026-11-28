"""The Firestore ownership fence shared by Python finalization and workerd.

Only rows marked pending in their creation transaction may enter Go
admission. A legacy or explicit Python decision is permanent. Handback
advances the epoch and pins Python. Go job documents retain their Go tag,
even after retirement, so delayed Python tasks cannot claim them.

Readers use this check on snapshots they already hold. It depends on
durable state, never on a process's rollout configuration.
"""

from collections.abc import Mapping
from typing import Any

ENGINE_FIELD = 'finalization_engine'
EPOCH_FIELD = 'finalization_owner_epoch'
CUSTODY_FIELD = 'go_finalization_custody'
REFUSAL = 'finalization_owned_elsewhere'


def python_owns_finalization(row: Mapping[str, Any]) -> bool:
    if ENGINE_FIELD not in row:
        return EPOCH_FIELD not in row
    epoch = row.get(EPOCH_FIELD)
    return row[ENGINE_FIELD] == 'python' and type(epoch) is int and epoch > 0


class FinalizationOwnedElsewhere(RuntimeError):
    """A Python processor attempted to enter a non-Python finalization."""
