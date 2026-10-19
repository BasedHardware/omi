"""Client summaries are display projections; funded admission owns processing policy.

At cap a summary never completes the deferred work or creates backlog consent.
"""

import os


def client_summaries_at_cap_enabled() -> bool:
    """Default on; exact false disables accepting new client summaries."""
    return os.getenv('CLIENT_SUMMARIES_AT_CAP_ENABLED', 'true') != 'false'
