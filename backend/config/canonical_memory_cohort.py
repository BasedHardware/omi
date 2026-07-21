"""Code-owned canonical-memory entitlement selector.

This deliberately dependency-free module is importable from database, utility,
and router layers. It is the one source of truth for canonical memory, task
intelligence, and Chat-first cohort membership.
"""

# This fixed Auth-emulator UID is a local-only E2E account. Its presence here
# deliberately makes the harness use the same membership predicate as every
# real account; the paired disabled fixture UID is intentionally absent.
LOCAL_CHAT_FIRST_E2E_ENABLED_UID = 'omi-local-emulator-chat-first-enabled-v1'

CANONICAL_MEMORY_USERS: frozenset[str] = frozenset(
    {
        "vi7SA9ckQCe4ccobWNxlbdcNdC23",  # david.d.zhang@gmail.com (prod Firebase: based-hardware)
        LOCAL_CHAT_FIRST_E2E_ENABLED_UID,
        # Next dogfood (re-enable soon):
        # "viUv7GtdoHXbK1UBCDlPuTDuPgJ2",  # kodjima33@gmail.com (prod Firebase: based-hardware)
    }
)


def is_canonical_memory_user(uid: object) -> bool:
    """Return whether ``uid`` belongs to the sole canonical entitlement cohort."""

    return bool(uid) and isinstance(uid, str) and uid in CANONICAL_MEMORY_USERS


__all__ = [
    'CANONICAL_MEMORY_USERS',
    'LOCAL_CHAT_FIRST_E2E_ENABLED_UID',
    'is_canonical_memory_user',
]
