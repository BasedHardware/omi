# Desktop Flash tool-request projection

The gateway maps desktop Gemini thinking settings to Luna reasoning effort.
That mapping must run **before** the final OpenAI request sanitizer. GPT-6 Luna
function tools on Chat Completions require `reasoning_effort=none`; a Gemini
`thinkingBudget=1024` must not restore `low` after the sanitizer has removed it.
See the [Luna model contract](https://developers.openai.com/api/docs/models/gpt-6-luna).

## Caller comparison

| Desktop caller | Anchor and request shape | Relevance |
| --- | --- | --- |
| macOS legacy `TaskAssistant.extractTaskSingleStage` | Premium 2.5 Flash / max 2.5 Pro, fallback 2.5 Flash; JPEG plus function declarations, tool history, initial forced tool choice, thinking budget 1024 | Projects to the rejected Luna tools + `low` combination. Still reachable through the screen-task legacy fallback and older installed clients. |
| macOS `ScreenTaskPrompt` / Windows `screenTaskPipeline` | 3.8 Flash; JPEG plus JSON response schema, 2048 output tokens; no function tools | Does not exercise the broken tools/effort combination. macOS requests low thinking; schema bounds remain enforced by the caller. |
| macOS dictation | 2.5 Flash; text-only cleanup, no function tools | Retains its mapped effort. |
| macOS suggestions | Premium Flash Lite / max 2.5 Flash; image plus JSON schema, default thinking budget zero, no function tools | Does not exercise this combination. |
| macOS memory, live notes, goals, dedup, prioritization, home suggestions | Flash Lite; text or image plus structured output, no function tools | Healthy sibling traffic is not evidence that tool-calling requests work. |
| Windows focus, screen synthesis, live notes / shared renderer Gemini client | 2.5 Flash; image/text and structured output, no function declarations at these call sites | Not repaired by the tools/effort change. |

The Swift shared image-analysis helper also declares `image/webp` while its
callers supply JPEG data. Provider rejection from that mismatch has not been
reproduced; it is separate follow-up evidence, not an established cause of the
Flash terminal errors. This fix does not alter image bytes, schemas, array
bounds, tool arguments, output caps, routing, or client code.

## Evidence and limits

`test_macos_payload_preserves_luna_tool_contract_and_drops_unsupported_controls`
in `tests/unit/test_reserved_capacity_only.py` runs the BFF Gemini translator,
real route resolver/executor and OpenAI provider adapter. Only reservation
discovery, credentials and upstream HTTP are faked. It asserts the actual JSON
HTTP body for all three Flash anchors, streaming/nonstreaming, with/without
tools, budgets 0/1024/4096 and a high thinking level. Before the ordering fix,
18 nonzero-thinking tool cases fail and 30 other cases pass. Afterward all 48
pass. Requests without tools retain the requested mapped effort.

This is an offline projection reproduction against the documented provider
contract, not a live provider acceptance result or deployed-product acceptance.
No production request content is needed.

The October 31 investigation supplied 24,363 terminal Luna HTTP 400
`invalid_request` failures among 90,367 Flash requests in seven days (about
3,480 failed requests/day). **These aggregate metrics do not prove Gemini
also returned HTTP 400.** `metrics.observe_error` sets terminal
`fallback_reason=error.failure_class`, not the preceding attempt's failure.
Success metrics and attempt traces have different semantics.

The gateway metric has no tool-presence, reasoning-setting or desktop-caller
dimension. Consequently the attributable fraction cannot be calculated from
it: 24,363 failures (27% of requests) is an upper bound, not the expected
recovery count.

A separate **ro-prod** Cloud Logging read projected only closed-vocabulary
desktop BFF terminal fields for the 24 hours ending 2026-10-31 13:30Z, filtered
to the 2.5 Flash anchor and gateway provider route. Among 17,627 terminal events
(complete, below the 50,000-row limit), 9,389 were HTTP 400: 7,039 macOS
`task_extraction` (75.0%) and 2,350 Windows `unknown` (25.0%). All macOS
task-extraction events in that sample were errors (7,039 HTTP 400, one HTTP
503). This is consistent with the deterministically invalid legacy task-loop
projection. An operational estimate is therefore **about 75% of BFF HTTP 400
volume**, conditional on this being that cohort's rejection cause. The BFF
does not expose the provider's detailed reason, and retries mean BFF events
are not a one-to-one count of unique generations or gateway requests. Do not
apply 75% to the seven-day gateway count as a proven recovered total. The
unattributed Windows quarter remains unproven.

The fix covers the invalid tools/effort construct for every client version
using this gateway. It does not establish that every terminal 400 shares it.
Use bounded per-attempt rejection categories or compare the same lane's 400
fraction before/after a gateway release, with request volume and caller mix,
to measure actual recovery. Do not infer causality from the October 30 volume
step or attribute it to a desktop release without build evidence.

Only **llm-gateway** needs deployment for this fix. Installed apps do not need
an update; callers bypassing this gateway and other invalid payload classes
remain outside its scope.
