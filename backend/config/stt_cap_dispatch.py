"""Dark dispatch policy. No environment/deployment changes enable this implicitly."""

import os


def enabled() -> bool:
    return os.getenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false').lower() == 'true'
