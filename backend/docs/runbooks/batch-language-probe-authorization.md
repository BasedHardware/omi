# Serving batch language-probe authorization

Unknown-language intake can classify audio with the self language model and then
the vendor detector. Immediately before each call, serving batch intake performs
a new uncached privacy transaction, checks `funded_processing.consent_allows`,
and asks `sync_allowed` for the batch lane. Execution-admission cohort membership
never skips those checks. The item carries the initial privacy generation.

A denial remains sticky for the unit, so resolver fallback cannot buy a second
call. The caller checks the guard after resolution: privacy denial returns the
existing409 response; consent/funding/read failure returns the existing503 retry
response. Neither acknowledges success, stages the denied unit, admits a queue
job, transfers ownership to legacy, nor deletes a source. Earlier staged units
remain retained for reconciliation. The sync router archives raw capture before
intake and the client retains its WAL on retry. Cap-held admission treats503 as
retry and retains its original durable hold. This is not a new accepted-job or
hold-state protocol.

Declared language invokes no probe and keeps the existing admission behavior.
The resolver's optional self-probe hook is shared with #24057; callers that do
not pass it retain their existing behavior.

Other callers, inventoried2026-10-29 (not changed here):

| Caller | Local callback contract | Remaining inspection |
| --- | --- | --- |
| `utils/stt/pre_recorded.py:prerecorded_from_bytes` | Calls `resolve_language` without probe hooks | Inspect each surface's upstream authorization before extending this guard |
| `utils/sync/pipeline.py` service-selection lambda | `resolve_file` receives vendor funding callback conditional on cap enforcement; no self hook | Characterize privacy/consent at each actual dispatch and preserve its cap-held custody on denial |
| `utils/stt/batch_language.py:resolve_file` | Forwards the optional vendor hook to `resolve_language`; no self hook parameter | Shared helper contract for the pipeline caller above |
| `utils/stt/batch_language.py:resolve_url` | Calls `resolve_language` without either hook after bounded download | Inspect upstream callers and authorize classification independently of download |
| `utils/batch_pipeline/shadow_intake.py` | #24057 supplies both hooks and fresh guard | Shadow discards denied candidates; serving must retain caller custody instead |

This inventory is source evidence, not a production incident count. The remaining
caller review belongs to the batch/funded-processing owners and the transcription
initiative; it must not be inferred complete from the serving-batch fix.
