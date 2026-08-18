# Analytics

What Context for Claude reports about itself, where it lands, and how to ask it a question.

Before this existed the app was completely unmeasured. The only signals were GitHub release download
counts — whose `-latest` pointer resets on every release, so the history was being destroyed weekly —
and Cloud Run request logs, which see nothing from an install that never signs in. "How many people
use this" could not be answered.

## Where it goes

PostHog project `302298`, the same project as the Omi macOS app, via `https://us.i.posthog.com/batch/`.
The project token in `AnalyticsSink.projectToken` is public by design: it can only write events into
that project, it reads nothing, and it already ships inside the Omi desktop binary.

**Two products, one project, kept apart by two independent mechanisms:**

1. Every event name is prefixed `cfc_`.
2. Every event carries `app = "context-for-claude"`.
3. **No event sets `$os_name`.** Omi's macOS retention, activation and weekly-actives queries all
   scope on `properties.$os_name = 'macOS'`. Setting it here would silently enrol every Context for
   Claude install into a four-month Omi trend line. `macos_version` carries the same information
   under a name nothing else queries.

Either of the first two alone is enough to separate the products; both are present so that whichever
one a future query author reaches for, it works. The third is pinned by
`AnalyticsPayloadTests.testPayloadNeverSetsDollarOSName`.

## What is sent

The complete list is `AnalyticsEvent` — a closed enum, deliberately, so this file cannot go stale
without a compile error somewhere. Every associated value is a number, a bool, or another closed
enum; `AnalyticsEventTests.testNoEventCarriesFreeFormText` fails if a free string appears.

| Event | Answers |
|---|---|
| `cfc_first_launch` | installs — the denominator |
| `cfc_app_launched` | the only signal from someone who opens the app and does nothing |
| `cfc_daily_active` | **DAU, retention, and "how much"** — see below |
| `cfc_permission` | the setup funnel, per capability, snapshotted every launch |
| `cfc_onboarding_step` / `cfc_onboarding_finished` | where first run is abandoned |
| `cfc_account_state` | whether an Omi account is attached (never which) |
| `cfc_capture_state` | mic / system audio / screen going live and stopping |
| `cfc_gesture_fired` | ⌘ + ⌘ actually firing — inert without Accessibility |
| `cfc_surface_opened` | which surfaces people open by hand |
| `cfc_search_ran` | local search use, bucketed result counts only |
| `cfc_update_outcome` | update health — a fleet that stops updating looks like a fleet nobody uses |
| `cfc_fallback` | fail-open paths, mirroring `ContextTelemetry.recordFallback` |

### `cfc_daily_active` is the spine

One event per install per **local calendar day**, carrying the day's rollup:

- `tool_calls_total`, `tool_calls_distinct`, and one `tool_<name>` per MCP tool
- `capture_minutes`, `screen_minutes` — wall clock, not a count of start/stop events
- `active_hours` — distinct hours in which anything happened. Twelve active hours and twelve capture
  minutes is a person at a desk; one active hour and 600 capture minutes is a laptop left open.
- `signed_in`, `airgapped`, `idle`

DAU is this event. Retention is this event, cohorted. "How much do they use it" is
`tool_calls_total` — the only evidence that captured context is reaching a model rather than
accumulating on a disk.

### What is never sent

No transcript, no OCR text, no window or app names, no URLs, no file paths, no search queries, no MCP
tool arguments, no email, no account id, no screenshots. A reader of `AnalyticsEvent.swift` can see
the entire disclosure — that is the property the closed enum exists to guarantee.

## Identity

`distinct_id` is `cfc_` + 16 hex characters of `SHA256("context-for-claude/analytics/v1" + installId)`.

The install id is the same UUID `ClientDevice` uses, under a **different salt**. That separation is
the whole privacy argument: the backend's `X-Device-Id-Hash` keys the user's own captured rows and is
joinable to their account, so an equal id would make every "anonymous" event trivially
re-identifiable by anyone holding both datasets. Salted apart, the two cannot be linked without the
original UUID, which never leaves the Mac.

**The id does not change on sign-in.** Knowing *that* an install has an account answers every product
question here; knowing *which* would turn an anonymous series into a per-person record of when
somebody's microphone was on.

Changing `AnalyticsIdentity.salt` re-anonymises every install and restarts every retention curve.
Don't.

## The three refusals

1. **Airgap Mode drops events, it does not defer them.** Every other `NetworkEgress.Client` queues
   its work and sends when the switch goes off. An analytics event doing that would mean Airgap Mode
   delayed the disclosure rather than preventing it. Those days are simply not measured.

   Note that **the Settings switch for Airgap Mode no longer exists** — it was removed in 1.0.9 and
   `ExclusionEngine.setAirgapMode` has had no caller since. The flag is still reachable two ways, and
   both are why the guard stays: an `exclusions.json` written before 1.0.9 (or by hand) still carries
   it, and `ExclusionSet.make` forces it on whenever the exclusion configuration **fails closed** — a
   config we cannot parse may carry exclusions we cannot express. The second case is the one that
   matters in practice: it means a machine with a corrupt config stops reporting rather than
   reporting from a state where it cannot honour the user's exclusions.
2. **Development builds report nothing.** `ContextPaths.isDevelopmentBuild` gates the whole path. This
   is not tidiness: for this app's first three weeks the Cloud Run logs show a `Context for Claude/1`
   user agent from up to twenty machines a day — the team's own builds, indistinguishable in
   aggregate from users.
3. **Nothing user-authored, ever** — enforced by construction, not by review.

## MCP tool calls cross a process boundary

`context-for-claude-mcp` is spawned by Claude over stdio, several at a time, and killed without
warning. It cannot report anything itself: a short-lived process that POSTs on exit either blocks
Claude's shutdown or loses the event.

So the MCP process counts and the app reports. `ToolCallLedger` (in `ContextCore`) is the seam — a
multi-writer counter file under an `flock`, drained destructively by the app's daily rollup. It is
separate from `QueryStamp` because that file is monotonic-latest ("did Claude just call us?") and this
one is cumulative ("how much?"); one file cannot be both.

Both hold a tool name and nothing else.

## Delivery

Batched, not per-event. One request per event would be absurd at ~10 events a day and, worse, would
make the app's network fingerprint track the user's activity in real time — a request the moment a
recording starts, another the moment a search runs. Batching on a 60-second timer decouples *when we
send* from *what the person just did*. That is a privacy property, not only an efficiency one.

The spool is durable (survives relaunch), capped at 500 events dropping oldest-first, and drains 50
per request. A failed send keeps the events; a 4xx other than 429 drops the batch, because keeping an
unsendable batch would park every later event behind it forever.

## Verifying it end to end

A release build cannot be run under a debugger on the machine that wrote it, and a sink nobody has
watched deliver is a sink that has never worked. So:

```bash
CONTEXT_ANALYTICS_FORCE=1 /path/to/Context\ for\ Claude.app/Contents/MacOS/Context\ for\ Claude
```

This overrides refusal 2 only. Events sent this way are indistinguishable from real ones and land in
production series — use a throwaway session, not a day of ordinary work.

Then query PostHog:

```sql
SELECT event, count() AS n, count(DISTINCT person_id) AS installs
FROM events
WHERE timestamp > now() - INTERVAL 1 DAY AND properties.app = 'context-for-claude'
GROUP BY event ORDER BY n DESC
```

## Asking it questions

`~/.claude/skills/omi-analytics/scripts/ph.py --preset cfc` covers actives, installs, tool-call
volume and the permission funnel. Anything else is HogQL against `properties.app =
'context-for-claude'`.
