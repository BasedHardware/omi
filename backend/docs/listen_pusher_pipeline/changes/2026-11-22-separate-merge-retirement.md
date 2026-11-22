# Retire the separate audio merge worker phase

David's 2026-11-17 quality-ladder flag docket retires the separate merge
worker phase of the audio archive plan (P71). It was dark for five weeks and
no separate merge worker was provisioned, so the phase is deleted rather than
ramped. This removes `AUDIO_ARCHIVE_SEPARATE_MERGE_ENABLED`, which admitted a
uid to the separate worker, and `AUDIO_MERGE_WORKER_URL`, which named that
worker. The feature flag registry records both as retired names.

Serving behavior does not change. Before this change a task left the default
handler only when the phase admitted its owner, and the enable flag was `false`
on every committed serving surface (the composed prod and dev manifest and the
prod and dev listen and pusher charts). That flag was the only cohort gate in
prod: `AUDIO_ARCHIVE_PERCENT`, which the COALESCE phase pins, is `100` there, so
setting the flag would have admitted every owner with no ramp. Dispatch would
have moved to the worker only once `AUDIO_MERGE_WORKER_URL` was also set, and
it was empty on every surface. Every merge task therefore already went to
`AUDIO_MERGE_HANDLER_URL`. The inbound
check accepted the handler URL plus the worker URL; with the worker URL empty
that list already collapsed to the handler URL
alone. Audio-merge tasks now always use the handler URL as both the dispatch
target and the single OIDC audience.

Tasks already in the `audio-merge` queue are unaffected: each was enqueued
with the handler URL as its OIDC audience, so the token Cloud Tasks mints at
delivery is one the handler still accepts. No enqueuer can request a
worker-audience token anymore. The merge queue, its invoker service account,
the paid merge path and raw audio ownership are unchanged.

The other archive phases are untouched: LIVE and READ stay on by default,
COALESCE stays unconditional, and STOP_PCM, SYNC and REGIONAL_CACHE keep their
staged dark rollouts. The runbook
[`sync-ingest-archive.md`](../../runbooks/sync-ingest-archive.md) drops the
phase and its worker provisioning steps.

Rollback is the plain revert of the removal commit. It restores the two env
reads with their code defaults (`false` and empty), which is the state every
surface serves today, so a reverted service behaves exactly like the current
one.

See [the pipeline contract](../../listen_pusher_pipeline.mdx) and
[the generated flag registry](../../feature-flag-registry.md).
