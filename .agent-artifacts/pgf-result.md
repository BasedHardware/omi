# C1 implementation result

Local branch: `lane/pgf-c1`. Worktree: `/Volumes/Ephemeral/scratch/worktrees/omi/omi-lane-pgf-c1-upstream-keep-clean`. No push, PR creation, provisioning, deployment, production API or production data access. GCP tier: **none**.

**Status:** the runtime fixture fix is complete and committed. Acceptance remains **blocked** on two additional out-of-scope admission metadata changes; neither patch was applied without authorization.

C1 supplies create-only, envelope-encrypted object-lake storage and Firestore/KMS space-key primitives with zero product callers. Config, lifecycle/retention policy, inert runtime/Helm bindings, offline admission validation and the unexecuted provisioning runbook ship together. The lead authorized and committed the four fixture/scanner/snapshot/dead-code scope exceptions before this round.

Historical C1 verification receipts remain in `pgf-verification.jsonl` and the linked `pgf-*.log` files. [Historical C1 report reconstructed from its original renderer and receipts](pgf-c1-result-before-r1.md) preserves the earlier blocked results; its old scope-exception status is superseded below. Rebase introduced M9's tracked report at this same generic path; that upstream report remains [in the pinned main tree](https://github.com/BasedHardware/omi/blob/876abc7312f28ae02d7b92c5c5034e5ba74303df/.agent-artifacts/pgf-result.md). This requested path now reports C1.

## Fix round 1

### Rebase and preservation

- Saved original branch tip `4a4f1b71d34b` as local branch `pgf-c1-before-fix-r1`.
- Fetched `origin/main` and rebased onto `876abc7312f28ae02d7b92c5c5034e5ba74303df`. All seven commits replayed without conflicts. The scope-exception commit became `3abf8596cb1c`.
- Ran `backend/.venv/bin/python backend/deploy/compose_runtime_env.py` and `backend/.venv/bin/python scripts/render_feature_flag_registry.py`; both outputs already match their sources (no diff). No generated output was hand-merged.
- Temporarily stashed only the two existing app edits for Git's clean-index requirement, restored them after rebase, and compared both the patch and file hashes. They are unchanged and remain uncommitted. SHA-256: analysis options `585e4fec57ff03a99bf6654e5f370e4eb49d9a4c55140089fbef37c883bb05f7`; lock `067a184bf86123668abe3fe825a74a280cff9d70335a6a2b187f1ec3fc5e52d4`.

### Root cause and correction

The fixture and validator read the **same** worktree `backend/deploy/runtime_env.yaml`; the parsed and normalized manifests agree. Regeneration is drift-free. The regression is positional: `with_object_lake_env()` prepended six entries before the leading `GOOGLE_CLOUD_PROJECT` entry, while later translation, ledger/sidecar, sync-settle and shadow helpers match only when that entry is first. Those helpers silently matched zero times. This left 17 unrelated required bindings absent, in addition to the intended gateway or secret failure.

Moved lake completion to the final return, after the anchored helpers, and removed an adjacent no-op assignment. No validator code, expected error list, secret-version assertion or negative kill-switch assertion changed.

- Before: [three failures on the lead-patched branch](pgf-r1-validator-before.log), including `test_cloud_run_state_rejects_old_secret_versions` with **18 errors instead of 1**.
- After: [the same selection](pgf-r1-validator-after.log), **3 passed / 148 deselected**. The full validator file also passes **151 tests**.
- Selection: `python -m pytest backend/tests/unit/test_backend_runtime_env_validator.py -q -k 'test_cloud_run_state_reports_missing_gateway_url or test_cloud_run_workflow_validation_uses_custom_manifest_for_runtime_env_outputs or test_cloud_run_state_rejects_old_secret_versions'` from the root, through the credential scrubber and `omi-heavy`.

### Review disposition

Two one-line runbook clarifications are applied: pin `OBJECT_LAKE_RELEASE=v1` until the lifecycle/retention contract migrates with it; C4 must durably fence deleted owners and quiesce in-flight puts before purge. The remaining review items need behavioral, integration or test work beyond a safe one-line change:

- C2/C4: durable deleted-owner write fence plus concurrent object/key resurrection coverage; C4 emulator transaction-contention/retry coverage.
- Next core test pass: reject an otherwise valid retry metadata DEK version that disagrees with the envelope header, and cover reload transport errors, unavailable/destroyed deep verification, and unsafe put identifiers. Header verification adds object IO to retry and needs an explicit tested policy.
- C2: choose and enforce per-class decompressed-size limits; retain fail-closed handling for malformed wrapped-key rows (currently unavailable/retryable, distinct from shredded).
- C2/C3: budget the deliberate key-doc authority reads (one per unwrap and two per put); optimize only while retaining cross-worker destroy semantics.
- Provisioning/C3: enforce release alignment in runtime/admission configuration before serving; the runbook pin alone is not a code guard.

### Validation

All commands use this worktree's Python 3.11 environment via `pgf-test-env.py`, which unsets `GOOGLE_APPLICATION_CREDENTIALS`, every `CLOUDSDK_*`, service-account/auth paths and inherited project bindings. Metadata discovery points at a closed loopback port; tests use demo-only project hints and loopback Redis. Heavy runs use `/Users/dazheng/workspace/omi/bin/omi-heavy run --wait 3600 -- ...`. The verification driver sets `BACKEND_PYTEST_WORKERS=4`, `BACKEND_UNIT_FILE_BUDGET_SECONDS=900`, and a process-local installed Opus loader path. No GCP credential tier was loaded.

Completed 2026-11-06T13:39:24.342868+00:00. Source fix commit: `b1404559e9da566e761ba208f70add244f74249d`; the final handoff commit changes only this report. This is local verification, not GitHub CI or deployed/provider acceptance.

| Command | Exit | Outcome | Evidence |
|---|---:|---|---|
| Four focused lake files, `python -m pytest ... -q` (backend/) | 0 | 88 passed | [focused](pgf-r1-focused.log) |
| `python -m pytest tests/unit/test_backend_runtime_env_validator.py -q` (backend/) | 0 | 151 passed | [runtime validator](pgf-r1-backend_runtime_env_validator.log) |
| `python -m pytest tests/unit/test_retention_contract.py -q` (backend/) | 0 | 26 passed | [retention](pgf-r1-retention_contract.log) |
| `python -m pytest tests/unit/test_verify_pusher_config_references.py -q` (backend/) | 0 | 28 passed | [pusher](pgf-r1-verify_pusher_config_references.log) |
| `python -m pytest tests/unit/test_sync_staging_lifecycle_guard.py -q` (backend/) | 0 | 27 passed | [lifecycle](pgf-r1-sync_staging_lifecycle_guard.log) |
| `python .github/scripts/test_check_dead_code.py` (root) | 0 | 16 passed | [dead-code self-tests](pgf-r1-dead-code-tests.log) |
| `bash backend/scripts/pre-deploy-check.sh` (root) | 0 | 456 pytest + 36 unittest tests passed; all source validators passed | [pre-deploy](pgf-r1-pre-deploy.log) |
| Required `make preflight` (root, exact env below) | 2 | Stopped at feature-flag registry; earlier checks including dead-code, runtime-image closure, async and Firestore passed | [make](pgf-r1-make-preflight.log) |
| First manifest continuation via explicit `--check-id` selections | 1 | Exposed the deployment classification omission | [continuation](pgf-r1-remaining-manifest-checks.log) |
| Final manifest continuation via explicit `--check-id` selections | 0 | All remaining 29 checks passed | [continuation 2](pgf-r1-remaining-manifest-checks-r2.log) |
| Draft `scripts/pr-preflight --pr-body-file ... --metadata-only` | 0 | All four checks passed | [final metadata](pgf-r1-pr-metadata-final.log) |

Repository preflight command executed through `omi-heavy` after the credential scrubber:

```sh
OMI_PR_BODY_FILE="$PWD/.agent-artifacts/pgf-pr-body.md" BACKEND_UNIT_FILE_BUDGET_SECONDS=900 BACKEND_PYTEST_WORKERS=4 make preflight
```

The first-failure runner cancelled unrun guards. Those guards were then executed with explicit manifest selections, preserving earlier passing results rather than claiming a terminal-green make run. The exact coverage assertion reports **53 selected, 51 passed, two not green**: [coverage receipt](pgf-r1-preflight-coverage.json). No test or validator assertion was weakened. Exact commands, timestamps and exit statuses are in [JSONL](pgf-r1-verification.jsonl); the [driver source](pgf-r1-verify.py) records the credential and budget settings. `git diff --check` is clean and product-import search is empty.

### Remaining scope blockers (prepared, not applied)

1. `scripts/check_feature_flag_registry.py` rejects the required lake percent declarations across `_base.yaml` plus four Helm values files. [One-line patch](pgf-feature-flag-scope-exception.patch) adds only `OBJECT_LAKE_WRITE_PERCENT` to the existing workstream-B duplicate-declaration allowlist, preserving its **2026-11-20 expiry**. The duplicate sources must be consolidated before that date. The actual source guard remains red. A disposable checker copy with exactly this one-line change passes: [candidate log](pgf-r1-feature-flag-candidate.log).
2. `config/deployment-setting-classification.json` lacks classification for the six lake deployment bindings. [Six-line patch](pgf-secret-classification-scope-exception.patch) adds them to `kinds.config`: the bucket and KMS resource identifier are configuration, not secret payloads. The actual source guard remains red. The unchanged checker passes using the proposed JSON via its `--policy` option: [candidate log](pgf-r1-secret-classification-candidate.log).

Both patches pass `git apply --check`. Both owning files are outside brief section 9 and the four scope exceptions the lead already authorized. Additional authorization was requested asynchronously in chat; neither was assumed. Candidate checks validate the proposed changes only and do **not** clear the branch's full preflight. Next: integration lead approves/applies these patches, then reruns full preflight. No provisioning, flag expansion, runtime apply or push is authorized by this handoff.


### Draft PR body

The refreshed ready-to-paste draft is [pgf-pr-body.md](pgf-pr-body.md). It includes current passing checks, the two remaining gate blockers, authorized scope exceptions, ramp ownership and review follow-ups.

### Outcome record and cleanup

Recorded on [the ANX C1 card](https://anx.scalingforever.com/o/david-zhang/w/omi/r/card:pg-foundation-c1-encrypted-object-lake), note `event:3337fd31-980a-4c00-947b-56ed2e20ed0f`, using the authorized [anx-participant skill](/Users/dazheng/.agents/skills/anx-participant/SKILL.md). The card remains blocked on the two scope exceptions; no merge, push or deployment is claimed.

All validation commands have reached terminal states. The app patch is still identical to the pre-rebase copy; the temporary stash created for rebase was removed after verification. The local `pgf-c1-before-fix-r1` branch remains as the requested operation's rollback reference. The task heartbeat is stopped after the final commit and recorded in `pgf-r1-cleanup.json`. No servers, emulators or watchers were started.
