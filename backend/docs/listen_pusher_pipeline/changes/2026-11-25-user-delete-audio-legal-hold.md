# Legal-hold gate for user conversation audio deletion

The user conversation delete now acquires one `audio_conversation_deletion` gate
for canonical packs and every audio prefix. The same gate covers the
post-response cleanup and the accepted-delete worker, including deployments
without a canonical bucket. A hold already active at gate acquisition blocks the
whole audio cleanup. A hold placement during cleanup is refused until the gate
releases.

The regression test runs both delete paths and attempts to place a hold before
the first prefix delete. It checks the same gate token at every blob mutation.
The change requires no rollout flag and can be reverted.

[Canonical audio archive contract](../../listen_pusher_pipeline.mdx#forward-canonical-audio-archive-default-off)
