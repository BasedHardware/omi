# WQ26 / 1027c — batch privacy writer fence and attempt memo

Branch: `lane/firestore-reads-wq26-bpp-fence`; starting base `cd784901266`.
WQ21 report was read first. The inherited 1027b edits and previously untracked
candidate files were treated as drafts and independently exercised.

## Disposition

Implemented a **default-off, locally verified candidate**. No PR, push, deploy,
production measurement, or runtime configuration change. GCP tier: **none**.
Only `bpp_generation_memo` was added to backend `KNOWN_LEVERS`; absence remains
0/off. No changes under `backend/deploy/**`, `backend/charts/**`,
`config/feature-flags.yaml`, or `.github/**`.

There is no known unfenced writer from the WQ21 enumeration in this checkout.
This is **not** certification of deployed writer convergence. Keep the reader
lever off until the integrator verifies every deployed writer/maintenance
producer uses the fence. Production savings delivered by this lane: **zero**
(not deployed or enabled).

Implementation commit: 5104edb2f6d (local only).

## Token and atomicity

`batch_pipeline_privacy/{sha256(uid)}` holds `memo_token` (random UUID hex) and
`memo_schema=1`. The usable cache version also includes the snapshot's server
`update_time`, including nanoseconds. It is entirely separate from admission/
erasure `generation`; normal fencing never advances that epoch or changes
`blocked` / `purging`.

`database.batch_privacy_write_fence` wraps synchronous and asynchronous GAPIC
`Commit`. It appends one masked token write per affected owner and database to
the **same Commit request**, retaining source order, masks, preconditions and
transaction ID. It removes only its appended WriteResults from the response,
preserving source CAS update times and delete commit times. No writer reads are
added, so transaction read-before-write ordering is unchanged. Existing memory
change-head and list-projection hooks compose with it.

The field classifier covers user protection/migration/consent; conversation
privacy, ownership and redirects; all creation/replacement/deletion operations;
tombstone existence; all account-marker and privacy-document writes. A masked
metadata-only update with `exists=True` can be excluded because it cannot change
existence. Full-row snapshot consumers are deliberately not certified by this
field set. Legal hold/gate writes rotate the token conservatively, without
adding legal holds to batch admission policy.

Non-atomic `BatchWrite` authority operations become individual atomic source +
token Commits. Result/status positions and partial failures are preserved;
unrelated operations retain BatchWrite. Labeled authority BatchWrite is rejected
**before any write**, since Commit cannot preserve its labels. No current
production authority caller using labeled BatchWrite was found. Unrelated
labeled batches pass through unchanged. Atomic Commit requests are never split
or silently stripped of fences; server limits/errors propagate. The draft's
incorrect 500-write cap was removed: existing list projection expands Commit
requests past 500, and the existing server emulator proof still passes.

A second draft defect was random-token replay: GAPIC Retry can resend the exact
prepared token after another writer. An emulator regression replays that exact
wire request after a consent denial. Its UUID returns to the old value, but the
server revision changes and the cached allow is rejected. UUID alone is not the
cache key.

## Writer ownership and atomic proof

Proofs below are in
`backend/tests/integration/test_bpp_generation_fence_emulator.py` and
`backend/tests/unit/test_bpp_generation_fence.py`. The emulator captures requests
**below all Commit hooks** and checks source and token in each wire request.
All ordinary writer cases preserve generation 7; only the original explicit
epoch advance changes 7 to 8.

| Writer / family | Atomicity proof |
|---|---|
| `speaker_auto_enroll.update_privacy` | Existing consent transaction + appended token; `consent` warms allow, changes token, then denies `recording_privacy_changed`, generation 7→7. |
| `speaker_auto_enroll.retract_conversation` | Existing retraction transaction + token; `retraction` denies `conversation_deleted` even without learned people, generation 7→7. |
| `conversation_tombstones.record_deletion` | SDK create becomes one source + token Commit; `tombstone` injects cleanup failure after durable intent, then denies, generation 7→7. |
| `users.set_data_protection_level` / `set_migration_status` | Their initial user merges carry the token atomically, before purge; tests fail the subsequent purge and still obtain fresh protection denial. |
| `users.finalize_migration` | User update / field deletion + token in one Commit; `migration_complete` denies after changing to E2EE. |
| `users` account marker creation and all status transitions; `account_deletion_transitions` | Every operation on `account_deletions/{uid}` qualifies regardless of payload/status. Real feedback creation, `mark_wipe_completed`, and `record_late_agent_vm_cleanup` are exercised; all SDK operation/mask shapes are covered. Cancellation, billing failure, claim/retry/running/failed transitions use this same root authority path. Process-local `deletion_marker_cache` is not the fence. |
| `upsert_conversation_with_lifecycle`, `persist_processing_result_with_lifecycle`, `create_conversation_if_absent_with_lifecycle` | Real persistence bodies, including direct create and deferred transactional create; dynamic privacy payload + token in one Commit, followed by fresh denial. Outer encryption/cache/notification decorators are bypassed in these emulator cases; persistence/lifecycle/backlog transactions and SDK encoding remain real. |
| `conversations.update_conversation` | Real prepared generic patch persists `uses_custom_stt=True` with token; fresh denial. |
| `conversations.claim_record_lane_owner` | Source update-time precondition preserved; actual returned CAS metadata equals source revision. `failed_cas` proves source and token both roll back on false precondition. |
| `batch_pipeline_intake.admit` → store `flush` ownership patch | Actual `FirestoreStore.run` / buffered ownership flush carries source + token; `admission_ownership` then denies. |
| Sync assignment engine | Actual `assign_in_transaction` creates a dynamically encoded canonical; separate bridge proof updates canonical and donor in one captured Commit containing token. Record-span, canonical, donor and ancestor writes all target the classified conversation path. |
| Smart merge engine | Actual `absorb_conversation` writes survivor, donor and inherited ancestor + token atomically; fresh redirect denial. Planning/optional audit/codec seams are isolated; the persistence engine and ancestor loop run. |
| `conversations.delete_conversation` / SDK hard delete | Its retraction is covered independently; direct SDK hard-delete surface used for final removal is exercised against a redirect target and denies `conversation_redirect_missing`. Both sync/async delete response metadata are tested. |
| `recording_sessions.tombstone_and_delete_empty_conversation` | Actual empty-parent transactional delete + token; redirect target then denies. |
| `purge_batch_owner`, `user_data_deletion.purge_user_subtree` | Real epoch advance, both namespace scans, finish and recursive user erasure run. Token remains outside the erased tree, generation becomes 8, blocking remains set, and fresh authorization denies the missing account. |
| `advance_privacy_generation` / `finish_privacy_purge` | Original epoch and purge semantics retained. Their privacy-document writes rotate token atomically; stale purge-generation completion remains the existing no-op. |
| `legal_holds.place_legal_hold`, destructive gate writes | Existing transactions + token; active hold still blocks destructive deletion, while batch authorization keeps its existing policy. Existing legal-hold suite passes. |
| Staging replay / enhanced-protection migration | Processes importing backend database owners / `_client` share the class-level hook. This does not certify the standalone `scripts/staging/replay.py` path or external/old-revision writers; staging replay requires explicit discipline before reader enablement. |
| `scripts/backfill_user_signup_platform.py` | Additional audit found its standalone Admin SDK merge could create a user without importing `_client`. It now installs the fence before client construction. Real script enumeration/write, SDK Commit and token rotation are emulator-tested. |

No direct GAPIC CreateDocument/UpdateDocument/DeleteDocument/Write-stream or raw
REST authority producer was found in these current backend sources. Those APIs,
other languages and external IAM writers are **not** covered by this Python
Commit hook. Any such producer found during fleet inventory is an enablement
blocker and must be migrated atomically, not papered over with a cache TTL.

## Memo semantics and actual read proof

`PrivacyAttempt` is a bounded ContextVar scope owned by one sync task attempt or
one `Pump._flight`; executor dispatch propagates it. Retries/new calls create a
fresh scope; explicit reset is available. Closing disables captured late executor
contexts. Entries retain client identity (plane), owner and exact source set.
Each authorization transaction physically reads the token document and its
server revision, including SDK retry callbacks. New sources cannot inherit an
existing source's decision; redirect invalidation follows the owner token.

Failed/partial walks are never stored. Failed token reads invalidate a warm
entry and propagate; they never authorize. Missing/malformed/blocked tokens,
missing/malformed revision, mismatches, and expected-generation changes take the
live checks. Full-row `snapshots=` exports remain live. Artifact calls that return
only `ProtectionContext` can reuse authorization, but still read the protection
level live inside that transaction. With the lever off, both the guard and actual
artifact path retain their exact original document-read order/count and outputs.

Hermetic evidence: `backend/tests/unit/test_bpp_generation_memo.py` and
`.agent-brief/WQ26-read-proof.json`. One explicitly owned attempt, same owner /
source, twenty separate transactions:

| Actual path | Off → on document gets | Interpretation |
|---|---:|---|
| `FirestoreStore.run` privacy checks | 100 → 24 | 5 cold + 19×1 token validation; 76% fewer reads. |
| Production `batch_artifact_authorize`, no row export | 100 → 44 | 6 cold + 19×2; token plus live protection-level read on hits; 56% fewer. |
| Production `batch_artifact_authorize`, full row export | 100 → 100 | Exported metadata changes are returned live; zero savings claimed. |
| Production sync completed-status reconciliation, explicitly scoped harness | 120 → 44 | Includes twenty unchanged ledger reads; serialized outputs identical. This does not claim twenty HTTP polling requests share a production task scope. |

The sync-status path is supplementary; the artifact callback is the production
path used by sync/batch artifact IO. The read-count fixture models ordering and
SDK read metadata; it does not model server concurrency. Separate emulator cases
cover actual atomic commits/revisions, rollback, wire replay and recursive erase.
SDK transaction callback retry is also covered by deterministic `Aborted`
injection in the focused unit suite.

Arithmetic against the supplied rounded 106.4M/day baseline is conditional:
76% would be 80.864M/day saved if all reads had the pure-check shape; the actual
artifact shape's 56% would be 59.584M/day saved **if all baseline reads were
eligible with the tested repetition pattern**. Neither is a fleet forecast.
Full-row exports save zero, new source sets/token churn miss, and each cold
artifact call costs one extra user read (6 versus 5). Its hit rate must exceed
25% to beat baseline reads. Production traffic composition and net token-write
cost remain unmeasured. Compare total read volume across both the old live-read
origin and the new direct token-read origin, not just disappearance of the old
`database.batch_pipeline_privacy:read` label.

## Verification (corrected by 1027e)

The prior **837 focused tests** aggregate is withdrawn as unreproduced; its
historical file lists/logs do not establish a reproducible scope here. The
reviewer independently ran six focused unit files: **234 passed**. This fix round
reran exactly those six files, using Python 3.11.15 from this worktree's
`backend/.venv`, through `omi-heavy`:

```sh
/Users/dazheng/workspace/omi/bin/omi-heavy run -- bash -c 'PYTHONPATH=backend backend/.venv/bin/python -m pytest -q backend/tests/unit/test_bpp_generation_fence.py backend/tests/unit/test_bpp_generation_memo.py backend/tests/unit/test_batch_pipeline_privacy.py backend/tests/unit/test_fsr_wq12_batch_privacy.py backend/tests/unit/test_conversation_tombstones.py backend/tests/unit/test_speaker_auto_enroll.py --junitxml=/Volumes/Ephemeral/scratch/wq26-fix-1027e/unit.xml > /Volumes/Ephemeral/scratch/wq26-fix-1027e/unit.log 2>&1'
```

| Unit file under `backend/tests/unit/` | Passed |
|---|---:|
| `test_bpp_generation_fence.py` | 56 |
| `test_bpp_generation_memo.py` | 25 |
| `test_batch_pipeline_privacy.py` | 14 |
| `test_fsr_wq12_batch_privacy.py` | 43 |
| `test_conversation_tombstones.py` | 13 |
| `test_speaker_auto_enroll.py` | 83 |
| **Total** | **234** |

Result: **234 collected, 234 passed, 0 failed, 0 skipped** (4.61s; one
`audioop` deprecation warning). No full backend suite was run in this round.

The WQ26 emulator file collects **30 tests**, not 34. The canonical harness
review run was **29 passed, 1 failed**, because the raw transport replay omitted
emulator-admin authorization metadata. The 1027e fix adds only
`metadata=(('authorization', 'Bearer owner'),)` to that replay; the prepared
Commit and all ABA assertions are unchanged. This round reran the entire file
under the repository's deny-all `firestore.rules`, from the repository root:

```sh
/Users/dazheng/workspace/omi/bin/omi-heavy run -- bash -c 'firebase emulators:exec --only firestore --project demo-omi-isolated-tests "PYTHONPATH=backend backend/.venv/bin/python -m pytest -q backend/tests/integration/test_bpp_generation_fence_emulator.py --junitxml=/Volumes/Ephemeral/scratch/wq26-fix-1027e/emulator.xml" > /Volumes/Ephemeral/scratch/wq26-fix-1027e/emulator.log 2>&1'
```

Result: **30 collected, 30 passed, 0 failed, 0 skipped** (2.98s; `audioop`
deprecation and positional-query warnings). Firebase CLI 15.30.1, Java 21.0.12;
the harness owns the loopback emulator at `127.0.0.1:8085` and shuts it down on
exit. Synthetic demo-project data only; GCP tier **none**. The four separate
list-projection tests from the earlier report are outside this 30-test WQ26
suite and were not rerun or included in this round's count.

The earlier report's `make preflight` claim (37 checks) was historical, not a
reviewer rerun. This round's `make preflight` **failed** after 72.17s (make exit
2): `product-file-line-count-ratchet` cannot measure the synthetic merge of HEAD
into local `origin/main` (`f10cbeb12c0e`) because
`backend/utils/batch_pipeline/retention.py` has a content conflict. No merge or
integration fix was attempted in this test-only round. Log:
`/Volumes/Ephemeral/scratch/wq26-fix-1027e/preflight.log`. Raw suite logs and JUnit counts:
`/Volumes/Ephemeral/scratch/wq26-fix-1027e/{unit,emulator}.{log,xml}`.

## Integrator configuration, rollout boundary and risks

Add only the entry `"bpp_generation_memo": 0` to the integrator-owned runtime JSON
when assembling the themed change; do not replace other lever values. Absence
already means off. This lane edits no runtime literal or deployment file.

The write substrate is intentionally mandatory/unflagged in real writer
processes; reader-off preserves live authorization reads but does not remove the
extra token write. It is not sufficient for readers alone to run this revision:
old backend/listen/sync/backfill/desktop/pusher/worker images, standalone admin
scripts or external writers can leave a memo stale. The integrator must establish
producer inventory and release convergence before enabling any reader cohort.
No deployed revisions were inspected here, and no enablement is authorized.

Recorded rollout caveats from review (documentation only):

- Same-document double-write in one Commit is proto-documented and
  emulator-verified, but **production-unverified**. The writer fence is active
  on deployment even with the reader lever off. Canary a protection-level
  change / purge on the first rollout before broad traffic, and retain that
  check for the first lever-on rollout (or verify via staging end-to-end).
- The future reader-lever enablement PR must explicitly restate and verify
  fleet closure: **all writer services and revisions are fenced**, including
  maintenance producers, with console-edit and staging-replay discipline.
  A passing in-repo suite does not establish that precondition.

Before a separate ramp decision, measure cohort-wide read totals, failed privacy
checks, token-write amplification/contention, and artifact hit rate; a short task
with mostly unique sources can regress reads. Full-row staging/enrichment stays
live by design. No production canary or fleet reduction is claimed. Local
emulator tests are not production contention/load acceptance.

Reader rollback: set the lever to 0/absent. Writer rollback: first disable readers
across the fleet, then revert the source commit; do not remove writer fencing
while any memo-enabled reader remains. No IAM, access, secret, historical data,
capacity, host configuration or production resource changes were made.

## ANX outcome

Recorded through the `anx-participant` skill on `card:loop-firestore-reads` as
`event:9d2845d5-d580-46ae-95c0-8e8215d56a37`. The note distinguishes local
validation from deployed acceptance, names the conditional read reductions and
rollout blockers, and does not complete/change the loop card or take over its
cadence promise. Skill: `/Users/dazheng/.agents/skills/anx-participant/SKILL.md`.
