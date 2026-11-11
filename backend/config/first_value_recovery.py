"""Default-dark authority for the first-value recovery experiment."""

# LIFECYCLE: experiment

import os

from utils.experiments import bucket_of

ENABLED_ENV = 'FIRST_VALUE_RECOVERY_ENABLED'
COHORT_PERCENT_ENV = 'FIRST_VALUE_RECOVERY_COHORT_PERCENT'


def cohort_percent() -> int:
    """Approved intake percentage; zero keeps every serving path dark."""

    try:
        value = int(os.getenv(COHORT_PERCENT_ENV, '0').strip())
    except (TypeError, ValueError):
        return 0
    return value if 0 <= value <= 100 else 0


def recovery_enabled() -> bool:
    """One runtime kill switch, checked before selection and dispatch."""

    return os.getenv(ENABLED_ENV, 'false').strip().casefold() in {'1', 'true', 'yes', 'on'} and cohort_percent() > 0


def intake_admitted(experiment_id: str, paid_start_key: str) -> bool:
    """The approved intake cohort is independent of the permanent 50/50 draw."""

    return bucket_of(f'{experiment_id}:approved-intake', paid_start_key) < cohort_percent() * 100
