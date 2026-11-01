# Scoped CI fixes for PR #21743

Base: `0071ab2fcb` on `lane/dream-38-launch`.

Only the failures named in `sol-ci-fixes.md` were investigated and changed. No `.github/` changes, Cloud Run mutations, gcloud commands, production API calls, pushes, or fixes to the listed main-branch failures.

## Per-test findings

| Test | Root cause and disposition | Targeted result |
| --- | --- | --- |
| `test_cloud_run_state_rejects_old_secret_versions` | **Test fixture update.** The handwritten dev snapshots omitted the three newly required Dream bindings on their processing hosts. The shared helper now covers backend, backend-sync, backend-sync-backfill, and backend-integration, supplying the bindings from the manifest without copying the account allowlist into test source. Old-secret rejection assertions remain intact. Manifest scope is intentional: these processing hosts admit Dream. | PASS; runtime-env validator file 165/165 |
| `test_cloud_run_state_reports_missing_gateway_url` | **Test fixture update.** Same incomplete snapshots caused nine unrelated missing-env errors. Complete the Dream bindings and preserve the exact missing-gateway error and backend scope checks. | PASS; runtime-env validator file 165/165 |
| `test_cloud_run_workflow_validation_uses_custom_manifest_for_runtime_env_outputs` | **Test fixture update.** Its custom-workflow portion passed; the later default-manifest Cloud Run snapshot was incomplete. Same fixture repair; custom-manifest behavior is unchanged. | PASS; runtime-env validator file 165/165 |
| `test_shaped_scope_is_trusted_quoted_and_after_cache_prefix` | **Code fix.** The shared harness began caching the first evidence message by default, moving chat's stable breakpoint into its history or volatile scope message. Add a mount choice for initial-evidence caching and disable it for chat. Chat keeps its stable system breakpoint, its separately marked history epoch, and uncached quoted scope/current request. Other agent seed caching remains enabled. | PASS: both history variants; addressable-ref file 18/18 |
| `test_signed_tool_history_survives_both_hops_and_old_client_history_is_admitted` | **Test update for intentional routing change.** The test assumed a desktop Pro alias could consume the active 3.8 reservation. It now asserts that route is unavailable to desktop, and separately exercises the existing Gemini wire/signature adapter for 3.1 Flash-Lite and 3.8, streaming/nonstreaming and legacy/current histories. This retains real signatures and the legacy admission marker without authorizing a paid desktop route onto Dream capacity. | PASS: all 8 adapter variants; signature file 13/13 |
| `test_no_recovery_plan_ever_routes_onto_the_reservation` | **Code fix plus current-policy coverage.** A direct recovery lookup could ask for 2.5 capacity after policy had moved it to Luna, raising ValueError; the 3.8 helper could also retry the reservation as shared. Direct proxy recovery now returns no Gemini retry for either reservation model. The test covers every ACTIVE/INACTIVE/UNKNOWN pair for the actual 2.5/3.8 models, checks protected destinations, and requires empty reservation recovery plans. | PASS: all 9 state pairs; proxy file 136/136 |
| `test_streaming_overflow_falls_back_and_leaks_no_provider_slot` | **Test update for intentional routing change.** The old assertion demanded a direct 2.5-to-Flash-Lite PayGo retry, which the new gateway/Luna policy forbids. Renamed to `test_streaming_reservation_overflow_stops_and_leaks_no_provider_slot`; requires one closed upstream attempt, a terminal rate-limit event, no Gemini fallback, and a released provider semaphore. | PASS; proxy file 136/136 |
| `test_followup_unicode_description_reserves_and_settles` | **Code fix.** Producers fitted the request to its exact UTF-8 byte ceiling before the gateway added explicit cache options, causing `input_bound` rejection. Structured producer requests now include those defaults before trimming. These single-user prompts have no reusable prefix, so this preserves the gateway's existing cache behavior and does not enlarge the admission ceiling. | PASS; request-contract file 32/32 |
| `test_mentor_large_context_requests_reserve_and_settle` | **Code fix.** Same post-fit cache-field growth. All five context variants must traverse real gateway validation, reservation, provider mock, and settlement. Cache options and Luna identity are also asserted by the basic wire contract. Gateway max(input, cache_write) reservation pricing and cache-part validation remain unchanged and have adjacent coverage. | PASS: all 5 context variants; request-contract file 32/32 |

## Validation

Baseline: the five scoped test files reproduced all named failures (16 failing parameterized cases). Log: `.agent-brief/sol-ci-fixes-baseline.log`.

The post-fix run selects the five scoped files plus adjacent proactivity admission/producer, gateway cache, shaped-agent/context, and Vertex routing contracts. Tests run through `backend/test.sh`, file isolated with `BACKEND_PYTEST_WORKERS=1`, prefixed by `nice -n 19 taskpolicy -b`.

```sh
nice -n 19 taskpolicy -b env \
  BACKEND_UNIT_TEST_FILE_LIST="$PWD/.agent-brief/sol-ci-fixes-tests.txt" \
  BACKEND_PYTEST_WORKERS=1 bash backend/test.sh
```

Result: **660 tests passed across the 12 selected files**, using the final result for each file:

| File (`tests/unit/`) | Passed |
| --- | ---: |
| `test_backend_runtime_env_validator.py` | 165 |
| `test_chat_addressable_refs.py` | 18 |
| `test_desktop_gemini_signature_contract.py` | 13 |
| `test_desktop_proxy.py` | 136 |
| `test_proactivity_v2_request_contract.py` | 32 |
| `test_proactivity_v2_gateway.py` | 54 |
| `test_proactivity_v2_producers.py` | 66 |
| `test_gateway_cache_policy.py` | 5 |
| `test_shaped_agent.py` | 61 |
| `test_shaped_agent_cache_invariant.py` | 3 |
| `test_shaped_chat_context.py` | 21 |
| `test_vertex_pt_routing.py` | 86 |

The first expanded run passed all 495 tests in the other eleven files but exposed that the initial fixture repair had omitted backend-integration. After completing that fixture, the full 165-test validator file passed in a separate serial run (exit 0). Logs: `.agent-brief/sol-ci-fixes-rerun.log` and `.agent-brief/sol-ci-fixes-validator-rerun.log`. Selections: `.agent-brief/sol-ci-fixes-tests.txt` and `.agent-brief/sol-ci-fixes-validator-tests.txt`.

The final validator command used the same runner and priority prefix, with `BACKEND_UNIT_TEST_FILE_LIST="$PWD/.agent-brief/sol-ci-fixes-validator-tests.txt"`.

Additional checks passed:

- Pinned backend Python formatter: all eight changed Python files unchanged (`BLACK_NUM_WORKERS=1`).
- Async-blocker gate scoped to the four changed production files with `--diff-base HEAD`: zero selected findings, exit 0. Log: `.agent-brief/sol-ci-fixes-async-scan.log`.
- `git diff --check`.

Manifest scope was checked against the shared post-write scheduling path (`database/dream_dirty.py`, `database/dream_store.py`) and `config/dream_agent.py`; the fixture was repaired instead of weakening rollout validation.

No full preflight was run, as required by the brief. This report describes local checks, not remote CI or deployment.
