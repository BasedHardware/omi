# Backfill re-derive preserves linked windows

A historical backfill re-derive can propose a replacement window on a recording
still claimed by an unplanned prior window. If task or memory links prevent removal
of that prior window, the transaction blocks with `backfill_rederive_linked_claims`
and preserves the previous projection and claims. Replacement and removal must fit
in one transaction when they share a recording, so an oversized partition blocks
before any batch commits.

This applies to historical backfill re-derive on rollout. The live builder and
live re-derive use the existing merge and retirement paths.

See the [pipeline overview](../../listen_pusher_pipeline.mdx) and SCA-4084.
