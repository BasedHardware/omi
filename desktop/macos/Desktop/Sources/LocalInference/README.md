# Local inference

`LocalInferenceService` is the local engine port. `LocalInferenceRuntime`
selects AFM when available, otherwise the developer loopback server; force/disable
settings can override selection. Failures retry only when transient, then return
`DeterministicConversationMinimum`. There is no cloud inference fallback.

- `AFMJSONSchemaBridge` validates the supported schema subset and preserves
  authored property order at every object, including objects inside array items.
  Its bounded UTF-8 scanner reads key order after Foundation validates JSON;
  duplicate decoded keys and unsupported shapes fail with `capabilityUnavailable`.
  Guided generation writes properties in that order.
- `LocalServerInferenceAdapter` accepts loopback URLs only, refuses redirects,
  splices schema text verbatim, and caps completions. Configuration includes
  explicit sampling defaults: temperature 0.7, top_p 0.8, top_k 20, min_p 0,
  presence_penalty 1.5, and disableThinking true. These are the Qwen3.5
  non-thinking settings measured on 2026-09-20 (0/51 repetition loops versus
  3/19 at temperature zero). Setting disableThinking false omits the template
  override; it does not force thinking on.
- `ConversationChunkSummarizer` budgets map/reduce calls from engine context,
  validates meaningful drafts, and assembles the client-processing projection.
  `LocalProjectionStore` owns persistence; finalization selects the local path.
- `DesktopLocalInferenceFallbackRecorder` uses the established
  `DesktopDiagnosticsManager.recordFallback` path: one `desktop_health_event`
  with `health_event=fallback_triggered`, `area=local_llm`, and bounded `from`,
  `to`, `reason`, `outcome`. The shared manager records locally and forwards to
  `AnalyticsManager`/PostHog on prod/beta; dev builds suppress remote analytics.
  Engine labels are afm, local-server, deterministic_minimum, none, or other.
  The shared reason allowlist buckets unknown reasons to other. No prompt,
  transcript, or free-form error is included. These are fallback counts, not
  a census of all Macs or proof of why Apple Intelligence is unavailable.

Build/tests from `desktop/macos/Desktop`:

```sh
xcrun swift build --build-tests
xcrun swift test --filter 'AFMLocalInferenceAdapterTests|AFMJSONSchemaBridge|LocalServerInferenceAdapterTests|LocalInferenceRuntime|ConversationChunkSummarizerTests|LocalSummaryBenchmarkTests|LocalSummaryEvalCorpusTests'
```

The focused suites exercise production parsing, captured HTTP bodies, fallback
health snapshots, and deterministic summarization without model generation or
live HTTP. Live AFM/server quality evaluation is opt-in and separate.
