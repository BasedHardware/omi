"""Which screen-frame docs belong to this environment.

Dev and prod backends share one Firestore but store frame bytes in different
buckets (`based-hardware-dev-screen-frames`, `based-hardware-prod-screen-frames`).
A frame doc is usable only by the environment whose bucket holds its bytes:
signing a dev-written frame against the prod bucket yields a broken image, and
letting a foreign frame into the cap would evict or demote this environment's
own frames. Every read, sign, cap, and notes-evidence path filters through
`own_frames` first. The helpers live beside the Firestore CRUD so callers that
cannot import this package still share one definition.
"""

from database.screen_frames import LEGACY_SCREEN_FRAMES_BUCKET, frame_storage_bucket, own_frames

__all__ = ['LEGACY_SCREEN_FRAMES_BUCKET', 'frame_storage_bucket', 'own_frames']
