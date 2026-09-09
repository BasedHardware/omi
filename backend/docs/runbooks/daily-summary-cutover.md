# Daily-summary recipient selection cutover (#13210)

The hourly `notifications-job` used to read every user document with a
`time_zone` on each execution and filter `daily_summary_enabled` /
`daily_summary_hour_local` in Python, because both fields were absent on most
documents and their defaults (`True`, `22`) lived only in code. Selection can
now be served by Firestore, staged behind one env knob.

## Pieces

- **Write-time defaults** (`database/notifications.py`): every path that writes
  `time_zone` or a preference on the user document also fills whichever of the
  two schedule fields is absent. Present values, including `False` and hour `0`,
  are never overwritten. Invariant: a document that carries `time_zone` carries
  both schedule fields.
- **Indexed selector** `get_users_for_daily_summary_indexed`: per hour group and
  per <=30-zone chunk, `daily_summary_enabled == True AND
  daily_summary_hour_local == H AND time_zone IN chunk`. Registered as
  `DAILY_SUMMARY_RECIPIENTS_QUERY` in `database/firestore_index_registry.py`;
  the composite is generated into `firestore.indexes.json`. Timezone -> local
  hour is still evaluated from tzdata at run time, so DST needs no reconciliation.
- **Backfill** `scripts/backfill_daily_summary_schedule_fields.py`: pages
  `users` by `__name__` with a projection and writes only absent fields.
  Dry-run by default; `--apply` writes; `--start-after <uid>` resumes;
  `--limit N` for a smoke run. Idempotent.
- **Mode** `DAILY_SUMMARY_SELECTION_MODE` (read by `utils/other/notifications.py`):
  - `legacy` (code default) - the full-pass selector.
  - `shadow` - legacy result is sent; the indexed selector also runs and one
    `daily_summary_selection_shadow hour=... legacy=N indexed=M only_legacy=K
    only_indexed=J sample_only_legacy=[...] sample_only_indexed=[...]` line is
    logged per hour group. Costs one extra legacy pass per execution.
  - `indexed` - indexed selector only.
- **Run lock**: `start_cron_job` takes `notifications_job:run_lock` (Redis
  `SET NX EX`, 55 min, token compare-and-delete release). An overlapping
  Scheduler fire logs `notifications_job_run_skipped reason=overlap` and skips
  the notification section; the existing checkpoint resumes the tail. A Redis
  error on acquire fails open and records the `daily_summary` fallback counter.

## Cutover order

1. Deploy the backend so the write-time defaults are live. The cron is unchanged.
2. Run the backfill against prod once: dry-run first and read `missing_enabled`
   / `missing_hour`, then `--apply`. Expect roughly one write per user document.
3. Set `DAILY_SUMMARY_SELECTION_MODE=shadow` on `notifications-job` in the
   runtime-env overlay, deploy, and read one execution's shadow lines.
   `only_legacy` must be `0` for every hour; a non-zero value names documents
   the backfill or funnel missed.
4. Set `DAILY_SUMMARY_SELECTION_MODE=indexed`, deploy. Confirm `users`
   `read_ops_count` drops from one full pass per execution to recipients only.
5. Follow-ups: remove the legacy selector; the 08:00 morning push
   (`_get_users_in_timezones`) still reads ~1/24th of users once a day.
