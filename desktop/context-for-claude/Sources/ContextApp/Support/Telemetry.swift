import Foundation

/// Production-health telemetry for Context for Claude.
///
/// Call `recordFallback` whenever the app takes a fail-open path: provider/mode switches,
/// correctness shortcuts, retries, drops, or permission loss. This is the single contract surface;
/// remote telemetry (PostHog, Sentry) is wired behind it — no call site reaches a sink directly.
///
/// Sensitive data must never be passed here: areas, modes, and outcomes are closed enums; reasons
/// are short fixed slugs, not user text. The sinks inherit that property: the analytics event and
/// the Sentry handled report are both built from these closed values and nothing else.
///
/// **Sinks below this line must consult `NetworkEgress.isSuppressed` before sending, and must not
/// report their own suppression.** `NetworkEgress` reports every Airgap Mode suppression through
/// this function, so a sink that forwarded one would phone home on exactly the machines whose
/// users asked for silence — and it would fire on exactly the machines whose users asked for
/// silence. Each sink owns its refusal (`ContextAnalytics.recordFallback` maps and drops;
/// `ContextSentry.report` re-checks suppression and the admission gate live); this function is the
/// fan-out, not the state authority.
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
            // Crash/error diagnostics, behind the same vocabulary mapping and the same
            // airgap-mode exclusion. `ContextSentry.report` re-checks suppression and the
            // admission gate at send time; the SDK-side whitelist (`ContextSentryPolicy`) is what
            // bounds the payload, and it passes only these closed values through.
            ContextSentry.report(
                ContextSentryHandledReport(area: area, outcome: outcome, reason: mapped))
        }
    }
}
