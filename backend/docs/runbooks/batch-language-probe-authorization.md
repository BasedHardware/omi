# Serving batch language-probe authorization

Unknown-language intake can classify audio with the self language model and then
the vendor detector. Immediately before each call, serving batch intake performs
a new uncached privacy transaction, checks `funded_processing.consent_allows`,
and asks `sync_allowed` for the batch lane. Execution-admission cohort membership
never skips those checks. The item carries the initial privacy generation.

The per-unit result distinguishes `PROBE_SKIPPED` from `REFUSED`; both stop
later probes for that unit. A funding denial or unavailable funding read skips
optional classification and retains ordinary unknown-language staging/admission.
It does not strand capped uploads in503 retries or authorize an unfunded model
call. Existing compute/provider dispatch still applies its own funding fence.

Only privacy, consent or their unavailable authority refuses intake. The caller
checks the guard after resolution: privacy denial returns the existing409;
consent/privacy-read failure returns the existing503 retry. These refusals do
not acknowledge success, stage the denied unit, admit a queue job, transfer
ownership to legacy, or delete a source. Earlier stages remain for reconciliation.
The sync router archives raw capture before intake and the client retains its WAL
on retry. Cap-held admission retains its durable hold on503. A consent reset
during a funding check is rechecked and refuses rather than being treated as a
budget-only skip. No accepted-job or hold-state protocol changes.

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
