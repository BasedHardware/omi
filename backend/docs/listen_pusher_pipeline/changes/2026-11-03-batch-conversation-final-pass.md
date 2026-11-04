# Batch conversations get a whole-conversation speaker pass

Enrichment runs the shared final pass after speaker resolution/evidence projection
and before summary construction. The [runbook](../../runbooks/batch-conversation-speakers.md#whole-conversation-final-pass)
defines flags, budgets, mapping and rollback; the
[batch speaker contract](../../listen_pusher_pipeline.mdx) remains the authority for
projection ownership and manual receipt precedence.

The default-on kill switch and default-100 percent sit inside existing batch
authority. Each unit's staged PCM and words use its admitted capture clock and
stable projection IDs, including record origin and WAL speech-span parts.
No playback re-encode must equal staged PCM. Missing/expired or privacy-fenced
artifacts and incomplete coverage leave all resolver labels unchanged. Reads have
an invocation budget of 180s, 320 MiB and 512 objects, including manifest sources;
every HTTP inference attempt charges audio/request caps, including retries.

Both sync settings are eligible inside the existing 24h post-projection staged
artifact window. No enrollment or artifact is written and retention is unchanged.
Shared naming keeps thresholds and owner arbitration; manual receipts win.
The lead ramps 10/50/100 using fallback rate, owner-parity delta, p95 enrichment
latency and diarizer-batch queue depth. Estimate 0.03–0.042 GPU-hours per admitted
audio-hour; per-unit diarization remains additive. Hermetic tests cover both
projection ID paths, capture gaps, whole-pass abstention, sync-off expiry,
read limits, privacy revocation and retry budget refusal before HTTP dispatch.
