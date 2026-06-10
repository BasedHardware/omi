# Mixpanel → archive migration tooling

One-shot operational scripts for exporting raw Mixpanel events as gzipped
JSONL chunks. Output is suitable for handoff to PostHog managed migration
(via S3 / GCS interop) or for cold-storage of the historical Mixpanel record
once the project is decommissioned.

This directory does not get imported by any service; it exists for
reproducibility and audit trail.

---

## `mixpanel_export.sh`

Streams `data.mixpanel.com/api/2.0/export` one UTC day at a time, writes each
day to `<out>/chunks/events-YYYY-MM-DD.jsonl.gz`, paces requests under the
documented 60 queries/hour rate limit, and is safe to interrupt and resume.

### Required env

| Var | Value |
|---|---|
| `MP_SERVICE_USER` | Mixpanel service account username (`<name>.<rand>.mp-service-account`) |
| `MP_SERVICE_SECRET` | Service account secret (shown once at creation) |
| `MP_PROJECT_ID` | Project id — `3314908` for Based Hardware |

Service account is created at **Mixpanel → Organization Settings → Service
Accounts → New**, with **Consumer** role on the target project. Read-only is
sufficient for `/export`.

### Optional env

| Var | Default | Notes |
|---|---|---|
| `MP_START` | `2024-03-01` | First UTC day, inclusive |
| `MP_END` | yesterday UTC | Last UTC day, inclusive |
| `MP_OUT` | `$HOME/mp-export` | Output directory; persistent disk |
| `MP_GCS_BUCKET` | unset | If set, `gsutil cp` each chunk to `gs://<bucket>/mixpanel/<project>/` after it lands |
| `MP_MIN_DISK_GB` | `20` | Refuse to start if free space is below this |
| `MP_PACE_SECONDS` | `65` | Target cycle time per request (≈55 req/hr at 65s) |

### Layout produced

```
$MP_OUT/
├── chunks/events-YYYY-MM-DD.jsonl.gz   one file per UTC day; 0-byte file = empty day
├── manifest.jsonl                       append-only log: {date, bytes, sha256, lines, ...}
├── failures.jsonl                       days that exhausted 5 retries; auto-retried on next run
├── run.log                              full timestamped log
└── .lock                                flock guard against concurrent invocations
```

### Resume semantics

Source of truth is the disk, not the manifest. A day is "done" iff its
gzip file exists and either:

* is 0 bytes (sentinel for legitimately empty days), or
* passes `gzip -t` integrity check.

Re-running the script:

1. Acquires the flock — refuses to start if another instance holds it.
2. Iterates `[MP_START, MP_END]` and skips days that pass `is_day_done`.
3. Re-fetches everything else, including any `failures.jsonl` entries from
   prior runs (they are not "done" on disk, so they get picked up
   automatically).

This is robust against:

* Ctrl+C / `kill` / OOM / VM reboot mid-stream — the in-flight day's `.tmp`
  is discarded; final file appears only after `mv`.
* Crash between `mv` and manifest append — file is "done" on disk, but
  manifest is missing the entry. Next run sees the file and skips correctly;
  manifest gets a coverage gap (acceptable, run.log is the audit trail).
* Truncated / corrupted final files — `gzip -t` catches them, day is
  redownloaded.

### Failure handling

| HTTP / signal | Action |
|---|---|
| `200` non-empty | Save chunk, append manifest entry, advance |
| `200` empty body | Save 0-byte sentinel, manifest entry with `empty=true` |
| `429` | Sleep with exponential backoff, retry same day, does **not** count against 5-attempt budget |
| `5xx`, timeout, connection reset | Exponential backoff (60s, 120s, 240s, 480s, 960s), max 5 attempts |
| `401`, `403` | Hard abort (`exit 2`) — creds are bad, no point continuing |
| Disk full / `gzip` error | Per-day failure, retried; if persistent the run fails loudly |

Days that exhaust retries are logged to `failures.jsonl` and the run continues
to the next day. Re-running the script picks them up automatically.

### Running it

Inside a named tmux session so it survives SSH disconnects:

```bash
export MP_SERVICE_USER='posthog-migration.xxx.mp-service-account'
export MP_SERVICE_SECRET='...'
export MP_PROJECT_ID=3314908
# optionally: export MP_GCS_BUCKET=omi-mixpanel-archive

tmux new -d -s mp-export 'bash scripts/migration/mixpanel_export.sh'
```

Read-only attach to watch progress:

```bash
tmux attach -r -t mp-export
```

Or check progress without attaching:

```bash
wc -l "$HOME/mp-export/manifest.jsonl"        # days completed
tail -n 5 "$HOME/mp-export/run.log"            # recent activity
ls "$HOME/mp-export/chunks" | wc -l            # files on disk
du -sh "$HOME/mp-export/chunks"                # disk usage
```

### Wallclock estimate

For Mar 2024 → today (≈793 days) at the default 65s pace: **~14h** unattended.
Failures and retries extend it. Resume on next run is exact — no work is
redone.

### Verification after the run

```bash
# Total events imported per manifest:
jq -s 'map(.lines // 0) | add' "$HOME/mp-export/manifest.jsonl"

# Compare against Mixpanel insights total for the same window:
# (run from Mixpanel UI or MCP Run-Query / $any_event total math)

# Spot-check a random chunk:
zcat "$HOME/mp-export/chunks/events-2026-04-01.jsonl.gz" | wc -l
zcat "$HOME/mp-export/chunks/events-2026-04-01.jsonl.gz" | head -1 | jq

# Find missing days (gaps in coverage):
ls "$HOME/mp-export/chunks" | sed 's/events-//;s/.jsonl.gz//' | sort > /tmp/got
seq -f '%g' 0 792 | while read i; do date -u -d "2024-03-01 + $i day" +%F; done > /tmp/want
diff /tmp/want /tmp/got | head
```
