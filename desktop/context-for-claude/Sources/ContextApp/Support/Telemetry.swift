import Foundation

/// Production-health telemetry for Context for Claude.
///
/// Call `recordFallback` whenever the app takes a fail-open path: provider/mode switches,
/// correctness shortcuts, retries, drops, or permission loss. This is the single contract surface;
/// remote telemetry (PostHog/Sentry) can be wired behind it later without touching call sites.
///
/// Sensitive data must never be passed here: areas, modes, and outcomes are closed enums; reasons
/// are short fixed slugs, not user text.
enum ContextFallbackArea: String, Sendable {
    case capture
    case upload
    case mcp
    case auth
    case settings
    case search
    case rewind
}

enum ContextFallbackOutcome: String, Sendable {
    case degraded
    case dropped
    case retried
    case bypassed
}

enum ContextTelemetry {
    /// Records that a component degraded or took a fail-open path.
    ///
    /// - Parameters:
    ///   - area: Which subsystem changed course.
    ///   - from: The expected/normal mode before the fallback.
    ///   - to: The mode actually used.
    ///   - reason: A short fixed slug describing the trigger (no user text, no PII).
    ///   - outcome: Whether the result was degraded, dropped, retried, or bypassed.
    static func recordFallback(
        area: ContextFallbackArea,
        from: String,
        to: String,
        reason: String,
        outcome: ContextFallbackOutcome
    ) {
        ContextLog.info("[fallback] area=\(area.rawValue) from=\(from) to=\(to) reason=\(reason) outcome=\(outcome.rawValue)", "telemetry")
        // Remote telemetry (PostHog/Sentry) requires project-specific credentials and SDKs that
        // are not yet dependencies of this package. The structured log above is the contract; a
        // future provider can read it or be called here without changing callers.
    }
}
