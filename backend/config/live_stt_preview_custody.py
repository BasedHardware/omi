"""Emergency rollback for promoting leaked local-preview audio to durable batch."""

import os


def preview_batch_custody_enabled() -> bool:
    return os.getenv('LISTEN_PREVIEW_BATCH_CUSTODY_ENABLED', 'true').strip().lower() not in {'false', '0', 'off', 'no'}
