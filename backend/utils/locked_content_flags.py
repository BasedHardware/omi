"""Dark reset recovery switch; operators enable it explicitly after review."""

import os


def reset_recovery_enabled() -> bool:
    return os.getenv('LOCKED_CONTENT_RESET_RECOVERY_ENABLED', 'false').lower() == 'true'
