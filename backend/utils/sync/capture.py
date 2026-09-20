"""Decoded capture coverage survives VAD cropping; no wire metadata is trusted."""

from uuid import NAMESPACE_URL, uuid5
import json


class CaptureSegments(set):
    def __init__(self):
        super().__init__()
        self.windows = {}
        self.silent = set()

    def add_capture(self, path, start, end, *, silent=False):
        self.add(path)
        self.windows[path] = (start, end)
        if silent:
            self.silent.add(path)


def chunk_identity(uid, source, device, locked, timestamp):
    # The same timestamp/provenance is the same input anchor across job retries.
    return str(uuid5(NAMESPACE_URL, json.dumps([uid, source, device, bool(locked), float(timestamp)])))
