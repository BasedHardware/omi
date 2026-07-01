# Canonical legacy memory backfill (single user)

**Purpose:** Migrate a whitelisted user's active legacy `memories` rows into canonical `memory_items` without mutating or deleting legacy data.

For first-user dogfood, use the **bucketed** strategy. It inventories the full legacy corpus, then lets an operator apply one reviewed bucket at a time. The older bulk strategy still exists for compatibility, but it copies every active legacy row as `long_term` and should not be used for noisy legacy accounts.

**Library:** `utils.memory.legacy_backfill.backfill_user_bucketed`
**CLI:** `backend/scripts/backfill_legacy_memories.py`

## Safety contract

- **Read-only on legacy** — uses `get_non_filtered_memories` only; never calls legacy mutators.
- **Write-only on canonical** — applies via `apply_long_term_patch_firestore`.
- **Cohort gate** — backfill runs only when `uid` is in `CANONICAL_MEMORY_USERS` (or `--allow-admin-override`).
- **Idempotent** — backfill ids are `mem_` + hash(`uid`, `legacy_memory_id`); apply path honors `idempotency_key`.
- **Both-store dedup** — if live extraction already wrote the same fact (`extraction_memory_id` from `conversation_id` + `content`), backfill skips that row.
- **Bucketed dogfood** — bucketed runs preserve legacy timestamps, write selected profile-like rows as either `long_term` or required-promotion `short_term`, and hold noisy/sensitive rows.
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

### 1. Bucket inventory dry run (no writes)

```bash
cd backend
python scripts/backfill_legacy_memories.py --uid YOUR_UID --strategy bucketed --dry-run
```

Expect:

- `dry_run: true`
- `source_count` = active legacy rows with non-empty content
- `bucket_counts` = full inventory by bucket
- `bucket_samples` = small row samples for review
- `written_count: 0`
- `cohort_gated: false` (if gated, add uid to whitelist first)

Buckets:

| Bucket | Writes? | Destination | Intended use |
|--------|---------|-------------|--------------|
| `manual_required_promotion` | Yes | `short_term` with `promotion.required=true` | User/manual memories that should flow through normal promotion |
| `profile_required_promotion` | Yes | `short_term` with `promotion.required=true` | Profile-like legacy rows that need consolidation/promotion review |
| `reviewed_long_term` | Yes | `long_term` | Profile-like rows already explicitly user-reviewed |
| `archive_review` | No | None | Non-obvious rows for later manual/archive policy review |
| `hold_noise` | No | None | Downloads inventory, focused-app activity, imperative task fragments, empty/low-signal rows |
| `hold_sensitive` | No | None | Credential/token/password/secret-like rows |

### 2. Bucket dry run (no writes)

Dry-run the first bucket before writing it:

```bash
python scripts/backfill_legacy_memories.py --uid YOUR_UID --strategy bucketed --bucket manual_required_promotion --dry-run
```

Expect `intended_count` to match the reviewed bucket size minus existing canonical destinations.

### 3. Apply one bucket

Apply only after reviewing the bucket inventory and samples:

```bash
python scripts/backfill_legacy_memories.py --uid YOUR_UID --strategy bucketed --bucket manual_required_promotion
```

Repeat bucket dry-run, review, and apply for the next approved writable bucket. Do not apply hold buckets; the script reports them as non-writable.

Monitor JSON output after each applied bucket:

| Field | Success signal |
|-------|----------------|
| `completed` | `true` |
| `verified` | `true` for the selected bucket |
| `selected_bucket` | The bucket you intended to apply |
| `written_count` + `skipped_*` | Should account for the selected bucket rows |
| `vector_sync_failures` | `0` |
| `errors` | `[]` |

Re-run is safe: already-present and both-store-duplicate rows are skipped.

### 4. Verification queries

**Firestore (console or script):**

- Legacy unchanged: `users/{uid}/memories/*` — same doc count as before; no `invalid_at` changes from backfill.
- Canonical items: `users/{uid}/memory_items/*` — one active processed item per applied writable-bucket row (either backfill id or live-write id).
- Required-promotion rows: selected `manual_required_promotion` / `profile_required_promotion` rows are `tier=short_term`, have `promotion.required=true`, `promotion.status=pending`, old `captured_at`, and future `expires_at`.
- Reviewed long-term rows: selected `reviewed_long_term` rows are `tier=long_term` with old `captured_at`.
- Control state: `users/{uid}/memory_control/state` exists after a real run.

**Python reconcile (same logic as the library):**

```python
from utils.memory.legacy_backfill import backfill_user_bucketed

report = backfill_user_bucketed("YOUR_UID", bucket="manual_required_promotion", dry_run=True)
assert report.errors == []
```

**Read path smoke:** with uid still whitelisted, `GET /v3/memories` (or desktop Memories tab) should show long-term facts without duplicates.

## Rollback (kill-switch)

1. Remove uid from `CANONICAL_MEMORY_USERS` in `memory_system.py` and redeploy.
2. User immediately reads legacy `memories` again.
3. Canonical `memory_items` written during backfill are **not** deleted and **not** copied back to legacy — accepted staleness per rollout policy.
4. Re-whitelisting resumes canonical reads; backfill re-run is idempotent.

## When *not* to proceed

- `cohort_gated: true` — fix whitelist before real run.
- `verified: false` after a completed bucket run — inspect `discrepancy` and missing selected-bucket items.
- `errors` non-empty — fix root cause; re-run the same bucket. Bucketed writes are deterministic and idempotent.

## Operational notes

- **Provenance:** bucketed rows preserve legacy `created_at` as `captured_at` and legacy `updated_at` as `updated_at`. Short-term bucketed rows set `expires_at` to migration time + 30 days so promotion can process them.
- **Bulk compatibility:** `backfill_user` and `--strategy bulk-long-term` still use the legacy id-set checkpoint. Bucketed dogfood does not use that checkpoint; re-runs reconcile by deterministic canonical ids.
- **Vectors:** backfill syncs Pinecone via `sync_canonical_memory_vector`; vector sync failures increment `vector_sync_failures` but does not roll back Firestore writes.

## Short-term promotion (canonical cohort)

Scheduled maintenance (`canonical_short_term_maintenance_cron`) promotes short-term items via the same vector sync path. After a promotion run, check `promotion.vector_sync_failures` on the maintenance report (and `vector_sync_failures_total` on the cron summary). Non-zero values mean Firestore tier flips succeeded but Pinecone metadata may still show `memory_layer=short_term` — investigate vector sync logs; re-run promotion does not re-upsert already-long-term items, so repair may require a targeted vector re-sync.
