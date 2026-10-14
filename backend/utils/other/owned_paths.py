"""Contain temporary I/O within application scratch or the owned local harness."""

import os
import tempfile


def owned_scratch_path(value: str, *, include_harness: bool = False) -> str:
    candidate = os.path.realpath(value)
    roots = [
        os.path.realpath('_temp'),
        os.path.realpath('syncing'),
        os.path.realpath(tempfile.gettempdir()),
    ]
    if include_harness:
        configured = os.environ.get('OMI_HARNESS_STATE_ROOT')
        if configured:
            roots.append(os.path.realpath(configured))
    for root in roots:
        if candidate != root and os.path.commonpath([root, candidate]) == root:
            return candidate
    raise ValueError('Path is outside owned scratch storage')
