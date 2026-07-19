//! Shared fallback / resilience telemetry for the desktop Rust backend.
//!
//! Same field contract as Python `record_fallback` and Swift
//! `DesktopDiagnosticsManager.recordFallback`. Prometheus is not wired in this
//! service yet, so we emit a fixed-field tracing event that scrapers/log
//! pipelines can aggregate. Call sites must still use this helper — do not
//! invent ad-hoc warn strings for new fallbacks.

pub use omi_desktop_core::fallback::{
    bucket_component, bucket_reason, safe_label, FallbackOutcome,
};

/// Record a fallback / resilience transition.
///
/// Never panics. Unknown components/reasons bucket to `other`.
pub fn record_fallback(
    component: &str,
    from_mode: &str,
    to_mode: &str,
    reason: &str,
    outcome: FallbackOutcome,
) {
    let component = bucket_component(component);
    let from_mode = safe_label(from_mode, "none");
    let to_mode = safe_label(to_mode, "none");
    let reason = bucket_reason(reason);
    tracing::warn!(
        event = "fallback",
        component = %component,
        from = %from_mode,
        to = %to_mode,
        reason = %reason,
        outcome = outcome.as_str(),
        "omi_fallback_event"
    );
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn buckets_unknown_reason_and_component() {
        assert_eq!(bucket_reason("enqueue_failed"), "enqueue_failed");
        assert_eq!(bucket_reason("totally_novel"), "other");
        assert_eq!(bucket_component("gemini_proxy"), "gemini_proxy");
        assert_eq!(bucket_component("brand_new"), "other");
    }

    #[test]
    fn safe_label_normalizes_and_defaults() {
        assert_eq!(safe_label("Cloud Tasks!", "none"), "cloud_tasks_");
        assert_eq!(safe_label("  ", "none"), "none");
        assert_eq!(safe_label("openai", "none"), "openai");
    }

    #[test]
    fn record_fallback_does_not_panic() {
        record_fallback(
            "gemini_proxy",
            "pro",
            "flash",
            "quota",
            FallbackOutcome::Degraded,
        );
        record_fallback("not_real", "", "x", "weird", FallbackOutcome::Exhausted);
    }
}
