# Round 3 capture-window-coverage — completed locally

Worktree: `/Volumes/Ephemeral/scratch/worktrees/omi/omi-lane-capture-window-coverage-upstream-keep-clean`.
Starting HEAD: `dbb1b959ca6501fe1baede1b4dc3462339c348a4`. Implementation/test HEAD: `de8dd1ea0f`.
New commits only; no amend, history rewrite, push, PR publication, deployment, production-data read or cloud/API operation. No sync/fetch was needed: this round explicitly builds on the coordinator's pinned HEAD. The coordinator's ruling permits fixing hermetic fixture blocks and continuing; no guard was relaxed and no production fallback was added.

## New local commits and deploy targets

| Commit | Repair | Deployment scope |
| --- | --- | --- |
| `3d766565eb` | Repair all four dev/prod listen/pusher Helm files: retention, strict projection and preservation each occur exactly once, each with explicit string `false`. Regenerate the registry, which now reports retention as false rather than merely declared. Update offline Cloud Run fixture declarations and the exact pusher expected-env dictionary with the strict flag. | Helm configuration: **listen / backend-listen and pusher**, dev and prod. Runtime manifests on **Cloud Run backend / backend-sync** and their existing cohosts remain off for these three flags. This commit enables nothing. |
| `11e22914b0` | `_admit_any_inventory` now receives explicit fixture audio, freezes a populated local inventory with generations/spans and fills decoded PCM cache entries. `_install_audio`, mixed sync/live and rebased survivor/donor fixtures pass the corresponding audio objects. No lazy storage listing/decode remains at assembly. | Tests only; no runtime deployment target. |
| `1bdf9570b9` | Narrow optional segment IDs with `s.id is not None` before both keyed vector lookup and mapping access. No suppression. | Shared speaker resolution on **Cloud Run backend / backend-sync**, **listen / backend-listen**, and **pusher** wherever conversation processing runs; also existing backend-sync-backfill/backend-integration cohosts. |
| `5437cf5679` | Trim only an at-most-1 ms missing leading or trailing edge to verified decoded PCM. Reject an internal gap, retain the one-second actual PCM minimum, middle-15-second maximum, generation-pinned cache, budgets and cache format. Update the owning pipeline documentation and add 22 local regressions. | Same shared processing targets as the narrowing commit. Behavior applies with **LIVE_SPEAKER_SPAN_RESOLUTION ON** to live, sync and v2 placements; OFF retains legacy midpoint clips. No new flag is enabled. |
| `af3864a4f2` | Make the existing composed declaration test use the safe C YAML loader. Reuse the existing module-scoped capability fixture rather than parsing the large manifest in the capability test call phase. Assertions and timing guards are unchanged. | Tests only. |
| `de8dd1ea0f` | Make an existing cached manual-teaching `_embed_missing` mock accept the new diagnostics kwargs. Its previous TypeError prevented scope normalization in two cases. | Tests only. |

The round 2 half-open projection and ten anonymous no-embeddings reasons remain intact. `LIVE_CAPTURE_WINDOW_RETENTION`, `LIVE_CAPTURE_WINDOW_MERGE_PRESERVATION`, `LIVE_CAPTURE_WINDOW_STRICT_PROJECTION` remain OFF in deployment declarations; `AUDIO_TIMELINE_V2` remains false. Preservation behavior was not edited. No public API/status/storage/cache-format change or wholesale embedding-cache invalidation.

## Edge proof and limits

The assembler reads only the invocation's admitted decoded cache. Before the first PCM piece it may advance the requested start by at most the existing `COVERAGE_TOLERANCE_SECONDS=0.001`. After the last piece it may finish at the actual verified end if the missing tail is at most that same tolerance. Between pieces only sub-sample wall-axis floating roundoff is accepted; an actual internal gap refuses. Concatenation contains original sample bytes only, with no padding, interpolation or additional storage reads. A trimmed clip must still contain at least 16,000 PCM16 samples.

The new test file loads exact pre-round-2 `0a435947a9` stage source from local Git in a module-scoped fixture. Fourteen sync/v2 replay cases cover exact continuous audio, leading/trailing/both 0.5 ms edges, adjacent chunks with a short tail, exactly one second after trimming and a just-under-one-second clip. Candidate embedding availability is at least base availability in this set; when base embeds, candidate remains resolved with identical cache bytes and at least as many verified PCM samples. Candidate clips equal the original decoded pieces byte-for-byte. Four stage cases prove 0.5 ms and 10 ms internal gaps refuse, including a tolerated tail; four helper cases admit exactly 1 ms edges and refuse 1.1 ms edges.

This qualifies continuous, otherwise-admitted synthetic inputs and the required tolerance behavior. It does not promise availability parity for missing/internal-gap/malformed inventories, certify all fleet inputs, or measure voice accuracy. Those unsafe inputs remain fail-closed even where the old midpoint policy could use a partial chunk.

## Exact local test commands and counts

Backend commands below ran from `backend/`, solely through the approved `test.sh` file lists or canonical shard runner. File-isolated focused runs use `BACKEND_PYTEST_WORKERS=1`; the local call-phase guard stays **0.30 s**. No timing allowlist or guard setting was added/raised. The canonical shard runner retains its own checked-in CI guard. No bare pytest was run.

1. Source admission, repository root:
   - `python3 backend/deploy/compose_runtime_env.py --check` — exit 0.
   - `python3 scripts/render_feature_flag_registry.py` then `python3 scripts/check_feature_flag_registry.py` — exit 0.
   - `python3 backend/scripts/verify_pusher_cohost_env_diff.py` — exit 0, both dev/prod.
   - `python3 backend/scripts/validate-backend-runtime-env.py --env dev --check-workflows`, then the identical prod command — exit 0 each. No live-cloud argument was used.
2. Declaration suite: `BACKEND_PYTEST_WORKERS=1 BACKEND_UNIT_TEST_FILE_LIST=../.agent-brief/r3-declaration-tests.txt PYTHON=.venv/bin/python bash test.sh` — **257 passed across 6 files**, exit 0; `r3-declarations-serial.log`. The initial default-worker run found stale strict-flag fixtures/expected env: **253 passed, 4 failed**, plus timing breaches; `r3-declarations.log`. Fixtures were repaired; the serial retry passed.
3. Local stage fixtures: `BACKEND_PYTEST_WORKERS=1 BACKEND_UNIT_TEST_FILE_LIST=../.agent-brief/r3-fixture-tests.txt PYTHON=.venv/bin/python bash test.sh` — **60 passed**, exit 0; `r3-fixtures.log`. Includes mixed/rebased assembly, growing-cache behavior and ON→OFF protections.
4. `PYTHON=.venv/bin/python bash scripts/typecheck.sh` — **0 errors, 12,797 warnings, 0 informations**, exit 0; `r3-typecheck.log`. The same counts repeat in every canonical shard invocation.
5. Edge regression red proof: `python3 .agent-brief/r3-edge-red-proof.py` at repository root. It saves the candidate speaker stage, overlays exact `git show dbb1b959ca:backend/utils/conversations/speaker_resolution.py`, runs only `BACKEND_PYTEST_WORKERS=1 BACKEND_UNIT_TEST_FILE_LIST=../.agent-brief/r3-edge-red-tests.txt PYTHON=.venv/bin/python PYTHONDONTWRITEBYTECODE=1 bash test.sh`, and restores candidate bytes in `finally`. **12 failed, 10 passed**, test runner exit 1 as expected; `r3-edges-red.log`. No ref/commit rewrite.
6. Edge and round 2 assembly/reason/OFF regressions: `BACKEND_PYTEST_WORKERS=1 BACKEND_UNIT_TEST_FILE_LIST=../.agent-brief/r3-edge-tests.txt PYTHON=.venv/bin/python bash test.sh` — **40 passed across 2 files**, exit 0; `r3-edges.log`.
7. Full focused list, with no competing shard/typecheck job: `BACKEND_PYTEST_WORKERS=1 BACKEND_UNIT_TEST_FILE_LIST=../.agent-brief/r3-focused-tests.txt PYTHON=.venv/bin/python bash test.sh`.
   - Initial pass: **575 passed across 20 files**, exit 1 solely from two existing CPU breaches: composed declaration 0.33 s and capability inventory just above 0.30 s; `r3-focused.log`.
   - After timing repair: **575 passed across 20 files**, exit 0; `r3-focused-final.log`.
   - After adding the manual-teaching file exposed by shard 4: **610 passed across 21 files**, exit 0; `r3-focused-complete.log`. All 22 new tests executed without guard breaches.
8. Full canonical unit shards, executed sequentially: `PYTHON=.venv/bin/python bash scripts/run-unit-ci.sh --all --shard 4/k`, k=1,2,3,4. The CLI spelling is total/index. Every invocation's environment preflight reports **17 passed, 9 warnings, 0 failed checks**; typecheck **0 errors / 12,797 warnings**. Final test receipts:

   | Shard | Selected files | Passed | Failed | Skipped | Deselected | Exit | Receipt |
   | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
   | 4/1 | 396 | 6,213 | 0 | 0 | 24 | 0 | `r3-shard-1.log` |
   | 4/2 | 396 | 7,614 | 0 | 1 | 712 | 0 | `r3-shard-2.log` |
   | 4/3 | 396 | 7,503 | 0 | 2 | 18 | 0 | `r3-shard-3.log` |
   | 4/4 | 395 | 7,260 | 0 | 24 | 1,338 | 0 | `r3-shard-4-final.log` |
   | Total | **1,583** | **28,590** | **0** | **27** | **2,092** | | |

   Original shard 4: **7,258 passed, 2 failed, 24 skipped, 1,338 deselected**, exit 1; `r3-shard-4.log`. Both failures were the cached manual-teaching fixture TypeError. After the test-only `de8dd1ea0f` repair, reran the expanded focused list alone, then reran the full 4/4 shard. Shards 1–3 ran at `af3864a4f2`; their files and all runtime source were unchanged by this fixture repair. The successful shard 4 rerun and expanded focused receipt ran at `de8dd1ea0f`. The 27 skips are existing cases, including real-libopus decoding, dev-only API-key revocation cases and inapplicable transport combinations; no new test was skipped. Parsed totals are saved in `r3-test-counts.json`.
9. Local PR metadata: `scripts/pr-preflight --suggest` generated `r3-preflight-suggest.txt`. `scripts/pr-preflight --pr-body-file .agent-brief/pr-body-r3.md --metadata-only` — **4 checks passed**, exit 0; `r3-pr-body-validation.log`. The local body cites INV-MEM-4 and records Failure-Class: none with rationale. No API lookup/publication.
10. Full local preflight: `OMI_PR_BODY_FILE=.agent-brief/pr-body-r3.md make preflight` — **45 checks passed**, exit 0 in **242.16 s**; `r3-preflight.log`. Metadata came from the local body file, with no PR API lookup.
11. OFF replay receipt refresh: `BACKEND_PYTEST_WORKERS=1 BACKEND_UNIT_TEST_FILE_LIST=../.agent-brief/r2-parity-tests.txt PYTHON=.venv/bin/python CAPTURE_PARITY_OUTPUT=../.agent-brief/r3-capture-candidate.json RESOLUTION_PARITY_OUTPUT=../.agent-brief/r3-resolution-candidate.json bash test.sh` — **2 passed**, exit 0; `r3-parity.log`. Parsed current capture and resolution receipts each equal the recorded exact `0a435947a9` HEAD receipts from round 2: **capture true, resolution true**; `r3-off-parity-equality.json`. This refresh compares the new candidate with the saved baseline artifacts; the baseline source was not rerun this round. Equality includes persisted payloads, existing counters, status/cache bytes and diarizer call counts for the exercised cases. New anonymous diagnostics remain additive.
12. `git diff --check` — exit 0; implementation worktree clean before adding this report. This report is added in a separate local documentation commit after verification.

## Remaining risks and rollout limits

- These are local source/unit/admission results, not a built/deployed artifact, remote GitHub CI, production-data audit, rendered product acceptance or diarizer voice-quality measurement. No flag promotion/deployment is authorized or performed.
- Retention still needs the previously reported fleet memory and concurrent callback-cost qualification before ON. Strict legacy projection remains default off, so the old within-horizon hiatus weakness remains dormant behind that rollout decision. V2 translation is strict in code but v2 remains disabled in deployment declarations.
- The assembler tolerates only 1 ms outer clipping. Missing internal extents remain refused. Existing inventory decode validation has its own tolerance/budgets; tests cannot establish every production input's availability. Placement proof does not certify the semantic correctness of the PCM, nor revalidate cached vectors against generation/content on every hit.
- Existing invalid cached vectors remain diagnosed without changing their cache policy. The anonymous reason labels/counts classify processing outcomes, not distinct conversations or fleet causal proportions.
- Preservation stays OFF and unchanged. A safe future version needs presentation grouping over original pieces, retaining each ID, capture proof, speaker/manual-receipt authority and replay lineage, plus embedding from independently placed/verified original PCM pieces within existing caps. It must explicitly handle internal gaps without manufacturing a union proof, qualify word-level/mixed-speaker cases, and visibly validate live/detail transcript rendering and summary/action-item inputs. More windowed short fragments alone are not an acceptance criterion.
