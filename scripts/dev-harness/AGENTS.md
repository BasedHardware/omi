# Dev harness contracts

Inherits [repository rules](../../AGENTS.md). Before changing mobile sessions,
read [MOBILE_SESSIONS.md](MOBILE_SESSIONS.md), [LIVE_SESSIONS.md](LIVE_SESSIONS.md)
and [PENDING_CONTRACTS.md](PENDING_CONTRACTS.md). Receipt freeze policy lives in
[contracts/session](../../contracts/session/README.md).

Run `bash scripts/dev-harness/run-tests.sh`, the relevant `make mobile-verify`
selection, and `make preflight`. Tests use injected processes/clock/device
adapters and must never boot hardware or contact production. Do not weaken
spine tests: builder edits are limited to removing pending-marker lines.

V1 has a compiling CLI skeleton only. Keep ordinary session and hermetic-fast
behavior unchanged while implementing explicit live operations. Missing live
support exits 2; a requested live run must never silently fall back to cold.
