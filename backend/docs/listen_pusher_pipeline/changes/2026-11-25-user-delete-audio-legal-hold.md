# Legal-hold gate for user conversation audio deletion

The user conversation delete now acquires one `audio_conversation_deletion` gate
for canonical packs and every audio prefix. The same gate covers the
post-response cleanup and the accepted-delete worker, including deployments
without a canonical bucket. A hold already active at gate acquisition blocks the
whole audio cleanup. A hold placement during cleanup is refused until the gate
releases.

If a hold arrives after the request gate releases, the post-response task
marks the tombstone for hold-release follow-up and records an erasure obligation
with the merge donor IDs. The erasure worker retries after release.

The regressions check the same gate token at every blob mutation and place a
hold between the request and audio gates to verify retention and release follow-up.
The change requires no rollout flag and can be reverted.

[Canonical audio archive contract](../../listen_pusher_pipeline.mdx#forward-canonical-audio-archive-default-off)
