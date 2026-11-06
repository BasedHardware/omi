# Speaker wake outage recovery — 2026-11-05

Local synthetic validation only. No production access, account data or GCP tier
was used. The parent still owns the real-data acceptance gate and publication.

Fix: `d836fba1cdf809d493dc3e29bdf2c33d1d3f137f`.
Fetched main: `feffb957c54a1cd6f62296e31b364036f5207940` (unchanged and already
an ancestor of the fix). No rebase or conflict resolution was needed this round.
All prior GMP alternatives remain present; this change adds the rollout histograms.
No amend, push or PR was performed.

## Findings and policy

| Finding | Change and evidence |
| --- | --- |
| Claim/settlement outage triggers unlimited queue retries | Both task edges return HTTP 200 / `deferred_custody` for typed transient custody failures, without another write, immediate wake or terminal counter. The existing dedicated-row sweeper rearms pending rows or expired leases after recovery. A failed uncommitted claim consumes zero attempts; a committed claim with a lost reply retains its attempt. Four claims remain the cap. |
| Lost terminal settlement reply / duplicate wake | A content-free terminal reporting receipt remains indexed for repair. Recovery reports the committed result without repeating inference. A CAS fence admits one terminal reporter; duplicate wakes are stale. Custody deferrals are outside terminal counts. |
| Nested HTTPX TLS errors incorrectly defer | A cycle-safe traversal of explicit causes and contexts vetoes retry for nested SSL errors before transport classification. The real HTTP adapter makes one call for the wrapped TLS fixture. |
| HTTP status transients become terminal | HTTP 408, 429 and every 5xx status are transient. The adapter retries once immediately; persistent failures enter the existing bounded speaker-only outbox. Other 4xx remain terminal. Real adapter tests cover initial and retry paths. |
| Sync GMP drops rollout histograms | Keep all `_bucket`, `_sum` and `_count` series for agreement, latency and owner-delta, alongside both counters. Declare missing source-backed names separately without changing the historical observed capture. |

This retains whole-pass shared-unit refusal, authority fences, staged-artifact
retention, resource limits and flag defaults. Recovery never runs full enrichment
or learns recurring voices. There is no new queue configuration, SDK retry loop
or blocking slot admission. Prometheus reporting is fenced against duplicate
wakes; it is not transactional with a process crash after the reporting CAS. The
durable row retains the authoritative terminal outcome.

## Verification

All commands ran through `omi-heavy`, using the worktree's Python 3.11 venv.

- **1,010 tests passed**, 10 dependency deprecation warnings, across 23 focused
  files. The command is the previous [transient-custody validation](2026-11-05-speaker-final-pass-transient-custody.md#rebase-and-verification)
  command plus `tests/unit/test_batch_final_pass_outage.py`. This includes the
  maximum-size memory stress/deadline test and realistic multi-unit,
  mixed-authority replay through `reproduce()`.
- **339 fast-lane tests passed**, one slow stress test deselected, through
  `test.sh` with one worker and `BACKEND_FAST_UNIT_FAIL_SECONDS=1.00`. Selected
  files: outage, retry, transient, owner-lab, resources and lifecycle.
- New outage tests exercise actual enrichment and sync FastAPI task edges,
  claim/settlement/reporting outages, lost committed replies, all four claims,
  concurrent duplicate terminal reporters, nested TLS errors, real HTTP adapter
  statuses and all 100 possible 5xx codes. HTTP and storage are synthetic.
- Black formatted seven changed Python files; the commit hook confirmed all
  seven unchanged after formatting. `git diff --check` passed.
- Offline monitoring alert lint passed with no new failures; three existing
  inventory/alert-debt entries remain unchanged.

`make preflight` passed **all 42 selected checks** in 166.38 seconds, using local
draft metadata (no PR). Checks include runtime image source and third-party
closure, Firestore boundaries/indexes, import purity, async blockers, test
isolation, task authority and monitoring lint. The source-closure check retained
the GPU batch worker boundary and Pusher's finalizer reachability through
`process_conversation`. Existing line-count growth declarations for the earlier
retry wiring remain in the local draft; this round adds no further growth there.
