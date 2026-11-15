# Compact Home projections

Home now has a compact display projection on each existing conversation and episode. Full conversation creation and episode sealing stamp separately encrypted display fields. Canonical source mutations atomically invalidate coverage and append content-free dirty ownership receipts through the existing Firestore Commit fence. Explicit authenticated preparation reconciles these receipts; passive list reads neither compose episodes nor hydrate members.

Live segment appends avoid repeated invalidation only when existing segment content, attribution and recorded start are unchanged. Content edits, membership changes, discard, deletion and access changes invalidate affected coverage. Account erasure suppresses derived receipts so deleted user subtrees cannot be recreated.

Upload-custody session registration, renewal and release do not change Home display or ownership. Updates limited to `record_upload_sessions` and existing playback/progress fields preserve prepared cards without extra Home writes; any combined content or access edit still invalidates coverage. Lifecycle emulator assertions compare the complete committed source before and after housekeeping, including its Home version token.

The API and readiness protocol are defined in [Home feed](../../home-feed.md). `HOME_FEED_ENABLED` defaults on and controls serving only; writer metadata remains maintained while it is off. Initial deployment must hold serving off through mixed writer versions, install the declared indexes and verify all canonical writers have the new fence before enabling. Standing operator processes and separate desktop/batch/job release lineages require explicit inclusion proof.

Hermetic coverage is in `tests/unit/test_home_feed*.py`, the SDK transport coverage in `tests/unit/test_bpp_generation_fence.py`, and emulator acceptance in `tests/integration/test_home_feed_emulator.py`. These checks establish source behavior, not production activation or measured production savings.
