# Second CI repair round for PR #21743

Starting HEAD: `f456a436d62` on `lane/dream-38-launch`.

## Per-failure findings

1. **Dev runtime first-user guard.** Dream's new allowlist contained an account identifier in six dev overlay bindings and both dev charts even though Dream is disabled there. All eight dev declarations now use an empty string. The composed manifest was regenerated. Production allowlists are unchanged, and the guard test is unchanged. The previous validator fixture already derives all three Dream values from the dev manifest, so it now receives the empty value automatically; its comment was corrected to describe disabled dev admission. Verification: runtime validator **165 passed**; manifest renderer **49 passed**, including the unchanged first-user guard.

2. **Dev pusher literal contract.** The strict expected-literals dictionary omitted the three Dream bindings introduced by this PR. Added `DREAM_AGENT_ELIGIBILITY=allowlist`, empty `DREAM_AGENT_UID_ALLOWLIST`, and `DREAM_ON_DEMAND_ENABLED=true`, matching the source declarations. Verification: pusher config references **28 passed**, including the named contract test.

3. **Prod desktop manifest/workflow mismatch.** This PR declared a desktop minimum-build literal that the prod workflow does not deploy. Removed that literal and its comment from the prod overlay. Composition retains the base environment passthrough declaration, with no default value; unset behavior remains fail-open. Regenerated the composed manifest and feature-flag registry using the existing as-of date. No affected test pins the removed build literal. Verification: desktop workflow parity test passes in the **49-test** renderer file; dev and prod offline workflow validators, compose staleness, and feature-flag registry checks pass. A structural comparison confirms the only production manifest change is removal of that desktop literal; all production allowlists remain identical.

4. **Vertex managed call-site inventory.** `VertexPTPolicyMixin._endpoint` now builds Dream's actual generation URL for the two private Dream lanes. This is a generation endpoint, not a reservation-state probe. Added a dedicated `dream_vertex_generation` inventory row with its exact host call site, pinned model/location, capacity rules, tool/schema shape, backend admission gates, and relevant guardrail coverage. The row explicitly records that S1 authorization is not wired at this internal entrypoint, following the inventory's `none_unwired` convention. Verification: slow guardrails **2 passed, 24 deselected**, including the exact-set inventory check; the fast portion of the same file **24 passed, 2 deselected**, including inventory schema, code-path, and declared-policy checks.

5. **Torn repair-journal test.** The reported failure did not reproduce: all eight parameter combinations pass. The full repair file has **205 passing assertions**. The PR diff does not touch this test, its repair script, the strict Firestore fixture, or the deterministic-minimum/recovery/transcript-hash helpers it imports. No repair-code changes were made. The first run hit an unrelated local CPU guard in `test_lease_expiry_uses_fresh_gcs_time_and_takeover_grace[-10000000]` (0.32s versus 0.30s) while all 205 assertions passed. A serial rerun with the same limits exits **0**, with that test at 0.25s (warning only). The original journal failure's cause remains unconfirmed; this is not evidence of a fixed journal defect.

## Verification commands

All test and render/check commands use `nice -n 19 taskpolicy -b`. Fast tests use `backend/test.sh` with file lists relative to backend and `BACKEND_PYTEST_WORKERS=1`; test runs never overlap.

```sh
nice -n 19 taskpolicy -b env \
  BACKEND_UNIT_TEST_FILE_LIST="$PWD/.agent-brief/sol-ci-fixes-2-tests.txt" \
  BACKEND_PYTEST_WORKERS=1 bash backend/test.sh

nice -n 19 taskpolicy -b env \
  BACKEND_UNIT_TEST_FILE_LIST="$PWD/.agent-brief/sol-ci-fixes-2-journal-tests.txt" \
  BACKEND_PYTEST_WORKERS=1 bash backend/test.sh

nice -n 19 taskpolicy -b env \
  BACKEND_UNIT_TEST_FILE_LIST="$PWD/.agent-brief/sol-ci-fixes-2-inventory-tests.txt" \
  BACKEND_PYTEST_WORKERS=1 bash backend/test.sh

# From backend/, matching run-slow-guardrails-ci.sh for this file only:
nice -n 19 taskpolicy -b .venv/bin/python -m pytest -q -p no:cacheprovider \
  -m "slow and not integration" tests/unit/test_llm_gateway_coverage_guardrails.py

nice -n 19 taskpolicy -b bash backend/scripts/check_runtime_env_compose.sh
nice -n 19 taskpolicy -b backend/.venv/bin/python \
  backend/scripts/validate-backend-runtime-env.py --env dev --check-workflows
nice -n 19 taskpolicy -b backend/.venv/bin/python \
  backend/scripts/validate-backend-runtime-env.py --env prod --check-workflows
nice -n 19 taskpolicy -b backend/.venv/bin/python scripts/check_feature_flag_registry.py
nice -n 19 taskpolicy -b env BLACK_NUM_WORKERS=1 scripts/backend-python-format --check \
  backend/tests/unit/test_backend_runtime_env_validator.py \
  backend/tests/unit/test_verify_pusher_config_references.py
```

Local logs: `sol-ci-fixes-2-unit.log`, `sol-ci-fixes-2-journal-rerun.log`, `sol-ci-fixes-2-guardrails.log`, `sol-ci-fixes-2-inventory-fast.log`, and `sol-ci-fixes-2-static.log` in `.agent-brief/`.

**Final local results:** 473 passing tests across the five files (447 fast assertions across the first four files, 24 fast inventory tests, and two slow inventory guardrails), using the successful journal rerun. All static checks above and `git diff --check` pass. The pinned formatter leaves both changed Python files unchanged.

No full preflight, workflow edits, cloud commands, production API requests, pushes, secrets, or new UID literals. Local verification does not establish remote CI or deployment status.
