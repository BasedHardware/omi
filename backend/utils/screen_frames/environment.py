"""Which screen-frame docs belong to this environment.

Frame bytes live in the bucket of the customer data plane that holds the frame
doc: every host serving production Firestore, the dev backends included, uses
`based-hardware-prod-screen-frames`. Docs written before that rule may still
point at `based-hardware-dev-screen-frames` (stamped, or unstamped legacy docs)
until scripts/migrate_screen_frames_to_data_plane_bucket.py moves them.
A frame doc is usable only by a host whose bucket holds its bytes:
signing a dev-written frame against the prod bucket yields a broken image, and
letting a foreign frame into the cap would evict or demote this environment's
own frames. Every read, sign, cap, and notes-evidence path filters through
`own_frames` first. The helpers live beside the Firestore CRUD so callers that
cannot import this package still share one definition.
"""

from database.screen_frames import LEGACY_SCREEN_FRAMES_BUCKET, frame_storage_bucket, own_frames

__all__ = ['LEGACY_SCREEN_FRAMES_BUCKET', 'frame_storage_bucket', 'own_frames']
