"""Dark dispatch policy. No environment/deployment changes enable this implicitly."""

import os


def enabled() -> bool:
    return os.getenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false').lower() == 'true'


def execution_admission_enabled() -> bool:
    """Live and queued work enforce ladder budgets even when legacy dispatch is dark."""
    return enabled() or os.getenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'false') == 'true'
