//! Shared fallback / resilience telemetry for the desktop Rust backend.
//!
//! Same field contract as Python `record_fallback` and Swift
//! `DesktopDiagnosticsManager.recordFallback`. Prometheus is not wired in this
//! service yet, so we emit a fixed-field tracing event that scrapers/log
//! pipelines can aggregate. Call sites must still use this helper — do not
//! invent ad-hoc warn strings for new fallbacks.

/// Closed outcome set matching the cross-platform contract.
#[allow(dead_code)] // Recovered/Exhausted used by call sites in later phases
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FallbackOutcome {
    Recovered,
    Degraded,
    Exhausted,
}

impl FallbackOutcome {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Recovered => "recovered",
            Self::Degraded => "degraded",
            Self::Exhausted => "exhausted",
        }
    }
}

const ALLOWED_COMPONENTS: &[&str] = &[
    "sync_dispatch",
    "pusher",
    "stt_selection",
    "vad",
    "audio_merge",
    "webhook",
    "realtime_hub",
    "ptt_cascade",
    "gemini_model",
    "gemini_proxy",
    "redis_ratelimit",
    "silent_mic",
    "other",
];

const ALLOWED_REASONS: &[&str] = &[
    "timeout",
    "provider_5xx",
    "provider_429",
    "enqueue_failed",
    "config_incomplete",
    "circuit_open",
    "capability_mismatch",
    "auth",
    "quota",
    "local_heal",
    "policy",
    "dispatch_disabled",
    "byok",
    "other",
    "none",
];

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

pub fn bucket_reason(reason: &str) -> String {
    let label = safe_label(reason, "other");
    if ALLOWED_REASONS.contains(&label.as_str()) {
        label
    } else {
        "other".to_string()
    }
}

pub fn bucket_component(component: &str) -> String {
    let label = safe_label(component, "other");
    if ALLOWED_COMPONENTS.contains(&label.as_str()) {
        label
    } else {
        "other".to_string()
    }
}

pub fn safe_label(value: &str, default: &str) -> String {
    let trimmed = value.trim().to_ascii_lowercase();
    let source = if trimmed.is_empty() {
        default
    } else {
        trimmed.as_str()
    };
    let normalized: String = source
        .chars()
        .map(|ch| {
            if ch.is_ascii_alphanumeric() || matches!(ch, '.' | '_' | ':' | '-') {
                ch
            } else {
                '_'
            }
        })
        .collect();
    let clipped: String = normalized.chars().take(64).collect();
    if clipped.is_empty() {
        default.to_string()
    } else {
        clipped
    }
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
