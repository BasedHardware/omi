"""Neutral object-storage port (ADR-0007/0032): GCS | S3-compatible behind one contract."""

from utils.object_store.errors import ObjectNotFound, ObjectStoreError
from utils.object_store.factory import get_object_store, reset_object_store_for_tests
from utils.object_store.ports import ObjectInfo, ObjectStore

__all__ = [
    "ObjectInfo",
    "ObjectStore",
    "ObjectNotFound",
    "ObjectStoreError",
    "get_object_store",
    "reset_object_store_for_tests",
]
