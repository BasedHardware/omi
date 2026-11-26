# Revert the expanded conversation deletion scope

One sync upload can feed several conversations. #26215 looked up the upload in the owner's sync ledger and erased the entire staging prefix when any linked conversation was deleted. That could erase raw audio still needed by a live sibling. The same change added audio erasure to the default `cascade=false` path, where failures in the post-response audio cleanup did not have a durable audio retry.

The [exact revert](https://github.com/BasedHardware/omi/pull/26219) restores pre-#26215 behavior. Conversation deletion records its tombstone before cleanup. The default `cascade=false` path removes the conversation without scheduling the cascade audio purge. Explicit `cascade=true` uses the existing conversation audio cleanup. The revert removes the added ledger-driven staging-prefix erase and the added ledger-only batch segment matching. The [conversation deletion owner scan](../../listen_pusher_pipeline.mdx#conversation-deletion-owner-scan-switch) continues to use its existing conversation associations. The route's legal-hold deferral predates #26215.

## Release evidence

- Original change on main: `3e1a54b0b924fcd460db162507ee4c9429a34162` ([#26215](https://github.com/BasedHardware/omi/pull/26215)).
- Revert: [#26219](https://github.com/BasedHardware/omi/pull/26219) merged at `755471d81eee89d8f09bd4ad707e59fb3db279b3` on November 25 at 04:50:39 UTC from Shipping-approved head `9bad8642893949b29a285d95a8467616bd41bf1c`. Release verified the inverse across all 14 files and confirmed the merge contains correction #26222. [Release Eligibility](https://github.com/BasedHardware/omi/actions/runs/45549525193) and [Backend Unit Tests](https://github.com/BasedHardware/omi/actions/runs/45549525283) passed on the merge SHA.
- Serving: Release last reported Backend source `0130d91` at 100% on `backend-unset-2b39df9daba374be` (generation 3372) in the November 25 04:41:03 UTC readback, before the revert merged. Production serving evidence for the revert is pending per-service admission and readback. [Release desk](https://multica.ai/issues/SCA-1819)

Any future reland requires a full custody review. Shared staging must survive while any linked conversation is live, and default-delete audio cleanup must retry storage holds and ledger-read failures durably, including after the primary conversation row is gone.
