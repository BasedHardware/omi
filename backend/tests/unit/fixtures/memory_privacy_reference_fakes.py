"""Resolve the SDK's atomic token union in memory-history writer tests."""

from google.cloud.firestore_v1.transforms import ArrayUnion


def apply_reference_patch(stored, patch):
    for key, value in patch.items():
        if isinstance(value, ArrayUnion):
            stored[key] = list(dict.fromkeys([*stored.get(key, []), *value.values]))
        else:
            stored[key] = value
