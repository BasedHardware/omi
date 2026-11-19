# Seal repair age metrics ignore invalid clocks

The repair coordinator excludes nonpositive source timestamps from
`oldest_unsealed_seconds`, `oldest_seal_age_seconds` and per-row seal ages,
while retaining the same selected rows, ordering, cursors and repair attempts.
Its summary reports `invalid_clock_rows` among attempted rows; the matching
log-based count definition is in `backend/deploy/record-seal-repair/log-metrics.json`.
Previously ineligible malformed or nonfinite job clocks remain ineligible.

The continuous worker independently samples conversation `finished_at`.
Its `omi_record_seal_invalid_clock_rows` gauge counts invalid clocks in the
last fully completed backlog pass, including claimed and backed-off debt.
Invalid clocks contribute to backlog and candidate selection, but not oldest
age or the successful-attempt age histogram. An entirely invalid sample has
age zero and a nonzero invalid-clock count. No flags or rollout settings change.

Regression coverage: `backend/tests/unit/test_record_seal_cluster_repair.py`,
`backend/tests/unit/test_record_seal_worker.py` and
`backend/tests/unit/test_record_seal_cluster_repair_deploy.py`.
