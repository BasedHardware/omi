# Tiered upload coalescing and original-request telemetry

2026-11-17. [Environment and receipt contract](../../listen_pusher_pipeline.mdx#tiered-batch-upload-coalescing-contract).

Free fresh and free non-fresh uploads can use independently configured longer
holds. Both code defaults remain 60 seconds; paid/trial/unknown behavior, R7,
privacy/custody/erasure and retention are preserved. Extended groups require a
fresh complete-fleet capability receipt and cap at 16 members, 600 seconds of
audio AND capture span, with existing byte/file/quota bounds. New compatible
completion readers accept those groups with local windows unset/60 or producer
OFF. No capability roster was published by this PR.

The unit counter and original-request-to-durable-transcript histogram use four
closed entitlement labels, retain original clocks through fanout, and are tested
against both Cloud Run scrape profiles and worker/sync export. Pre-accept retries,
client receipt and notes are separate measurements. Current entitlements do not
expose a separate live trial state; missing adapters remain unknown/unmeasured.

[Qualification and ramp](../../runbooks/batch-upload-coalescing.md): replay tests
cover 300/600s units and recovery custody; real RSS/VRAM, paired output quality,
provider recovery, oldest outstanding age, latency and net reads remain canary
work. There is no 10% coalescing cohort switch. First canary is already-admissible
free backlog at 300s, free fresh at 60s, on backend-sync producers and all drainers
after capability verification. Free p90 must stay below 30 minutes, paid/trial
latency unchanged. Margin lead expands; done or reverted by 2026-11-24. Rollback
is both windows 60, retaining compatible readers for outstanding groups.

The enrichment HTTP adapter now lives with the lightweight enrichment router;
worker RPC imports remain at module scope without burdening that adapter with
serving/projection imports. Its response/queue contracts and strict timing guard
are preserved. Part B's content-completion trigger is design only.

No deploy, merge or production configuration/data change. No saving is claimed.
