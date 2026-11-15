"""UID experiment roster erasure, shared by admission fencing and account wipes.

Delete failures propagate so the existing account-wipe retry remains authoritative.
This module owns no client construction, enrollment or billing decisions.
"""

EXPERIMENT_ID = 'EXP-006-yearly-switch-retention'


def erase_assignment(uid: str, client) -> None:
    client.collection('experiments').document(EXPERIMENT_ID).collection('assignments').document(uid).delete()
