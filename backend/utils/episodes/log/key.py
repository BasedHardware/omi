"""Batch-1 attach gate digest is the batch-2 input fact key, byte for byte."""

from utils.conversations.episode_attach_key import content_key
from utils.episodes.log.codec import digest


def gate_digest(row):
    return content_key(row)


def uncertain_key(cid, row):
    # Missing recorded/transcript proof must never suppress a member-state update.
    # This explicit uncertainty envelope is outside batch 1's memo-eligible domain.
    return digest({'uncertain_member': cid, 'row': row})
