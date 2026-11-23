# Keep v3 deletion gates aligned with marker writes

SCA-3166 fixes four existing transactional paths to read `wipe_status`, the field written by the account-deletion marker: transcript projection, summary commit, backfill prior creation, and live re-derive undo. Restored (`cancelled`) and billing-failed accounts can resume these writes; pending deletion remains blocked. This corrects the readers without changing deletion policy.

Rollout and flag state: the corrected checks are active by default when this code serves. No new production read or write path and no new flag are introduced. Roll back by reverting the marker-field changes.

Verification: `bash backend/test.sh backend/tests/unit/test_conversations_v3_transactions.py backend/tests/unit/test_conversations_v3_live_rederive.py` passed (124 tests); `bash backend/test.sh backend/tests/unit/test_firestore_query_shapes.py` passed (629 tests, 1 deselected), including the refreshed body digest for the corrected `commit_projection` marker field. After rollout, perform a read-only log check for v3 `account_deletion` conflicts where the marker was cancelled at write time. Record the observation window, observed write volume, and conflict count without account identifiers; report the result as inconclusive if marker state cannot be attributed to writes or no writes occurred.
