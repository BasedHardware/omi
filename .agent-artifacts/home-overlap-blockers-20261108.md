# Home overlap review blockers: local evidence

Measured 2026-11-08T03:39:43+00:00. Repository: BasedHardware/omi; branch: lane/home-overlap; candidate parent: ba47f2a917da63ec2da1b5dbca6e0f901e8478a0. No GCP tier, production access, deploy or merge.

## Behavior and regressions

- Home list omissions require a valid echoed episode/member pair for the current live owner. Missing, malformed, mismatched and stale-member snapshots retain recordings, including new members and unlinked overlapping recordings. Omission response headers preserve acknowledged source rows locally. The held-member and live ownership kill switches remain independent. `test_homesettle.py` covers each boundary; the app provider test executes an actual failed episode fetch before acknowledging a fetched live snapshot.
- Recording detail grants 4,200 seconds of narrow intent: maximum hold plus one quiet window. Real enrichment callback admission is clock-driven at 300, 599, 600, 601, 3,601 and 4,201 seconds. No notes run before admission or after lease expiry while a live owner remains. The durable enqueue still precedes the Redis lease.
- Both process entry and finalizer preflight bypass empty-transcript notes waits, including photo-only rows. Retained batch registration precedes early and late actual notes waits; refusal prevents yielding. Tests exercise the production entry body and finalizer scheduling boundary.
- `finish_absorb` really did wrap scheduling deferrals as `SmartMergeIncomplete`. The explicit propagation now reaches finalizer scheduling without failure retry/fanout. Survivor refresh still compare-and-releases its lease through the existing exception boundary.
- Legacy fake-Redis payloads physically omit both new admission metadata keys. Decoding and pending projection preserve visibility, count one and existing TTL with ownership either enabled or disabled.

## Backend tests

Each file ran as its own command from `backend`, with the shell looping outside `omi-heavy`:

```sh
/Users/dazheng/workspace/omi/bin/omi-heavy run -- .venv/bin/python -m pytest -q tests/unit/<file>.py
```

| File | Passed |
| --- | ---: |
| `test_capture_group_notes_refresh.py` | 20 |
| `test_conversation_action_item_mirror.py` | 3 |
| `test_conversation_events_bounds.py` | 21 |
| `test_conversation_finalization_jobs.py` | 78 |
| `test_conversation_finalizer_failure_logging.py` | 3 |
| `test_conversation_smart_merge_finalizer.py` | 33 |
| `test_episodes_finalizer_hook.py` | 32 |
| `test_homesettle.py` | 58 |
| `test_meeting_evidence_admission.py` | 33 |
| `test_pending_work.py` | 50 |
| `test_phone_batch_process_now.py` | 13 |
| `test_sync_job_retention.py` | 31 |
| `test_sync_v2.py` | 176 |

Total: 551 passing cases across 13 files. After the final review changes, the affected Home, episode hook, smart-merge, meeting-admission and failure-logging files were rerun. No file used a combined pytest session. Capacity retries were limited to exit 75.

## Flutter and metadata

From `app`, through `omi-heavy run --`:

```sh
/Users/dazheng/.local/share/mise/installs/flutter/3.44.5/bin/flutter test --no-pub --timeout 90s --dart-define=HOME_ROW_RENDER_OUTPUT=<scratch-render-directory> test/unit/episode_provider_test.dart test/unit/home_rows_test.dart test/unit/home_rows_state_space_test.dart test/widgets/home_row_contract_render_test.dart test/services/pending_work_store_test.dart test/widgets/pending_work_test.dart test/providers/conversation_home_typed_fetch_test.dart
```

116 passed with Flutter 3.44.5 / Dart 3.12.2, including Home render and failed-fetch acknowledgment tests. The regenerated after PNG is byte-identical to the committed image: SHA-256 `36b858994fbfd786b917a26e3ae043480d86f6ccf5a7ffdc1af0d3bf52638139`. This follow-up changes acknowledgment transport and backend scheduling, with no widget layout edit. Existing tracked renders remain applicable.

`scripts/pr-preflight --suggest` ran; `scripts/pr-preflight --metadata-only --pr-body-file <draft>` passed all five checks. Python formatting and whitespace checks passed. Full preflight, normal pre-push, pushed identity, CI and final independent review results belong to the PR's current validation section.

## Attempt notes

The first new lease fixture omitted its required runtime stage and failed before enqueue; setting its hermetic prod-stage namespace corrected it. An early metadata run detected a concurrent source edit; its settled reruns passed. Two full preflight runs were deliberately stopped by verified owned process group when subsequent edits/review made their snapshots stale. No other lane's processes, check settings, production data or flag defaults changed.

## Final local gates and CI fixture

The previous published head's backend shard failed 21 events/assignment tests at router import: its fake database package could not load the newly imported notes outbox. The fixture now stubs the unrelated notes seam, matching the existing action-item fixture. The corrected file passes all 21 assertions in its own `omi-heavy` command. Production behavior is unchanged by that fixture correction.

Independent source re-review returned PASS after exact member acknowledgments, omission restoration headers and the early finalizer transcript guard were added. One optional missing-echo header assertion is reserved for a separate owned follow-up PR. Full `make preflight` passed 71 checks (exit 0); the PR body records publication and final review identity. Initial publication pre-push will revalidate the committed tree, including the fixture.

Record finalized 2026-11-08T04:02:31+00:00.

The first commit attempt was correctly refused because Homebrew Flutter had drifted to 3.47.9. The installed pinned 3.44.5 formatter made no file changes; all 116 Flutter tests were rerun with that SDK and fresh render comparison. The guard was not bypassed.
