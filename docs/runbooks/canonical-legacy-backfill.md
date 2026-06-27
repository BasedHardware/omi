# Canonical legacy memory backfill (single user)

**Purpose:** Copy a whitelisted user's active legacy `memories` rows into canonical `memory_items` (`layer=long_term`) without mutating or deleting legacy data.

**Library:** `utils.memory.legacy_backfill.backfill_user`
**CLI:** `backend/scripts/backfill_legacy_memories.py`

## Safety contract

- **Read-only on legacy** — uses `get_non_filtered_memories` only; never calls legacy mutators.
- **Write-only on canonical** — applies via `apply_long_term_patch_firestore`.
- **Cohort gate** — backfill runs only when `uid` is in `CANONICAL_MEMORY_USERS` (or `--allow-admin-override`).
- **Idempotent** — backfill ids are `mem_` + hash(`uid`, `legacy_memory_id`); apply path honors `idempotency_key`.
- **Both-store dedup** — if live extraction already wrote the same fact (`extraction_memory_id` from `conversation_id` + `content`), backfill skips that row.
- **Reversible** — remove `uid` from `CANONICAL_MEMORY_USERS` and redeploy to return them to legacy reads; legacy rows remain intact.

## Preconditions

1. **Target uid chosen** — first production dogfood user only; no bulk/cron.
2. **Backend env** — `GOOGLE_APPLICATION_CREDENTIALS` (or emulator) points at the intended project.
3. **Cohort whitelist** — add uid to `CANONICAL_MEMORY_USERS` in `backend/utils/memory/memory_system.py` **before** backfill, then deploy:
   ```python
   CANONICAL_MEMORY_USERS: frozenset[str] = frozenset({
       "your-firebase-uid",
   })
   ```
4. **Control state** — `users/{uid}/memory_control/state` is created automatically on first real run (dry-run does not create it).

## Procedure

### 1. Dry run (no writes)

```bash
cd backend
python scripts/backfill_legacy_memories.py --uid YOUR_UID --dry-run
```

Expect:

- `dry_run: true`
- `source_count` = active legacy rows with non-empty content
- `intended_count` = rows still to copy (respects resume checkpoint)
- `written_count: 0`
- `cohort_gated: false` (if gated, add uid to whitelist first)

### 2. Real run

```bash
python scripts/backfill_legacy_memories.py --uid YOUR_UID
```

Monitor JSON output:

| Field | Success signal |
|-------|----------------|
| `completed` | `true` |
| `verified` | `true` (`source_count == destination_count`) |
| `written_count` + `skipped_*` | Should account for all `source_count` rows |
| `errors` | `[]` |

Re-run is safe: already-present and both-store-duplicate rows are skipped.

### 3. Verification queries

**Firestore (console or script):**

- Legacy unchanged: `users/{uid}/memories/*` — same doc count as before; no `invalid_at` changes from backfill.
- Canonical items: `users/{uid}/memory_items/*` — one active processed item per legacy row (either backfill id or live-write id).
- Checkpoint: `users/{uid}/memory_control/state` — `legacy_backfill_completed_at` set when `completed=true`.

**Python reconcile (same logic as the library):**

```python
from utils.memory.legacy_backfill import backfill_user

report = backfill_user("YOUR_UID", dry_run=True)
assert report.verified is True
```

**Read path smoke:** with uid still whitelisted, `GET /v3/memories` (or desktop Memories tab) should show long-term facts without duplicates.

## Rollback (kill-switch)

1. Remove uid from `CANONICAL_MEMORY_USERS` in `memory_system.py` and redeploy.
2. User immediately reads legacy `memories` again.
3. Canonical `memory_items` written during backfill are **not** deleted and **not** copied back to legacy — accepted staleness per rollout policy.
4. Re-whitelisting resumes canonical reads; backfill re-run is idempotent.

## When *not* to proceed

- `cohort_gated: true` — fix whitelist before real run.
- `verified: false` after a completed run — inspect `discrepancy`, missing items, or partial checkpoint (`legacy_backfill_processed_count`).
- `errors` non-empty — fix root cause; resume from checkpoint (`resume=True` default).

## Operational notes

- **Provenance:** backfilled rows set `user_asserted=False`, `visibility=private`, `captured_at=now` (legacy `created_at` is not copied).
- **Fingerprint:** checkpoint fingerprint is legacy **id-set only**; editing legacy content under the same id does not re-copy (staleness, not data loss).
- **Vectors:** backfill syncs Pinecone via `sync_canonical_memory_vector`; vector sync failures increment `vector_sync_failures` but does not roll back Firestore writes.

## Short-term promotion (canonical cohort)

Scheduled maintenance (`canonical_short_term_maintenance_cron`) promotes short-term items via the same vector sync path. After a promotion run, check `promotion.vector_sync_failures` on the maintenance report (and `vector_sync_failures_total` on the cron summary). Non-zero values mean Firestore tier flips succeeded but Pinecone metadata may still show `memory_layer=short_term` — investigate vector sync logs; re-run promotion does not re-upsert already-long-term items, so repair may require a targeted vector re-sync.
