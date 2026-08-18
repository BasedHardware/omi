import ContextCore
import Foundation

/// Everything Context for Claude will ever report about itself, as a closed vocabulary.
///
/// ## Why an enum and not a string
///
/// A `track(name:properties:)` taking free-form strings is how analytics schemas rot: names drift
/// (`app_open`, `App Opened`, `appLaunched` all meaning one thing), properties acquire user text by
/// accident, and nobody can answer "what does this app send?" without grepping the whole target. The
/// enum makes the answer a single file, makes a typo a compile error, and — the reason that matters
/// most here — makes it *structurally impossible* for a call site to attach a string it happened to
/// have lying around, because there is nowhere to put one.
///
/// **Every associated value in this file is a number, a bool, or another closed enum.** That is the
/// invariant. `AnalyticsEventTests.testNoEventCarriesFreeFormText` fails if a `String` appears.
///
/// ## What this app does not send
///
/// No transcript, no OCR text, no window or app names, no URLs, no file paths, no queries, no MCP
/// tool arguments, no email, no account id, no IP-derived location, no screenshots. This app's whole
/// premise is that it watches a person's screen and hears their room; an analytics payload is the
/// one place where the temptation to include "just a little" context is strongest and the cost of
/// giving in is highest. The rule is that a reader of this file can see the entire disclosure.
enum AnalyticsEvent: Sendable {

    // MARK: - Lifecycle — "how many people use this"

    /// The very first launch on this Mac, ever. The install denominator.
    case firstLaunch

    /// Every launch after the first. Cheap, and the only signal from someone who opens the app and
    /// does nothing else.
    case appLaunched

    /// Emitted at most once per local calendar day, carrying the day's rolled-up usage.
    ///
    /// This single event is the spine of the whole measurement: it is DAU by definition, it is the
    /// input to every retention curve, and its payload is the "how much do they use it" answer. A
    /// per-action event stream could in principle produce the same numbers, but only for people who
    /// take actions — this fires for an install that ran all day and was merely *available*, which
    /// for an ambient capture app is the honest baseline.
    case dailyActive(DailyRollup)

    // MARK: - Setup funnel — "where do they fall out"

    /// A permission's state changed, or was observed for the first time this launch.
    ///
    /// The setup funnel is this product's activation story: with no Screen Recording grant it sees
    /// nothing, and with no Accessibility grant the ⌘ + ⌘ gesture is inert while every button in the
    /// app still claims it works. Measuring the grant state is how "people don't know what to do
    /// with it" stops being a guess.
    case permission(Permission, PermissionState)

    /// Onboarding reached a step. Ordinal only — the step *names* are product copy that changes every
    /// release, and a funnel keyed on copy is a funnel that resets every release.
    case onboardingStep(index: Int, of: Int)

    /// How long the whole first run took. Paired with the last `onboardingStep` an install reached,
    /// this is the drop-off curve; on its own it is how long setup costs somebody.
    case onboardingFinished(secondsElapsed: Int)

    /// Whether this install has an Omi account attached. Not who — see the disclosure rule above.
    case accountStateChanged(signedIn: Bool)

    // MARK: - Use — "how much do they use it"

    /// A capture source went live, or stopped being live.
    case captureStateChanged(source: CaptureSource, live: Bool)

    /// The ⌘ + ⌘ gesture fired. The product's one deliberate foreground interaction.
    case gestureFired

    /// A surface the user opened by hand.
    case surfaceOpened(Surface)

    /// A local search ran. Length buckets only, never the query.
    case searchRan(resultCountBucket: CountBucket)

    // MARK: - Health — "does it work for them"

    /// Sparkle's outcome. Update health is invisible without this and an app that silently stops
    /// updating looks identical to an app nobody uses.
    case updateOutcome(UpdateOutcome)

    /// A subsystem took a fail-open path. Mirrors `ContextTelemetry.recordFallback` so the local log
    /// and the remote series describe the same event.
    case fallback(area: ContextFallbackArea, outcome: ContextFallbackOutcome, reason: FallbackReason)

    // MARK: - Closed value types

    /// One case per `Capability`, spelled the same, so the two vocabularies cannot drift. The
    /// mapping is exhaustive in `init(_ capability:)`, which is a compile error the day a capability
    /// is added — the alternative, a `default:`, would silently report a new permission as an old one.
    enum Permission: String, Sendable, CaseIterable {
        case microphone
        case systemAudio
        case screen
        case accessibility

        init(_ capability: Capability) {
            switch capability {
            case .microphone: self = .microphone
            case .systemAudio: self = .systemAudio
            case .screen: self = .screen
            case .accessibility: self = .accessibility
            }
        }
    }

    enum PermissionState: String, Sendable, CaseIterable {
        case granted
        /// Not granted, and never has been. The ordinary "hasn't set it up yet" state.
        case denied
        /// Granted once, gone now. Distinct from `denied` because it means something *broke* — a TCC
        /// reset, or a re-signed build whose code requirement no longer matches the stored record —
        /// rather than that someone said no. Conflating the two would hide a class of failure that
        /// looks exactly like abandonment in the funnel. See `Permissions.grantWasLost`.
        case revoked
    }

    /// The three things this app can be capturing. `CaptureComponent.storage` has no analogue on
    /// purpose — it is bookkeeping, not capture, and reporting it would put a component that is
    /// always live into a series meant to show whether the app is hearing anything.
    enum CaptureSource: String, Sendable, CaseIterable {
        case microphone
        case systemAudio
        case screen

        init?(_ component: CaptureComponent) {
            switch component {
            case .microphone: self = .microphone
            case .systemAudio: self = .systemAudio
            case .screen: self = .screen
            case .storage: return nil
            }
        }
    }

    /// Only surfaces that are actually recorded appear here. A case nobody emits produces a series
    /// that is permanently empty, which reads as "nobody opens it" rather than as "nobody measured
    /// it" — the more dangerous of the two, because it looks like a finding.
    enum Surface: String, Sendable, CaseIterable {
        case menuBar
        case activity
        case settings
        case search
    }

    enum UpdateOutcome: String, Sendable, CaseIterable {
        case checkFailed
        case updateFound
        case installed
        case upToDate
    }

    /// The fixed slugs a fallback may report. Free text here would be the one hole in the closed
    /// vocabulary, and it is the field most likely to have an error message pasted into it.
    enum FallbackReason: String, Sendable, CaseIterable {
        case airgapMode
        case offline
        case unauthorized
        case rateLimited
        case permissionMissing
        case timeout
        case unavailable
        case malformedResponse

        /// Maps the kebab-case slug `ContextTelemetry.recordFallback` receives onto this closed set.
        ///
        /// Returns nil for anything unrecognised, and the caller drops it. That is deliberate: the
        /// local `reason` parameter is a plain `String` held to a convention, so the only thing
        /// standing between a future call site passing `"\(error)"` and an error message reaching
        /// PostHog is this lookup refusing to invent a case for it.
        init?(slug: String) {
            switch slug {
            case "airgap-mode": self = .airgapMode
            case "offline": self = .offline
            case "unauthorized", "401", "403": self = .unauthorized
            case "rate-limited", "429": self = .rateLimited
            case "permission-missing": self = .permissionMissing
            case "timeout": self = .timeout
            case "unavailable": self = .unavailable
            case "malformed-response": self = .malformedResponse
            default: return nil
            }
        }
    }

    /// Counts, bucketed. A raw count of anything a person did is a fingerprint at the tail; a bucket
    /// is an answer to the product question with the tail flattened.
    enum CountBucket: String, Sendable, CaseIterable {
        case zero
        case one
        case few        // 2–5
        case several    // 6–20
        case many       // 21+

        init(_ count: Int) {
            switch count {
            case ..<1: self = .zero
            case 1: self = .one
            case 2...5: self = .few
            case 6...20: self = .several
            default: self = .many
            }
        }
    }

    // MARK: - Wire form

    /// The PostHog event name.
    ///
    /// **Every name is prefixed `cfc_`, and that prefix is load-bearing.** These events land in the
    /// same PostHog project as the Omi macOS app, whose retention, activation and DAU queries are
    /// written against unprefixed names like `App Launched`. An unprefixed event here would silently
    /// enter those numbers and make a four-month macOS trend line jump for no reason anybody could
    /// find. The prefix — plus never setting `$os_name`, see `AnalyticsPayload` — is what keeps two
    /// products in one project from becoming one product in the dashboards.
    var name: String {
        switch self {
        case .firstLaunch: return "cfc_first_launch"
        case .appLaunched: return "cfc_app_launched"
        case .dailyActive: return "cfc_daily_active"
        case .permission: return "cfc_permission"
        case .onboardingStep: return "cfc_onboarding_step"
        case .onboardingFinished: return "cfc_onboarding_finished"
        case .accountStateChanged: return "cfc_account_state"
        case .captureStateChanged: return "cfc_capture_state"
        case .gestureFired: return "cfc_gesture_fired"
        case .surfaceOpened: return "cfc_surface_opened"
        case .searchRan: return "cfc_search_ran"
        case .updateOutcome: return "cfc_update_outcome"
        case .fallback: return "cfc_fallback"
        }
    }

    /// The event's own properties. Super-properties (version, channel, OS) are added by
    /// `AnalyticsPayload`, not here — a call site should never be able to forget them.
    var properties: [String: AnalyticsValue] {
        switch self {
        case .firstLaunch, .appLaunched, .gestureFired:
            return [:]

        case let .dailyActive(rollup):
            return rollup.properties

        case let .permission(permission, state):
            return ["permission": .string(permission.rawValue), "state": .string(state.rawValue)]

        case let .onboardingStep(index, total):
            return ["step_index": .int(index), "step_total": .int(total)]

        case let .onboardingFinished(seconds):
            return ["seconds_elapsed": .int(seconds)]

        case let .accountStateChanged(signedIn):
            return ["signed_in": .bool(signedIn)]

        case let .captureStateChanged(source, live):
            return ["source": .string(source.rawValue), "live": .bool(live)]

        case let .surfaceOpened(surface):
            return ["surface": .string(surface.rawValue)]

        case let .searchRan(bucket):
            return ["result_count": .string(bucket.rawValue)]

        case let .updateOutcome(outcome):
            return ["outcome": .string(outcome.rawValue)]

        case let .fallback(area, outcome, reason):
            return [
                "area": .string(area.rawValue),
                "outcome": .string(outcome.rawValue),
                "reason": .string(reason.rawValue),
            ]
        }
    }
}

/// One local day of use, reported once.
///
/// Everything here is a count or a duration the app already had; nothing is collected *for* this
/// struct. That is deliberate — a rollup that needed its own instrumentation would be a second
/// capture pipeline, and this app does not get a second capture pipeline.
struct DailyRollup: Sendable, Equatable {
    /// Calls Claude made to each MCP tool today, drained from `ToolCallLedger`. **This is the number
    /// the product lives or dies by**: it is the only evidence that the context is actually reaching
    /// a model rather than accumulating on a disk.
    var toolCalls: [String: Int]
    /// Minutes the microphone/system audio was actually capturing.
    var captureMinutes: Int
    /// Minutes screen capture was running.
    var screenMinutes: Int
    /// Distinct hours of the day in which anything at all happened — a coarse "spread across the
    /// day" measure that separates an app left running from an app in use.
    var activeHours: Int
    /// Whether an Omi account was attached at rollup time.
    var signedIn: Bool
    /// Whether Airgap Mode was on. A rollup from an airgapped install never sends at all, so this is
    /// always false in practice; it is here so that if the suppression is ever wrongly relaxed the
    /// evidence is in the payload rather than absent from it.
    var airgapped: Bool

    static let empty = DailyRollup(
        toolCalls: [:], captureMinutes: 0, screenMinutes: 0, activeHours: 0,
        signedIn: false, airgapped: false)

    /// Did anything actually happen? An install that ran all day and captured nothing is still a
    /// DAU, so this is not a send gate — it is a dimension, so "available" and "used" can be told
    /// apart in the same series.
    var isIdle: Bool {
        toolCalls.isEmpty && captureMinutes == 0 && screenMinutes == 0
    }

    var properties: [String: AnalyticsValue] {
        var properties: [String: AnalyticsValue] = [
            "tool_calls_total": .int(toolCalls.values.reduce(0, +)),
            "tool_calls_distinct": .int(toolCalls.count),
            "capture_minutes": .int(captureMinutes),
            "screen_minutes": .int(screenMinutes),
            "active_hours": .int(activeHours),
            "signed_in": .bool(signedIn),
            "airgapped": .bool(airgapped),
            "idle": .bool(isIdle),
        ]
        // One property per tool, so "which tools does Claude actually reach for" is answerable
        // without a second event type. The names come from our own dispatch table and are sanitised
        // by `ToolCallLedger.normalized` before they ever reach this struct.
        for (tool, count) in toolCalls {
            properties["tool_\(tool)"] = .int(count)
        }
        return properties
    }
}

/// The only value shapes that may appear in a payload.
///
/// There is no `.any` case and there will not be one. `[String: Any]` is how a dictionary that was
/// meant to hold three integers ends up holding an `NSError` whose `localizedDescription` is a file
/// path; a closed value type means the compiler asks "which of these is it?" at every call site.
enum AnalyticsValue: Sendable, Equatable {
    case string(String)
    case int(Int)
    case bool(Bool)

    var json: Any {
        switch self {
        case let .string(value): return value
        case let .int(value): return value
        case let .bool(value): return value
        }
    }
}
