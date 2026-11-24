# Allowlisted unsupported languages on server batch

[Admission contract](../../listen_pusher_pipeline.mdx#server-batch-only-capture-by-platform).

David approved this experiment on 2026-11-03, excluding Japanese. Dev/prod
listen ships with `SERVER_BATCH_UNSUPPORTED_LANGUAGES` empty, preserving previous
new-session admission. The lead owns the initial language rollout after
`backend-sync-backfill` serves this commit. Profile agreement and all privacy,
funding, speaker and custody checks still apply. Bosnian retains its recorded
`bs` route while matching the existing `sr` spoken-language profile equivalence.

The shared C8 route/enqueue API lives in lightweight `provider_stt_admission.py`;
provider execution remains in `provider_stt.py`, keeping pusher admission free of
GPU-worker/provider-execution imports. All in-tree callers use the new owner.
The CPU serving coordinator injects the provider outbox factory; shared capture
and GPU repair helpers never import the generic CPU outbox/enrichment registry.

Native complete and partial units previously bypassed provider selection and
entered the GPU ring. Named unsupported units now enter the existing C8 Modulate
batch stage with its atomic outbox, paid-once intent and unchanged diarization.
The recorded language determines their route even after the allowlist is cleared.
`record_language.prove_manifest` preserves declared-language evidence without LID;
only auto/multi inputs use whole-unit proof. Vendor routing tables already classify
these languages as `gpu_unsupported`, which cannot contain a GPU option.

`omi_batch_pipeline_language_route_total{route="blocked"}` is route evidence,
not a job state or a count of permanently lost units. At `surface=worker` it
means the frozen language barred Parakeet before VAD/ASR; speech then fails the
language barrier and follows existing fenced recovery/held disposition. At
`surface=intake` it means admission excluded the language with no legacy route
available. The reported approximately 645/day is task-provided, not verified
against production in this change. Newly admitted named unsupported native units
bypass that worker entirely and emit `surface=intake,route=multilingual`.

The rollout lead must serve the new native-record drainer/provider routing on
`backend-sync-backfill` before enabling the listen allowlist. Checked-in chart
values and the composed runtime manifest keep it empty through a listen-first
release; an older drainer would still enqueue these units at the GPU language barrier.

Planscost reads the bounded per-language suppression counter and Modulate batch
results after 48 h clean batch timeliness, `failed_held`, and T2 `terminal_speech`;
then expands languages in batches, always excluding Japanese. Counters measure
initialization decisions, including retries, rather than unique sessions.
Provider health/funding holds remain possible and visible through existing C8
metrics; this change does not bypass them or promise a transcript during outages.

Evidence: `test_server_batch_unsupported_languages.py`, native complete-record
routing cases in `test_batch_pipeline_live.py`, partial continuation cases in
`test_record_partial.py`, and the existing provider/vendor-routing suites.
