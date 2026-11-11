import Foundation

/// Production-health telemetry for Context for Claude.
///
/// Call `recordFallback` whenever the app takes a fail-open path: provider/mode switches,
/// correctness shortcuts, retries, drops, or permission loss. This is the single contract surface;
/// remote telemetry (PostHog/Sentry) can be wired behind it later without touching call sites.
///
/// Sensitive data must never be passed here: areas, modes, and outcomes are closed enums; reasons
/// are short fixed slugs, not user text.
///
/// **This helper does not egress, and a future remote sink must keep it that way.** `ContextLog`
/// writes to `os.Logger` and, only under `CONTEXT_DEBUG=1`, to a local file; nothing here opens a
/// socket. That is load-bearing rather than incidental: `NetworkEgress` reports every Airgap Mode
/// suppression through this function, so a telemetry client wired in below that phoned home would
/// turn the airgap guard itself into the disclosure it exists to prevent — and it would fire on
/// exactly the machines whose users asked for silence. Anything added here must consult
/// `NetworkEgress.isSuppressed` before sending, and must not report its own suppression.
enum ContextFallbackArea: String, Sendable, CaseIterable {
    case capture
    case upload
    case mcp
    case auth
    case settings
    case search
    case rewind
}

enum ContextFallbackOutcome: String, Sendable, CaseIterable {
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

        // The remote half. Only reasons that map to a known slug are forwarded — `reason` is a
        // convention-enforced string here, and the analytics vocabulary is closed, so an unmapped
        // slug is dropped rather than smuggled through as free text.
        //
        // **`airgap-mode` is excluded, and that exclusion is load-bearing twice over.** It is the
        // invariant this type was written with: `NetworkEgress` reports every Airgap Mode
        // suppression through here, so forwarding one would phone home on exactly the machines whose
        // users asked for silence. It is *also* the cycle breaker — `ContextAnalytics.record`
        // reports its own airgap refusal through `NetworkEgress.recordSuppression`, which calls
        // this function, which would call `record` again. See `ContextAnalytics.recordFallback`.
        if let mapped = AnalyticsEvent.FallbackReason(slug: reason), mapped != .airgapMode {
            ContextAnalytics.recordFallback(area: area, outcome: outcome, reason: mapped)
        }
        // Remote telemetry (PostHog/Sentry) requires project-specific credentials and SDKs that
        // are not yet dependencies of this package. The structured log above is the contract; a
        // future provider can read it or be called here without changing callers — but only behind
        // `NetworkEgress.isSuppressed`, for the reason in this type's documentation. Until then the
        // Settings row's "no telemetry leaves this Mac" is true unconditionally, not just in Airgap
        // Mode, which is why that row no longer claims to suppress telemetry.
    }
}
