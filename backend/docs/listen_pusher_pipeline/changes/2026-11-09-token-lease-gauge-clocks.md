# Repair age gauge excludes invalid enqueue clocks

Lead decision 6 follows the local production readout
`data/run-2026-11-08-pipeline-refactor/findings-24953-gate.md` in the Omi
workspace. Zero enqueue clocks produce a horizon-epoch age, masking the
oldest valid sample in the token-lease backlog warning.

Discovery now optionally collects metric ages where the enqueue clock is
known. `MIN_METRIC_ENQUEUED_AT` is a telemetry-only floor of 2020-01-01 UTC,
before the record pipeline existed. Older/non-positive clocks do not
contribute to the gauge; future clocks already fail the existing discovery
minimum-age check. With no valid samples the gauge is zero, indicating absence
of valid age samples in this bounded pass. Repair row counts still include
invalid-clock jobs. The conversation
discovery samples still contribute as before, excluding duplicate job paths.

Returned rows, their ages, ordering, cursors, saturation and repair attempts
are unchanged, including jobs with zero or implausible clocks. This does not
implement the discovery correction owned by cl2-fixnow or Part B. The active
repair CronJob remains the producer, the idle seal worker stays disabled,
and no alert expression or threshold changes.

Unit regressions cover mixed valid/zero pages, all-zero pages, other
implausible clocks and the inclusive floor, in both discovery orders. They
compare the complete discovery result with and without metric collection and
exercise the coordinator's actual gauge publication. Real PromQL backtests
add a zero-age page that stays quiet, correction of a legacy pinned series to
zero that clears the warning, and a legacy pinned epoch constant that still
fires: a positive constant is indistinguishable from a legitimate flat backlog
in the warning, so validation belongs at the producer.

Mode remains off by default. Production signal-gap measurement, the 48-hour
shadow soak and ramp acceptance remain pending. No production/GCP access is
used for this correction.

## Validation

The correction commit is `684e6e010d57312a635068aaeb27c8da151b71c5`, rebased
onto `95aa2b499eb91d885097feeb42f4c6deedea6eeb`. Registry conflict resolution
preserves every main entry exactly and adds only the five existing lease
declarations. The four gauge code/test files are byte-identical across the
rebase. A static AST comparison also confirms discovery is unchanged except
for the optional output argument and metric sample collection.

The first focused run passed 392 tests across eight suites and all seven real
PromQL scenarios. Its full preflight stopped at the synthetic-merge line-count
check because shared `origin/main` advanced during the run and conflicted in
the feature-flag registry files (exit 2, 391.85 seconds). The Firestore guard
set passed before that stop. The subsequent rebase resolves that metadata
conflict without changing the gauge implementation or unrelated registry
entries; focused checks and the complete preflight are rerun afterwards.

All heavy validation uses:

```sh
/Users/dazheng/workspace/omi/bin/omi-heavy run --wait 7200 -- python3 /Volumes/Ephemeral/scratch/tokenlease-gauge-validate.py
```

That launcher runs each unit suite in a fresh interpreter from `backend/`:

```sh
.venv/bin/python -m pytest -q --tb=short tests/unit/test_record_token_lease.py
.venv/bin/python -m pytest -q --tb=short tests/unit/test_record_seal_cluster_repair.py
.venv/bin/python -m pytest -q --tb=short tests/unit/test_record_token_lease_deploy.py
.venv/bin/python -m pytest -q --tb=short tests/unit/test_record_seal_cluster_repair_deploy.py
.venv/bin/python -m pytest -q --tb=short tests/unit/test_monitoring_alert_backtest.py
.venv/bin/python -m pytest -q --tb=short tests/unit/test_monitoring_notification_contract.py
.venv/bin/python -m pytest -q --tb=short tests/unit/test_monitoring_alert_rule_contract.py
.venv/bin/python -m pytest -q --tb=short tests/unit/test_monitoring_telemetry_contract.py
.venv/bin/python tests/promql/record_token_lease.py --promtool /Volumes/Ephemeral/scratch/tokenlease-promtool/promtool
# Repository root, OMI_PR_BODY_FILE=.agent-brief/tokenlease-pr-body.md:
make preflight
```

It unsets GOOGLE_APPLICATION_CREDENTIALS, every CLOUDSDK_* variable and
service-account/auth-file bindings, and gives subprocesses private HOME/config
and temporary directories to prevent ADC fallback. GCP tier: none. Logs:
`/Volumes/Ephemeral/scratch/tokenlease-gauge-validation.log`; command exit
codes and timing: `/Volumes/Ephemeral/scratch/tokenlease-gauge-results.json`.

Final post-rebase verification, recorded 2026-11-09T08:08:52.609130+00:00:

| Unit suite | Passed |
| --- | ---: |
| `test_record_token_lease.py` | 80 |
| `test_record_seal_cluster_repair.py` | 129 |
| `test_record_token_lease_deploy.py` | 9 |
| `test_record_seal_cluster_repair_deploy.py` | 10 |
| `test_monitoring_alert_backtest.py` | 29 |
| `test_monitoring_notification_contract.py` | 8 |
| `test_monitoring_alert_rule_contract.py` | 75 |
| `test_monitoring_telemetry_contract.py` | 52 |
| **Total** | **392** |

- Real PromQL engine: **7 scenarios passed**, including all-zero, legacy pinned constant, and correction of that constant to zero.
- Expanded `make preflight`: **56/56 passed**, exit **0**, 2556.86 seconds (preflight reports 2554.07 seconds internally).
- No new waiver, relaxed assertion or xfail. Existing repository exceptions remain unchanged.
- Local validation only. No push, PR, deployment or GCP access. The production soak and ramp remain pending.

## Files changed for decision 6

- `backend/utils/batch_pipeline/record_seal_cluster_repair.py`
- `backend/tests/unit/test_record_seal_cluster_repair.py`
- `backend/tests/support/firestore_batch_pipeline_drivers.py`
- `backend/tests/promql/record_token_lease.py`
- `backend/docs/listen_pusher_pipeline/changes/2026-11-09-token-lease-gauge-clocks.md`
