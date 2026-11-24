# Home read settling and rollback

Home holds completed, uncurated below-floor rows permanently; only provisional
minimum/batch-short holds expire after two hours. Pending, processing and
in-progress rows remain visible. Search and direct access keep the recording.

The episode list closes at most two idle episodes per read and queues each
composer in that same call. Successful close returns its committed state; a lost
CAS performs one exact read. Five exact episode documents per request bound
client-acknowledged member validation; members beyond the cap remain visible.
There is no transcript-hydration read for legacy titles.

`HOME_HIDE_EPISODE_MEMBERS=off` restores source rows, version checks and caching.
`HOME_HIDE_BELOW_FLOOR_ROWS=off` releases floor/minimum Home holds.
`HOME_NEUTRAL_MINIMUM_TITLES=off` restores stored titles. All default on.
Dead-letter terminal titles remain useful and are never neutralized.
`EPISODE_OUTPUT_LANGUAGE_PIN=off` restores preference-then-capture resolution for
both notes and episodes; omitted transcripts always keep valid capture fallback.

Contracts: [terminal title authority](../../listen_pusher_pipeline.mdx)
and [episode reads](../../../utils/episodes/ARCHITECTURE.md). Backend deployment
belongs to the rollout lead. App startup/placeholder rendering and batch attachment
at audio close are separate PRs. All evidence uses hermetic fixtures.
