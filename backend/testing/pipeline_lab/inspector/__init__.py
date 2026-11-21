"""Pipeline-lab inspector: a stdlib HTTP server and a static UI over the run store.

Read-only except for verdict writes. ``sample_run`` writes a synthetic store for tests and UI work.
Nothing here constructs clients or touches the filesystem at import time.
"""
