# Reservation cutoff: client audit and verification

Source audit at `85530e7e32`, 2026-10-02. No production reads. Traffic numbers
below are the coordinator's 2026-09-30 14:00–20:00 UTC aggregate snapshot, not a
fresh measurement. Runtime policy: `config/vertex_reservations.py`;
classification: `utils/llm/desktop_reservation_policy.py`.

| Request lane | Active / unknown | Confirmed inactive | Cost and visible effect |
| --- | --- | --- | --- |
| Audited pre-capability macOS task loop (builds 12425, 12432, 12433, 12434), including its max/Pro fallback | 2.5 dedicated, existing cheaper overflow | Refuse identified loop with terminal `no_task_found` | No inference spend; no tasks from this loop. It still sends subsequent normal capture requests. Other builds remain served. |
| Current/capable macOS old loop, flag-off/out-of-cohort, or new-extractor legacy fallback | 2.5 dedicated, existing cheaper overflow | 2.5 shared (`desktop_other`) | Preserve service; no automatic path selection or consent/cohort override. |
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

Classification requires all three: the five-tool signature, an extraction workload
or task-extraction lane tag, and **positive identification of an audited macOS
build predating the new pipeline**. Only builds 12425, 12432, 12433 and 12434 are
currently declared. Every other build (including older but unaudited builds),
missing/contradictory identity, generic Darwin user agent, and Windows caller is
served. This intentionally sacrifices cutoff coverage rather than guessing.

The audited `GeminiClient` bypasses `OmiHTTPTransport.buildHeaders`: its proxy
requests do **not** explicitly carry `X-App-Platform`, `X-App-Version` or
`X-App-Build`. They use Foundation's ephemeral URLSession default User-Agent.
Codemagic sets `CFBundleName=Omi` and `CFBundleVersion=<release build>`; the Beta
variant sets `CFBundleName=Omi Beta`. A local Foundation canary using those bundle
fields captured `Omi/12434 CFNetwork/3896.100.1.1.1 Darwin/27.0.0` and
`Omi%20Beta/12434 CFNetwork/3896.100.1.1.1 Darwin/27.0.0`. This is a local transport
check, not a signed historical binary or production-header capture. The parser
requires that full name/build/CFNetwork/Darwin structure and an audited build;
other wire variants fail open. Explicit macOS platform + matching audited
version/build headers are also accepted, with conflicting hints rejected.

The false-match surface is a client or intermediary deliberately copying an
old Omi macOS identity together with its extraction tag and complete tool set.
These unauthenticated routing hints are not an attested client identity. A future
client's own identity or the absence of identity cannot trigger refusal. Raw
User-Agent and app versions are never logged or used as metric labels.

## Current flag-off builds and rollout order

Current/capable builds are **served**, including flag-off/out-of-cohort legacy
loops and the new extractor's legacy failure fallback. They use shared 2.5 after
confirmed inactivity. There is no server path-selection hint and no consent/cohort
override. The ramp still reduces spend, but is no longer a correctness dependency
for keeping capable clients functional. Default enforcement applies only to the
explicitly audited pre-capability builds. Observe mode remains available.

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
