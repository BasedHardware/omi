# Fence finalization-triggered episode composer writes

The [episode lifecycle](../../listen_pusher_pipeline.mdx#episode-lifecycle-and-overdue-quiet-recovery) carries the finalizing conversation into the composer. Its episode updates now check account deletion authority and the conversation tombstone inside the existing Firestore transactions. If either blocks after the lease is claimed, the composer discards the result and leaves the existing lease to expire.

The transaction tests count four extra point reads on a paid compose with one lease claim and one result write. When the marker arrives between those writes, the account deletion race uses three fence reads because the account check can stop before the tombstone read. The tombstone race uses four. Each additional guarded transaction attempt can add up to two reads. The fence adds no writes or provider calls. These counts come from hermetic fixtures.

The change ships with the Python backend. Revert this PR to roll back. SCA-4083 tracks the production rollout and Firestore readback.
