# Connector background refresh

Periodic, unattended refresh of the macOS import connectors (Calendar, Apple
Notes, local files).

Before this existed there was no scheduler anywhere in the desktop app.
`ImportConnectorStatusStore` persisted a UserDefaults timestamp and nothing ever
re-read the source, so "Connected" was a latch: a connector that last synced
weeks ago looked identical to one that synced this morning. `INV-INT-1` forbids
gating connected state on a timestamp latch or a one-time success — keeping the
data genuinely fresh is the other half of honoring that.

## Shape

| Type | Role |
|---|---|
| `BackgroundRefreshableConnector` | What a connector must declare to be schedulable |
| `ConnectorRefreshPolicy` | Pure decide/backoff/state-transition core — no clock, no I/O |
| `ConnectorRefreshState` + `…StateStore` | Per-user, per-connector durable bookkeeping (one JSON blob per connector) |
| `ConnectorRefreshOutcomeMapper` | Total mapping between import outcomes and refresh results |
| `ConnectorRefreshScheduler` | Timer, wake/terminate observers, dispatch, attention, fallback telemetry |
| `*BackgroundRefreshAdapter` | Thin per-connector shims; own no reader internals |

The scheduler refreshes **at most one connector per tick**, chosen most-stale
first. That is the anti-thundering-herd rule and an implicit global
single-flight. Per-connector single-flight is delegated to the existing
`ConnectorImportRunner.start`, which already returns `nil` for an in-flight run
and already owns run state and terminal telemetry — there is no second
single-flight mechanism here.

## Eligibility: never prompt in the background

The hard rule. A background refresh must **never** raise a macOS consent
dialog. The `userInitiated` gates in the readers are not bugs — those paths
decrypt another application's Keychain item (browser cookies), address Apple
Events at Notes.app, or make a first-touch TCC read of a user folder, and each
surfaces a system dialog. A naive timer passing `userInitiated: true` would spam
permission prompts from a process the user is not looking at, so every adapter
passes `userInitiated: false`.

So eligibility is a **declared property of the connector**
(`supportsUnattendedRefresh`), never inferred from a connector id, and it is the
first and highest-precedence gate in `ConnectorRefreshPolicy.decide`. It is a
`{ get }` requirement rather than a stored constant because local files is only
prompt-free *after* a user-initiated scan proved a full grant
(`deniedUserFolders.isEmpty`, recorded as
`ConnectorRefreshState.unattendedGrantProven`).

Skip precedence, most structural first:

```
notEligibleForUnattendedRefresh → notConnected → needsUserAction → alreadyRunning
→ signedOut → offline → batteryCritical → backoffNotElapsed → intervalNotElapsed
```

## Raw import only — never LLM synthesis

A background refresh does raw, idempotent import and nothing else.

The backend dedupes raw import artifacts on `external_id` + `content_hash`
(`backend/database/memory_imports.py`), so re-importing the same events, notes,
or files is a no-op. The **synthesis** path emits items with no `external_id`,
so varying model output would mint fresh duplicate artifacts on every refresh,
forever. This repo has already paid for that failure once with a server-side
purge. Every adapter's doc comment repeats this, and the unattended entry points
listed there must skip `synthesize*` entirely. Mechanically that is one flag:
`ConnectorImportOperations.importAppleNotes`/`importCalendar` only call
`synthesizeFromNotes`/`synthesizeFromEvents` under `if userInitiated`, and the
local-file rescan is an on-device reindex with no synthesis path at all.

## Failure handling

- **Transient** (network, timeout, rate limit, …) → exponential backoff from 15
  minutes to a 6 hour ceiling, ±15% injected jitter.
- **Five consecutive transient failures** → escalate to `needsUserAction` and
  stop retrying.
- **User-action classes** (expired session, denied grant, decrypt failure, …) →
  park immediately, no backoff loop. Retrying either fails identically or raises
  a prompt.
- **`noContent`** is a *success* with zero counts. A read that legitimately found
  nothing is not a failure.
- **Re-arm**: a user-initiated sync (`connectorDidSync`) clears failures and
  unparks the connector with no app restart.

`record_fallback` fires at exactly two sites, deduped to once per connector per
24h: retries exhausted / credential died → `manual_only`, and persistently
deferred past 2× the interval → `deferred`. Area `sync_dispatch`, reasons
`auth`/`policy`/`other`. A single transient failure and expected steady-state
skips emit nothing.

## Live wiring

`ConnectorRefreshRegistry.live()` is installed by `ViewModelContainer.init`, and
every adapter's `liveRefresh(progress:)` calls the real import operation:

| Adapter | Live call | Eligible unattended? |
|---|---|---|
| Apple Notes | `importAppleNotes(progress:userInitiated: false)` | yes |
| Calendar | `importCalendar(progress:userInitiated: false)` | **no** — see the adapter's doc comment; flips with server-side OAuth |
| Local files | `rescanLocalFiles()` | only once a user-initiated scan proved a full grant |

The progress sink is threaded through `BackgroundRefreshableConnector.refresh(progress:)`
rather than built per adapter: `ConnectorImportRunner.ProgressSink` has
`fileprivate` storage, so only the runner can create one, and the scheduler
already dispatches through the runner. The protocol is `@MainActor`, so the sink
never crosses an isolation boundary.

Scheduler-driven runs pass `surface: .background` to the runner. The runner is
the single terminal telemetry boundary for imports, so without a distinct
surface every unattended tick would land in the user-initiated
`Integration Connect *` funnel and silently change what the existing PostHog
queries measure.
