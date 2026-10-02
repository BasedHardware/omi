# Reservation cutoff: client audit and verification

Source audit at `85530e7e32`, 2026-10-02. No production reads. Traffic numbers
below are the coordinator's 2026-09-30 14:00–20:00 UTC aggregate snapshot, not a
fresh measurement. Runtime policy: `config/vertex_reservations.py`;
classification: `utils/llm/desktop_reservation_policy.py`.

| Request lane | Active / unknown | Confirmed inactive | Cost and visible effect |
| --- | --- | --- | --- |
| macOS legacy task loop, premium; also fallback from max/Pro and failure fallback from the new extractor | 2.5 dedicated, existing cheaper overflow | Refuse identified loop with terminal `no_task_found` | No inference spend; no tasks from this loop. It still sends subsequent normal capture requests. Roll out the new pipeline first. |
| macOS new gated one-call extractor | 3.8 dedicated when active; shared otherwise | 3.8 shared | No quality/model change; list $1.50/$7.50 per million input/output when shared. |
| macOS voice-typing cleanup (`PushToTalkManager`, `ModelQoS.Gemini.dictation`) | 2.5 dedicated | 2.5 shared (`desktop_other`, future `macos_dictation` tag) | Preserve text quality; $0.30/$2.50 per million. Per-lane volume unavailable. |
| macOS max-tier notch suggestions, and their Flash fallback (`SuggestionAssistant`) | 2.5 dedicated | 2.5 shared (`desktop_other`, future `macos_suggestions` tag) | Preserve suggestions; same 2.5 price. Per-lane volume unavailable. |
| Windows screen task extraction (`assistants/tasks/geminiWire.ts`) | 2.5 dedicated | 2.5 shared (`windows_tasks`) | No new pipeline exists on Windows; keep task capture available. |
| Windows focus/distraction screenshot analysis (`assistants/focus/gemini.ts`) | 2.5 dedicated | 2.5 shared (`desktop_other`, future `windows_focus` tag) | Preserve focus/distraction classification and notifications. |
| Untagged/unknown Flash desktop callers, older/unidentified tool loops | 2.5 dedicated | 2.5 shared (`desktop_other` / `windows_tasks`) | Conservative classification; does not switch unrelated features off. |
| Gateway backend features | No feature profile currently resolves to 2.5 Flash | Explicit/default 2.5 anchors use shared (`backend_other`) | `model_config.py` has Luna/Nano plus seven 2.5 Flash-Lite features; generated desktop-vertex-flash is the only normal Flash route. Future feature overrides retain requested model. |
| macOS memory, LiveNotes, goals, dedup, prioritization, home suggestions, premium notch suggestions; Windows memory, goals, insight; backend session_titles, followup, onboarding, app_integration, trends, translation, screen_frame_judge | Pinned 2.5 Flash-Lite shared | Unchanged | Never promoted onto a costlier model. |
| macOS max task loop, Insight and any requested Pro | 3.1 Flash-Lite shared (over quota: 2.5 Flash-Lite) | Unchanged | Existing Pro containment remains. Only an actual subsequent 2.5 task-loop request is subject to refusal. |
| BYOK (all features/platforms) | User-selected model/key | Unchanged | Does not read, teach or enforce reservation state. |

The snapshot contains 13,524 successful Flash calls: tagged extraction with an
image = 58% of calls / 69% of burn; untagged image = 32% / 27%; untagged text =
10% / 4%. The untagged 42%/31% is attributed mainly to Windows, **not an exact
Windows census or a task/focus split**. Whole old-model PayGo was estimated at
~$100/day; the untagged share is roughly ~$31/day on a burn-proportional estimate,
not a measured bill (burndown weighting differs from list-price weighting).
Refusing all Windows Flash would disable both task extraction and focus for all
Windows users. Keeping it shared is the default decision awaiting David's review.
Moving each lane to dedicated 3.8 would avoid its marginal PayGo while capacity
is available, but unreserved 3.8 costs 5x input / 3x output; this PR does not make
an unevaluated model switch. Cheap-Lite remaps risk extraction/text quality.

## Shipped client response audit

Read current sources and tags `v0.12.434+12434-macos`, `v0.12.433+12433-macos`,
`v0.12.432+12432-macos`, `v0.12.425+12425-macos` with `git show`. All four pin
premium tasks to Flash, max tasks to Pro, and send `X-Omi-Workload: extraction`.
All four task loops declare `search_similar`, `search_keywords`, `extract_task`,
`reject_task`, `no_task_found`; the last tool immediately returns no new task.
ModelQoS blob is `240cba054edb576df83265400e327d3d51c0c413` on these tags.
These are source-tag checks, not a claim that each candidate reached Stable.

`GeminiClient.httpError` reads `X-Omi-Retryable`; retry and secondary-model
fallback require explicit true. A 426 with false stops that round but returns an
API error for each future screen. It has no 426-triggered updater UI. The existing
stale list-client 426 precedent does not make Gemini requests update-aware.
Windows `sendToolTurn` at this main also now requires `x-omi-retryable: true`;
the proxy's comment about Windows retrying on 503 alone describes older clients.
Neither 426 nor 403 is a retryable capacity error in those older status-based
clients. Windows callers catch failures rather than crashing, but repeated frames
still create error logs. No server response can install its missing new pipeline.

Chosen refusal: HTTP 200, `X-Omi-Retryable: false`,
`X-Omi-Reservation-State: inactive`,
`X-Omi-Error-Class: legacy_task_reservation_inactive`, and one Gemini
`no_task_found` function call with empty context/activity and `finishReason=STOP`.
SSE wraps that same candidate. It does not fabricate analysis, token usage, tasks
or activities. Existing decoders take their successful zero-task termination;
there is no error, retry, model fallback, or update prompt. The server records a
**refusal**, not an inference success. Normal later capture requests continue,
but no provider is billed. This is suppression of inference, not remotely
stopping the old executable.

Classification requires the full five-tool signature plus the shipped macOS
extraction workload tag. Windows platform/UA declarations override that tag.
An untagged signature is preserved as Windows/unknown. The broad workload tag,
a screenshot, version number, or raw prompt alone never authorizes refusal.
Optional `X-Omi-Lane` can refine classification, but is not required and is not
logged raw. Refusal still requires the tool signature to avoid synthesizing a
tool a caller cannot decode. These are routing hints, not a security boundary.

## Current flag-off builds and rollout order

A server hint cannot retrofit new-path selection into already shipped builds.
Silently forcing it would also bypass the current consent/cohort flag and its
rollback semantics. **Before enforcement becomes effective, deploy the gate,
ship the capable macOS version, and complete the eligible/consenting macOS ramp.**
David has authorized privacy; this PR does not create or change any flags.
If migration wins that race, use `OMI_VERTEX_LEGACY_TASK_MODE=observe` until the
ramp is ready, accepting the visible old-lane PayGo cost. Default remains enforce,
as requested. Flag-off/out-of-cohort clients otherwise receive zero-task refusals;
that is an explicit rollout dependency and a decision for David, not a hidden
claim that all current clients can be served. A failed new extractor's old-loop
fallback is likewise refused; retry the new path on the next capture.

## Live smoke, 2026-10-02

Two synthetic calls reached the real `VertexGeminiProvider` HTTPS path:
`gemini-2.5-flash`, regional `us-central1`, dedicated header. Both returned
403. The first exposed a decoding error in the observation harness; after fixing
raw-byte capture the second confirmed `PERMISSION_DENIED` for
`aiplatform.endpoints.predict`. The authorized ADC mint succeeded. No alternate
identity, production endpoint, datastore or control-plane API was used.

Both calls reported no token counts and no trafficType; counts are **unreported**,
not inferred zero. Conservative reserved spend $0.02 each, $0.04 total, below
the $0.50 ceiling. There is no successful live routing evidence from this run.
Stopped before 3.8/shared, Lite, Pro-remap and streaming probes. Re-run the bounded
synthetic provider smoke with that same authorized credential source once its
inference permission is restored. Mock coverage cannot replace this release gate.
