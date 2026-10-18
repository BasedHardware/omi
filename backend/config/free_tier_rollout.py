"""Deploy validation for the surviving memory-suppression emergency stop."""

EMERGENCY_STOP = 'FREE_TIER_EMERGENCY_STOP'
FREE_TIER_DEPLOY_KEYS = (EMERGENCY_STOP,)


def validate_free_tier_deploy_value(name: str, value: str) -> None:
    if name == EMERGENCY_STOP and value not in {'true', 'false'}:
        raise ValueError(f"{name} must be exactly 'true' or 'false'")
