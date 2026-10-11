"""Deploy admission for the AFM-only, explicit-account development rollout.

The runtime cohort parser also supports percentages. Stage 1 deliberately
admits only its UID-token subset; no account values belong in source control.
Shared by Cloud Run and ConfigMap rendering so malformed input fails before
either deploy path applies configuration (the #14316 deploy-boundary contract).
"""

LOCAL_PROCESSING = 'FREE_TIER_LOCAL_PROCESSING'
LOCAL_PROCESSING_COHORT = 'FREE_TIER_LOCAL_PROCESSING_COHORT'
EMERGENCY_STOP = 'FREE_TIER_EMERGENCY_STOP'
FREE_TIER_DEPLOY_KEYS = (LOCAL_PROCESSING, LOCAL_PROCESSING_COHORT, EMERGENCY_STOP)


def validate_free_tier_deploy_value(name: str, value: str) -> None:
    """Reject unsafe spellings without including account identifiers in errors."""
    if name in (LOCAL_PROCESSING, EMERGENCY_STOP):
        if value not in {'true', 'false'}:
            raise ValueError(f"{name} must be exactly 'true' or 'false'")
    elif name == LOCAL_PROCESSING_COHORT:
        # Both deploy transports are line-oriented. The runtime trims tokens,
        # lowercases their kind, and permits colons within a non-empty UID.
        if any(character in value for character in ('\n', '\r', '\u2028', '\u2029', '\0')):
            raise ValueError(f'{name} must be a single-line explicit UID cohort')
        if not value.strip():
            return
        for token in value.strip().split(','):
            kind, separator, uid = token.strip().partition(':')
            if not separator or kind.strip().lower() != 'uid' or not uid.strip():
                raise ValueError(f'{name} must be empty or comma-separated uid:<non-empty> tokens; no percentages')
