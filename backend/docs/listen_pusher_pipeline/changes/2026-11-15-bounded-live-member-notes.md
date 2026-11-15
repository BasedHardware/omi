# Bounded live-member notes

The [ownership contract](../../listen_pusher_pipeline.mdx#home-processing-ownership-default-on)
releases idle owners through Home's activity-fenced transaction. Non-batch pendant
members gain one extra note attempt after 180 seconds of finalization-job age.
`HOME_LIVE_MEMBER_NOTES_BOUNDED_ENABLED` defaults on; off restores the original gate.
The revision permit is consumed before notes generation; retries cannot purchase
it twice. Completion, a newer revision, owner closure or explicit detail/reprocess
exits that budget. Crashes can leave the extra attempt uncertain. No startup scan,
historical recompose or change to the preceding 30-minute grouping window occurs.
