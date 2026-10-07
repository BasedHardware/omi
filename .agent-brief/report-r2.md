# Round 2 capture-window-coverage — STOPPED, not ready to ship

Worktree: `/Volumes/Ephemeral/scratch/worktrees/omi/omi-lane-capture-window-coverage-upstream-keep-clean`.
Starting HEAD: `0a435947a9`. Existing commits were not amended or rewritten. No push, PR publication, deployment, production data read, or successful cloud/API request is claimed.

## Safety stop

The supplied `.agent-brief/prompt.md` says: **“If any code path you run tries to reach a real cloud service, stop and report it.”**

The broader approved `backend/test.sh` run exposed `BlockedNetworkError` in 16 existing speaker-resolution stage tests. The new clip assembly accesses `session.chunks`; the old `_admit_any_inventory` fixture returns an empty real `AudioChunkReadSession` while mocking only `iter_audio_chunk_pcm`. Accessing that session's inventory enters `storage.list_audio_chunks` / lazy GCS-client construction. The hermetic network guard rejected the attempted nonlocal access. There is no evidence of a successful outbound connection or cloud-data read. The caught exception logs only its type, so the exact attempted hostname was not captured; no further reproduction was attempted.

Stopped upon inspecting that evidence. All four already-started shard processes had exited at typecheck before any shard tests ran; no lane process remained to terminate. No additional test or cloud operation was started. `make preflight` was not run after this stop. This report is the local handoff, not successful completion of Round 2.

## Local commits and intended deployment targets

- `8dfb9f465f` — `fix(listen): project capture windows as gated half-open intervals`.
  Shared `CaptureTimeline.project_window` handles half-open ends and positive wall discontinuities. Legacy attachment opts into strict projection via `LIVE_CAPTURE_WINDOW_STRICT_PROJECTION`; v2 translation uses it unconditionally. New flag defaults off in code, registry, classification, composed manifests and intended Helm declarations. Retention and preservation remain off; v2 remains off in deployed declarations. Receiver/accepted-send/persistence regressions include the original horizon and old retained anchors. **Known Helm insertion error remains in this commit; do not deploy it as-is.** Runtime behavior belongs to **listen / backend-listen**. Shared runtime declarations accompany backend, backend-sync, pusher and the other existing co-host entries; those declarations do not activate the feature. This commit is behavior-gated, not attribution-only.
- `2536c7baab` — `fix(speakers): assemble verified adjacent clips and explain empty evidence`.
  After placement and inventory/decoded-extent verification, concatenate adjacent generation-pinned PCM from the invocation cache, without new reads, gap padding, or interpolation. Clip remains capped at the middle 15 seconds; read, embedding-count and deadline budgets remain. Span-resolution ON uses this for **live, sync and v2** scopes. OFF retains legacy midpoint-chunk clips and cache behavior. Add the ten fixed no-embeddings reasons and anonymous numeric log fields; existing outcome/status/cache formats remain. Processing execution targets are **Cloud Run backend / backend-sync, listen / backend-listen, and pusher** wherever they invoke conversation processing/resolution. This commit combines the R3 behavior repair and bounded diagnostics. **It has typecheck errors and incompatible old test fixtures; do not deploy it as-is.** No new stage-enable switch is added.

## Projection parity and construction analysis

The strict legacy switch is independent of `LIVE_CAPTURE_WINDOW_RETENTION`, including retention OFF. An unconditional legacy correctness fix would change stored windows within the old 64-anchor horizon, so it was not shipped unconditionally for legacy.

With strict projection OFF, the helper delegates to exactly the old two `wall_strict` endpoint lookups: **zero additional base windows are refused by construction**. With strict ON, among otherwise-projectable nonempty base intervals, newly refused windows are precisely those with `start < anchor_sample < end` at at least one positive wall discontinuity. An exclusive end equal to an anchor is corrected using the preceding slope, without refusal; a start equal to the anchor uses the right-hand interval. Compacted ranges still refuse. A fleet count cannot be inferred without data, which this lane is forbidden to read.

The synthetic three-window set `[.9,1.1)`, `[.9,1)`, `[1,1.1)` has one newly refused crossing, one corrected exclusive end, and one unchanged right-hand window. Both the two-frame original-horizon case and seventy-frame retained-anchor case exercise this construction. V2 always uses strict projection but the deployment flag remains false; this is a dormant v2 correctness change.

## Tests and exact commands

All commands below ran from `backend/`, except the explicitly named source-overlay wrapper and registry commands. No bare pytest was used. Logs and receipts are under `.agent-brief/`.

1. `python3 .agent-brief/r2-head-proof.py` (repository root).
   This local wrapper saves the four changed runtime Python files, overlays their exact `git show 0a435947a9:<path>` contents, invokes only the approved file-list test runner, and restores candidate bytes in `finally`. No commits or refs are rewritten. Its test invocation is `BACKEND_UNIT_TEST_FILE_LIST=../.agent-brief/r2-tests.txt PYTHON=.venv/bin/python PYTHONDONTWRITEBYTECODE=1 bash test.sh`.
   - `r2-red-head.log`: **22 failed, 32 passed**, exit 1. R1: 8 failures (crossing/exact end, legacy/v2, original/retained horizon). R3/diagnostics: 14 failures (three adjacent-chunk scope cases, all ten reason labels, exact 15-second assembly). The corrected v2 fixture uses the actual provenance model; boundary comparisons use absolute 1 microsecond tolerance and `rel=0`.
2. `BACKEND_UNIT_TEST_FILE_LIST=../.agent-brief/r2-tests.txt PYTHON=.venv/bin/python bash test.sh`.
   - `r2-green.log`: **54 passed**, exit 0 with the local **0.30-second** call-phase guard. Includes gaps of .0005 and .01 seconds refused without embedding, exact original PCM across two chunks, and OFF sync/v2 legacy behavior/cache keys. No guard was raised or disabled.
3. HEAD and candidate OFF replay:
   `BACKEND_UNIT_TEST_FILE_LIST=../.agent-brief/r2-parity-tests.txt PYTHON=.venv/bin/python CAPTURE_PARITY_OUTPUT=../.agent-brief/r2-capture-candidate.json RESOLUTION_PARITY_OUTPUT=../.agent-brief/r2-resolution-candidate.json bash test.sh`.
   The wrapper in step 1 runs the same list against exact HEAD runtime source and writes `*-head.json`.
   - `r2-parity-head.log` and `r2-parity-candidate.log`: **2 passed each**, exit 0. Parsed receipt equality: capture **true**, resolution **true**. Capture receipt includes persisted payloads and existing counters across three providers, compaction, merging, out-of-range timestamps and a recent hiatus crossing. Resolution receipt compares four OFF sync/v2 cases: public payload/status, exact cache bytes, diarizer call count and existing outcome/placement counters. New reason-series/log details are additive, intentionally not identical. Existing ON->OFF cache protections are not certified by the failed broader suite.
4. `BACKEND_UNIT_TEST_FILE_LIST=../.agent-brief/r2-focused-tests.txt PYTHON=.venv/bin/python bash test.sh`.
   - `r2-focused.log`: **500 passed, 32 failed across 18 files**, exit 1. Failures: declaration test 1; runtime-env tests 12; pusher-config tests 3; stage-fixture tests 16. One additional existing runtime-env test breaches the 0.30-second CPU guard (display rounds to 0.30). New R1/R3/reason tests pass in this run. This is the run that triggers the safety stop. No CPU exception or allowance was added.
5. `PYTHON=.venv/bin/python bash scripts/run-unit-ci.sh --all --shard 4/1`, and identically `4/2`, `4/3`, `4/4`.
   - `r2-shard-1.log` through `r2-shard-4.log`: **all exit 1 at typecheck**, each **2 errors, 12,797 warnings**, **0 shard tests executed**. Environment preflight reports 17 passed, 9 warnings, 0 failed checks in each. The CLI accepts `total/index`, so `4/k` is the correct four-shard spelling, rather than `k/4` in the request. Its documented internal CI guard was not edited; the selected new tests separately passed under the default local guard.
   - Both type errors are introduced by the diagnostic helper: `speaker_resolution.py:846` indexes a `Mapping[str,...]` with an optional segment ID. Narrow/assert the truthy ID in the vector extraction comprehension, then rerun typecheck via the canonical runner.
6. Source generation: `python3 backend/deploy/compose_runtime_env.py`; `python3 scripts/render_feature_flag_registry.py` — exit 0 before commits. `git diff --check` — exit 0 before commits. `scripts/pr-preflight --suggest` — completed locally; output `r2-preflight-suggest.txt`. **Full `make preflight` and source admission validation remain unrun after the safety stop.**

## Diagnostic policy

Exactly ten primary reason labels: `all_short`, `no_eligible`, `chunk_boundary`, `clip_too_short`, `embed_failed`, `budget`, `max_embeddings`, `invalid_vector`, `missing_vector`, `no_clip`.

Precedence: no eligible IDs/speakers, all short eligible speech, invalid vectors, budget/cap, embedding failures, chunk boundary, short clip, missing keyed vector, then no clip. One reason counter increment per no-embeddings outcome. Numeric fields retain mixed-population information: stop, embeddable, pending, cache hits, new embeddings, valid vectors, clip skips/failures, eligible/short counts, speech seconds, excluded IDs/speakers, requested/successful counts, invalid/missing vectors, stale entries and clip counts. Existing resolved log also becomes anonymous and gets the required bounded counts. No new transcript/path/cache-key/provider-body/uid/user-derived labels. Existing unrelated failure logs retain their earlier behavior.

## Outstanding repairs and residual risks

1. **Helm YAML is malformed semantically:** insertion placed the strict flag immediately after the retention `name`, before retention's `value`, leaving retention without a value and strict with duplicate values. Repair all four listen/pusher values files to give each flag exactly one explicit false value. Then run the declaration/validator/pusher suites and source admission gates. No flag should be enabled.
2. **Fix old fixtures before running them:** `_admit_any_inventory` must return a fully local, populated decoded cache and inventory corresponding to the mocked PCM. Never let the fake session lazily construct a storage client. `_install_audio` and mixed/rebased audio tests must supply the local objects to the assembly path; do not solve this with a production fallback to unverified iteration or disable the network guard.
3. **Fix the two optional-ID type errors** above. No typecheck suppressions.
4. **Sync/v2 edge tolerance needs qualification:** assembly currently refuses incomplete extents, including a longer otherwise-embeddable window whose decoded tail is short within existing placement tolerance. A safe no-worse version can trim only the leading/trailing tolerance-sized edge to actual verified PCM while preserving the one-second minimum; it must never concatenate over an internal missing extent. Add regression evidence before claiming all sync/v2 inputs are no worse. Current proof covers exact adjacent/single extents and OFF behavior only.
5. New tests pass the local guard, but the broader run has an existing runtime-env call-phase breach under concurrent shard/typecheck load. No guard change is allowed. After repairs, run the entire focused list without competing lane jobs, then all four shards and full local preflight with a local PR-body file to avoid API lookup.
6. Retention memory/callback-load qualification remains required before ON, as in the independent review. The new legacy strict switch defaults off, so the pre-existing hiatus weakness remains until separately enabled. This report does not certify production mixture, deployed artifacts, voice accuracy, fleet capacity or live acceptance. Invalid cached vectors are diagnosed without changing cache policy or wholesale invalidation.

## R2 preservation: no changes this round

Preservation stays OFF and its implementation was not changed. A safe next version needs a presentation grouping layer over original pieces that retains every piece ID, capture proof, speaker/manual-receipt authority and replay lineage while rendering coherent turns. Grouping must not replace pieces with a made-up union window across gaps. Embedding eligibility should be computed from grouped original pieces, with each PCM piece independently placed and verified, enough eligible audio collected within existing caps, and explicit handling of internal gaps without manufacturing proof. Test word-level providers and mixed-speaker repairs, then visibly qualify live/detail transcript rendering plus summary/action-item inputs. The current short-fragment behavior cannot be promoted based only on increased field coverage.
