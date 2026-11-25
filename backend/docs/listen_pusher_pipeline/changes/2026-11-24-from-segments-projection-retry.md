# Client processing projection on keyed retries

The [keyed from-segments retry note](./2026-11-24-from-segments-keyed-retry.md) describes re-admitting the retained row after a budget cut. This correction keeps the client-authored `client_processing` projection display-only on that resume path: strip any stored projection before validating the row, validate a retry-supplied projection against the submitted transcript for the existing rejection logging, then discard it because processing reuses the first attempt's stored transcript. The coordinator receives no projection, generic persistence does not overwrite the stored display field, and admission plus transcript reuse remain unchanged. Completed idempotency hits retain the existing digest-checked late-bind path.

This prevents stale or schema-incompatible display data from blocking resumed admission and prevents a retry projection from entering processing state. It adds no Firestore reads, indexes, collections, or writes and changes no wire contract.

## Rollout and verification

No flag or migration is required. The correction is part of [PR #26222](https://github.com/BasedHardware/omi/pull/26222) and follows the existing release train; it is not a separate production rollout. Rollback is to revert that PR. The targeted trust-boundary and keyed-retry tests run on M1 through `bin/omi-heavy`; current CI evidence is at [the PR checks page](https://github.com/BasedHardware/omi/pull/26222/checks).
