# Recording-derived conversations v3

The [v3 contract](../../listen_pusher_pipeline.mdx#recording-derived-conversations-v3)
keeps recording IDs on capture, socket events and finalization while deriving
user-visible conversations from recorded-clock transcript windows. Recording
processing exits before model or derived work; source markers keep draining
through an admission rollback. Stage defaults to beta; no runtime flag was
changed by this implementation. Release acceptance and complete test evidence
belong to the local PR body and must be reviewed before rollout.
