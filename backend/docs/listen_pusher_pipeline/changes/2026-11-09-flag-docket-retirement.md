# Retire dormant pipeline flag paths

David's 2026-11-09 docket removes unused batch shortcuts, single-language hint
variants, optional canonical packing, paid legacy empty recovery and revision
reuse. The serving paths retain the production values recorded at 03:20Z.
Parakeet retains its first-text and progress expiry behavior. STT cap dispatch
keeps its independent enforcement switch; ladder-only enforcement is removed.
The free strict-VAD silence guard and post-persist dedupe seam remain.
Canonical archive privacy deletion, existing pack verification and merge rewrites
remain available for previously stored bytes; forward writers and the pack job
are removed. No client wire format changes.

Audio archive and mobile Standard batch admission retain injected Firestore
cohorts, without UID environment fallbacks. Before deployment, confirm each
cohort has its existing production member. First-summary admission retains its
percent/deadline gates and loses the redundant UID exception. The feature flag
registry records the retired keys. Calls/recap and action-items-v2 selectors
remain available for the November 16 readout.

See [the pipeline contract](../../listen_pusher_pipeline.mdx) and
[the generated flag registry](../../feature-flag-registry.md).
