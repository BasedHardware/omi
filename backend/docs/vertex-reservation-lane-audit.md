# Reservation cutoff: client audit and verification

Source audit at `85530e7e32`, 2026-10-02. No production reads. Traffic numbers
below are the coordinator's 2026-09-30 14:00–20:00 UTC aggregate snapshot, not a
fresh measurement. Runtime policy: `config/vertex_reservations.py`;
classification: `utils/llm/desktop_reservation_policy.py`.

| Request lane | Active / unknown | Confirmed inactive | Cost and visible effect |
| --- | --- | --- | --- |
| Positively identified macOS task loop, build 7000 ≤ build < configured first-capable build, including its max/Pro fallback | 2.5 dedicated, existing cheaper overflow | Refuse identified loop with terminal `no_task_found` | No inference spend; no tasks from this loop. It still sends subsequent normal capture requests. Unset/invalid threshold, observe mode, and builds outside that range remain served. |
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

Source history audit scanned **1,112 local macOS release tags**, from
`v0.0.1+1-macos` through `v0.12.434+12434-macos`, across the three historical
source locations (`app/macos/Runner`, `desktop/Desktop/Sources`, and
`desktop/macos/Desktop/Sources`). **1,061 tags** have the complete five-tool
signature, beginning at **`v0.7.0+7000-macos`**. Their `no_task_found` branches
have two semantic forms (plus formatting changes): return a `hasNewTask: false`
result immediately, or return already-extracted results and otherwise the same
false result. Empty context/activity strings are accepted in both. The 28 unique
`GeminiClient` source blobs in that matching history decode `functionCall` into
tool calls. Their success path either discards URL response metadata entirely,
checks only 2xx status, or returns for 2xx before examining error/retry headers.
Thus the extra refusal headers on HTTP 200 do not cause a retry or model fallback.

Of the 51 scanned tags below build 7000, 32 (v0.0.1–v0.3.0) contain the
earlier JSON/text-only native extractor and 19 (v0.3.1–v0.6.6) contain no
`TaskAssistant.swift`. None has the complete five-tool signature. The inspected
JSON/text-only decoder cannot consume this tool-only terminal body. The
additional declared lower bound **`MIN_TERMINAL_TOOL_BUILD = 7000`** excludes it
also when a request presents copied/inconsistent tools. No incompatible handling
was found among the matching v0.7.0–v0.12.434 tool-loop families. These are source
history checks, not signed-binary tests or proof that every tag reached Stable.

The audit explicitly includes Stable-era `v0.12.402+12402-macos` and older tags.
**12433 and 12434 already contain the flag-off pipeline from #20265**; they were
incorrectly called pre-pipeline in the prior audit. Capability for this cutoff
means a release containing **#20374**, including quiet refusal handling, not just
presence of `screen_task_jev_gate`. #20374 was open during the release-history
audit and subsequently merged to main as `d84b84f860`. Its client records this HTTP 200 refusal as
`outcome=refused`. The operator must still select the first released build
containing it; no capable build number is inferred from the merge or hardcoded.

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

Classification requires the complete five-tool signature, an extraction workload
or task-extraction lane tag, and a parseable positive macOS Omi identity. Actual
refusal additionally requires confirmed 2.5 inactivity, enforce mode, and
**7000 ≤ build < N**, where `N` is the per-request operator control
`OMI_VERTEX_LEGACY_TASK_MIN_CAPABLE_MACOS_BUILD`. Unset/invalid `N` refuses nothing;
it still records `would_refuse` for otherwise eligible inactive task-loop
candidates, without claiming they are proven older than an unknown release.
At/above `N`, below 7000, Windows, unparseable/conflicting and unidentified callers
are served. No allowlist of individual releases remains.

The audited `GeminiClient` bypasses `OmiHTTPTransport.buildHeaders`: its proxy
requests do **not** explicitly carry `X-App-Platform`, `X-App-Version` or
`X-App-Build`. They use Foundation's ephemeral URLSession default User-Agent.
Codemagic sets `CFBundleName=Omi` and `CFBundleVersion=<release build>`; the Beta
variant sets `CFBundleName=Omi Beta`. A local Foundation canary using those bundle
fields captured `Omi/12434 CFNetwork/3896.100.1.1.1 Darwin/27.0.0` and
`Omi%20Beta/12434 CFNetwork/3896.100.1.1.1 Darwin/27.0.0`. This is a local transport
check, not a signed historical binary or production-header capture. The parser
requires that full name/build/CFNetwork/Darwin structure with a positive integer
build; other wire variants fail open. Explicit macOS platform + consistent
version/build headers are also accepted: the audited `0.<minor>.<patch>` scheme
maps to `minor * 1000 + patch`. Unknown/hotfix version shapes on this explicit
path fail open; a UA without version headers does not need that mapping. A generic transport User-Agent supplies no competing app identity and does not
invalidate explicit headers. If both app-identity forms are supplied they must
agree; malformed Omi or conflicting Windows identities are served.

The false-match surface is a client or intermediary deliberately copying an
old Omi macOS identity together with its extraction tag and complete tool set.
These unauthenticated routing hints are not an attested client identity. A future
client's own identity or the absence of identity cannot trigger refusal. Raw
User-Agent and app versions are never logged or used as metric labels.

## Current flag-off builds and rollout order

The operator leaves the minimum-capable control unset until the first release
containing #20374 is cut, then sets it to that release's build on desktop-backend.
Builds at/above it are served even when flag-off/out-of-cohort or using the legacy
fallback. Builds below it (including 12433/12434 if they precede that release)
are refused after confirmed inactivity when enforce mode is selected. No client
consent/cohort flag is overridden.

`omi_vertex_reservation_policy_total` and the policy log add one bounded
`build_bucket`: `below_supported`, `7000_9999`, `10000_11999`, `12000_12399`,
`12400_12499`, `12500_12999`, `13000_plus`, or `unidentified`. No raw build,
version, or User-Agent is a label/log field. With unset/invalid control, inactive
eligible candidates count as `action="would_refuse"` in either mode; with valid
control, observe mode counts only the below-threshold eligible candidates.
Other states/actions are still counted, allowing candidate traffic to be seen
before inactivity. Setting/removing the control takes effect on the next request.

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
Stopped before 3.8/shared, Lite, Pro-remap and streaming probes. This initial
recipe selected the inherited read-only credential; the corrected interactive
ADC requires reauthentication. It does not establish that the human identity
lacks inference permission.

The coordinator reports a separate 2026-10-02 production dedicated 2.5 Flash
response with `usageMetadata.trafficType=PROVISIONED_THROUGHPUT`. This is available
positive metadata evidence, not this agent's provider-path or 3.8 discovery result.

The authorized dev-operator smoke at `6744d638f3` made 28 synthetic dispatches in
`based-hardware-dev`: 12 dedicated 429 capacity errors and 16 completed shared
200 `ON_DEMAND` responses, across gateway/direct and JSON/SSE. Normal 2.5 requests
fell back to shared 3.1 Flash-Lite; target dedicated failures recovered to shared
3.8. Both states stayed unknown. Four real synthetic probes used the 30-second
deadline and published one failure each; 600-second leases deduplicated new state
instances. State storage was isolated FakeRedis, not deployed Redis. Counts:
48 input, 29 candidate output, 77 total; errors omitted usage. Known gross list
cost $0.0001721; cumulative conservative allowance $0.2801721/$0.50. The PR body
contains every dispatch's counts and exact error message. These are negative-order
and recovery results, not evidence of a live 3.8 order or automatic inactive
confirmation. Refusal classification subsequently moved to the operator-configured build
range above; the response contract is unchanged.

Successful dedicated 3.8 discovery cannot be qualified until its order exists.
Real-order activation and successor-based inactivity remain pending on prod;
the six-hour unknown/shared alert makes missed discovery visible in the meantime.

Follow-up 3 additionally exercised strict **process-local** state with no Redis or
FakeRedis: 12 dev dispatches (8 dedicated 429s, 4 shared 200 ON_DEMAND), gateway/
direct JSON and SSE, both synthetic model probes with actual 30-second deadlines,
and per-process 600-second lease deduplication. Tokens: 12 input, 6 output, 18
total; additional known list cost $0.0000315. Conservative cumulative allowance
across all smokes: $0.4402036/$0.50. All evidence remained unknown, as expected.
A harness assertion initially overlooked the one-second read cache delaying the
second probe; the corrected follow-up verified both leases, with no serving fix.
