"""Recording-derived conversations; independent of the episode engine."""


class Conflict(RuntimeError):
    """Retryable v3 ownership and source-revision conflicts."""
