//! Shared fallback-label normalization.

/// Closed fallback outcome set shared by desktop hosts.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FallbackOutcome {
    /// Primary path recovered after a fallback.
    Recovered,
    /// A lower-quality path completed.
    Degraded,
    /// No fallback path completed.
    Exhausted,
}

impl FallbackOutcome {
    /// Stable telemetry value for this outcome.
    pub const fn as_str(self) -> &'static str {
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
    "chat_retrieval",
    "gemini_model",
    "gemini_proxy",
    "gemini_stream_proxy",
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

/// Maps unknown reasons into the stable `other` bucket.
pub fn bucket_reason(reason: &str) -> String {
    let label = safe_label(reason, "other");
    if ALLOWED_REASONS.contains(&label.as_str()) {
        label
    } else {
        "other".to_owned()
    }
}

/// Maps unknown components into the stable `other` bucket.
pub fn bucket_component(component: &str) -> String {
    let label = safe_label(component, "other");
    if ALLOWED_COMPONENTS.contains(&label.as_str()) {
        label
    } else {
        "other".to_owned()
    }
}

/// Normalizes a bounded telemetry label without retaining unsafe characters.
pub fn safe_label(value: &str, default: &str) -> String {
    let trimmed = value.trim().to_ascii_lowercase();
    let source = if trimmed.is_empty() {
        default
    } else {
        &trimmed
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
        .take(64)
        .collect();
    if normalized.is_empty() {
        default.to_owned()
    } else {
        normalized
    }
}

#[cfg(test)]
mod tests {
    use super::{bucket_component, bucket_reason, safe_label};

    #[test]
    fn safe_label_should_normalize_and_bound_untrusted_input() {
        assert_eq!(safe_label("Cloud Tasks!", "none"), "cloud_tasks_");
        assert_eq!(safe_label(" ", "none"), "none");
        assert_eq!(safe_label(&"a".repeat(65), "none"), "a".repeat(64));
    }

    #[test]
    fn buckets_should_preserve_known_values_and_hide_unknown_ones() {
        assert_eq!(bucket_reason("enqueue_failed"), "enqueue_failed");
        assert_eq!(bucket_reason("novel"), "other");
        assert_eq!(bucket_component("gemini_proxy"), "gemini_proxy");
        assert_eq!(bucket_component("novel"), "other");
    }
}
