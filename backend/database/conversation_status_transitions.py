"""Recovery verdict validation at the storage boundary."""


def recovery_discard_payload(write_data: dict) -> bool:
    # Imported lazily: several unit harnesses load this module with a stubbed
    # ``utils`` package that has no ``utils.conversations`` subpackage.
    from utils.conversations.recovery import verified_recovery_discard

    return verified_recovery_discard(write_data.get('discarded'), write_data.get('relevance_decision'))
