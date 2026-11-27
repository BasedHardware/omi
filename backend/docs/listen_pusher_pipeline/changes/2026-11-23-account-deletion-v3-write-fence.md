# Keep v3 deletion gates aligned with marker writes

SCA-3166 fixes six existing transactional paths to read `wipe_status`, the field written by the account-deletion marker. The paths are transcript projection, summary commit, backfill prior creation, live re-derive undo, terminal pending cleanup, and live title preview. Restored (`cancelled`) and billing-failed accounts can resume these writes. The shared deletion policy still blocks pending deletion and fails closed for unusable markers.

Rollout and flag state: the corrected checks are active by default when this code serves. No new production read or write path and no new flag are introduced. Roll back by reverting the marker-field changes.

The transaction regression tests exercise `cancelled`, `billing_failed`, and `pending`, including both claiming and publishing live title previews. The Firestore query-shape tests verify the refreshed `commit_projection` body digest.

After rollout, perform a read-only log check for v3 `account_deletion` conflicts where the marker was cancelled at write time. Record the observation window, observed write volume, and conflict count without account identifiers. Report the result as inconclusive if marker state cannot be attributed to writes or no writes occurred.
