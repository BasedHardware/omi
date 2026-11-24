"""Default-on source equivalence kill switch; accepted aliases keep their fences."""

import os


def enabled() -> bool:
    return os.getenv('BATCH_SOURCE_REUSE_ENABLED', 'true').strip().lower() in {'true', '1', 'on', 'yes'}
