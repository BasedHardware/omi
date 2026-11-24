"""Stored candidate filter for the default v3 Home list."""

import os

from google.cloud import firestore

FIELD = 'home_visible'
FLAGS = ('recording', 'home_hidden')


def visible(row):
    return not any(row.get(flag) for flag in FLAGS)


def stamp(patch, current=None):
    """Set the bit on a replacement or on a patch to a transactionally read row."""
    values = (patch.get(flag, (current or {}).get(flag)) for flag in FLAGS)
    patch[FIELD] = not any(value is not firestore.DELETE_FIELD and value for value in values)
    return patch


def enabled(uid):
    # Admit only owners whose entire collection has been reconciled.
    return uid in {
        value.strip() for value in os.getenv('OMI_HOME_VISIBILITY_INDEX_OWNERS', '').split(',') if value.strip()
    }
