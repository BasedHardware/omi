"""Model-free process fencing shared by the worker and lease coordinator."""


class FatalGpuError(RuntimeError):
    """GPU process must restart; never turn this flight into a segment failure."""
