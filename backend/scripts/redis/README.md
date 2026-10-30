# Redis capacity census runbook

Read-only tooling that produces the capacity numbers behind backend memory
decisions on the prod Redis Cloud Essentials 12GB box. Run it monthly or
before/after any Redis-facing change; compare against the previous census
before claiming growth or savings.

## Usage

Credentials come from env (`REDIS_DB_HOST`/`REDIS_DB_PORT`/`REDIS_DB_PASSWORD`)
or hostctl secrets `omi-redis-db-*` (present on David's Macs).

```bash
cd backend
.venv/bin/python scripts/redis/census.py          # INFO memory + DBSIZE
.venv/bin/python scripts/redis/census.py --tally  # full-keyspace prefix key counts
.venv/bin/python scripts/redis/census.py --deep   # per-prefix bytes + max key (slow: 1 op/key)
```

The Lua scripts in this directory are `#!lua flags=allow-oom` so they run even
at `maxmemory` (EVAL is deny-oom flagged by default on Redis 7). They are
strictly read-only (SCAN, MEMORY USAGE, PTTL, TIME).

## Reading the output

- `--tally` gives key counts per prefix. Key counts != bytes: on 2026-10-15
  `translate:v2` was 37% of keys but ~4% of bytes.
- `--deep` gives per-prefix GB and the largest single key seen per prefix.
  Uniform `MEMORY USAGE` sampling explains only ~40-70% of `used_memory`; the
  remainder is allocator overhead + fat tails. Do not treat the gap as a
  "hidden writer".
- Watch for growth **rate** (measure ≥90s apart; short windows wobble ±20MB/min)
  and for new prefixes or rising no-TTL shares.

## Historical reference points

- 2026-10-15 16:00 (incident): 15.26M keys, 12.86GB (99.8%), OOM writes ~60min.
  Recovered organically via bulk TTL expiry — see
  `omi-knowledge:incidents/2026-10-15-prod-redis-oom/README.md`.
- 2026-10-15 23:30 (post-incident + expiry wave): 8.49M keys, 10.36GB (80.6%).
  Largest: sync_job 1.23GB, users 1.18GB (protected), cache 0.89GB.
