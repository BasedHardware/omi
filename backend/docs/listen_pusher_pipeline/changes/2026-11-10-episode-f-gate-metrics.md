# Variant F gate refusal and fallback attribution telemetry

Adds `omi_episode_f_gate_total{reason}` at the candidate privacy refusal branch in
`utils/episodes/f_join.py:settle`. The existing `f_no_answer` boundary counter and
all allow/deny decisions, read order and short-circuiting remain unchanged. There
is no new flag, fallback, Jev call or hold-completion behavior.

The first failing condition wins, in the existing gate order: owner, row consent
(data protection or explicit private-cloud-sync opt-in), locked/discarded,
deleted/deferred/processing-deferred, status, local pending, terminal-no-derived-effects
(`other`), client processing, local only, held, hidden, then current user consent.
Missing candidate rows use `other`; exceptions retain the existing error path.
Labels are bounded to `held`, `client_processing`, `deferred`, `local_pending`,
`local_only`, `row_consent`, `user_consent`, `locked_discarded`, `owner`, `status`,
`hidden`, and `other`. All series are primed at zero.

The shared `utils.metrics` registry exports this alongside `omi_episode_boundary_total`
on pusher's `/metrics` route, scraped by the in-cluster `pusher-metrics` job. The
metric inventory records a source declaration, not an observed production series.
The GMP query-consumer inventory is regenerated with `monitoring_gmp_shadow.py`.
Rollback is a revert; release and production measurement belong to the lead lane.

Validation: refusal cases and generated row combinations compare against the
pre-instrumentation predicate; settlement tests assert unchanged joins, boundary
counts and exact reads. Export tests exercise the authenticated metrics route,
zero priming, bounded labels and reload-safe registration. No env/wire contract
changes to [the pipeline](../../listen_pusher_pipeline.mdx).


`omi_episode_f_fallback_total{site}` attributes all nine `_fallback` call sites:
`pending_conflict`, `pending_error`, `synced_failed`, `recheck_failed` (post-Jev
membership read), `previous_failed`, `gate_failed`, `unknown_previous` (empty
predecessor), `recheck_failed_settle` (sync/late owner read), and `unknown_jev`
(no usable answer). `other` bounds unmapped values. Existing `record_fallback`
reasons remain `other` or `unknown` exactly as before, with the same call count.
This counter shares the gate counter's registry, zero priming and inventory
contract. Tests exercise each call site and assert exactly one distinct site
increment plus the unchanged shared fallback arguments; AST coverage fails if a
new call site is missing attribution or reuses a site label.


Local validation on 2026-11-10: `backend/test.sh`, with an explicit file list of
all `tests/unit/test_episode*.py` plus metrics cardinality, reason-label enums,
GMP shadow inventory, alert backtest and telemetry contract tests, passed 1,133
tests across 40 isolated files. The command ran through `bin/omi-heavy` with
`GOOGLE_APPLICATION_CREDENTIALS` and all `CLOUDSDK_*` variables unset,
`BACKEND_UNIT_FILE_BUDGET_SECONDS=900` and four pytest workers. Pyright 1.1.403
on the two changed runtime modules and two changed test modules, using the
worktree's Python 3.11 environment, reported zero errors (189 type warnings).
