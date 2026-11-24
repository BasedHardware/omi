# Revert the expanded conversation deletion scope

One sync upload can feed several conversations. #26215 looked up the upload in the owner's sync ledger and erased the entire staging prefix when any linked conversation was deleted. That could erase raw audio still needed by a live sibling. The same change added audio erasure to the default `cascade=false` path, where failures in the post-response audio cleanup did not have a durable audio retry.

The [exact revert](https://github.com/BasedHardware/omi/pull/26219) restores pre-#26215 behavior. Conversation deletion records its tombstone before cleanup. The default `cascade=false` path removes the conversation without scheduling the cascade audio purge. Explicit `cascade=true` uses the existing conversation audio cleanup. The revert removes the added ledger-driven staging-prefix erase and the added ledger-only batch segment matching. The [conversation deletion owner scan](../../listen_pusher_pipeline.mdx#conversation-deletion-owner-scan-switch) continues to use its existing conversation associations. The route's legal-hold deferral predates #26215.

## Release evidence

- Original change on main: `3e1a54b0b924fcd460db162507ee4c9429a34162` ([#26215](https://github.com/BasedHardware/omi/pull/26215)).
- Revert: [#26219](https://github.com/BasedHardware/omi/pull/26219) is open. The reviewed revert head `7d1df650d55dc5a51e1a2a635dd3b54ca725fd80` matched the inverse of #26215 against its first parent and preserved #26207. Release will record the merged SHA after verifying the refreshed inverse and green exact-head CI.
- Serving: Release recorded Backend serving `backend-69ba4fa-45359837893-1` at 10:48:35 UTC on November 24. This is the rollback target. Revert serving evidence is pending the exact-SHA Backend GO and production readback. [Release desk](https://multica.ai/issues/SCA-1819)

The planned reland requires a full custody review. Shared staging must survive while any linked conversation is live, and default-delete audio cleanup must retry storage holds and ledger-read failures durably, including after the primary conversation row is gone.
