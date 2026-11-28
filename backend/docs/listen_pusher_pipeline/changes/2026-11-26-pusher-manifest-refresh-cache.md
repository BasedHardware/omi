# Pusher custody manifest reuse across playback refreshes

SCA-3882 adds a Pusher rollout flag to keep verified encoded manifest bodies
for 15 minutes within the existing 8 MiB process budget. The default lifetime
is two minutes. A typical five-minute inventory refresh still lists current
media and requires a unique manifest. Each warm read checks live generation
and metageneration and repeats decryption, digest, frame, media binding and gap
validation. Cache admission requires the same custody checks.

Release owns the flag after full custody review. The [rollout and readback
runbook](../../runbooks/private-sync-inventory-manifest-reuse.md) describes the
comparison and the settled billing proof. The [retained seal proof
rules](../../listen_pusher_pipeline.mdx#retained-seal-proof-rules) and the
[Pusher cache contract](../../listen_pusher_pipeline.mdx#pusher-playback-inventory-manifest-reuse)
apply.
