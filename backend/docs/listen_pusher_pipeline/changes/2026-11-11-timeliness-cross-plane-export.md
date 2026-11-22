# Timeliness cross-plane export and alert handoffs

Cloud Run integration shares the timeliness leader lease with GKE. Its sync GMP
profile and dev/prod Prometheus bridges must retain all producer-registered
sampler families; election and sampling behavior are unchanged.

The bridge can replay a superseded leader with fresh scrape timestamps. Alert
inputs therefore join each gauge to its own source observation, matching every
identity label except the gauge's extra `leg`, and keep only sources tied for the
newest numeric observation before aggregation. Observation history spans 20m;
freshness is 1200s, covering the 600s maximum cadence plus 60s collection grace
and up to 180s delivery delay with 360s jitter margin. This prevents a stale
Cloud Run breach from borrowing a healthy GKE successor's timestamp. The reverse
handoff has the same guard. Missing or stopped samplers still reach the existing
sample-stale alert after the freshness budget and 5m pending window.

Changed inputs: batch-timeliness (unpublished A/B, sample-stale A/threshold,
scan-blind A), batch-input-retention (staged age A), pipeline-drain (drain C,
held-row A), and critical-failures (backlog A, including growth and saturation).
Combined import and migration-inventory expressions mirror the split sources.
No alert or recording rule currently consumes the staged-clock counter or
all-time/over-SLA counts; the producer-derived scan will guard future consumers.

Verification: the unit selector covers producer, bridge, alert and recording-rule
paths. Real Prometheus fixtures replay stale high values after handoffs in both
directions, sustain sparse 600s observations with 180s Cloud Run delay, and then
stop the sampler to verify paging. Post-deploy qualification requires sustained
Cloud Run leadership, not just its first visible sample, plus both handoffs in
GMP and the alert datasource. No deployment or runtime proof is claimed here.
