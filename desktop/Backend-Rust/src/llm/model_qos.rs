// Model QoS Tier System for Rust Backend
//
// Central model configuration with switchable tiers, mirroring the Swift ModelQoS.
// All LlmClient call sites should use these accessors instead of hardcoded model strings.
//
// Tier is read from OMI_MODEL_TIER env var at startup (default: "standard").

use std::sync::OnceLock;

/// Active tier, resolved once from OMI_MODEL_TIER env var.
static ACTIVE_TIER: OnceLock<ModelTier> = OnceLock::new();

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum ModelTier {
    /// Cost-optimized: Flash for all Gemini workloads
    Standard,
    /// Quality-optimized: Pro for structured extraction, Flash for simple tasks
    Premium,
}

impl ModelTier {
    fn from_env() -> Self {
        match std::env::var("OMI_MODEL_TIER").as_deref() {
            Ok("premium") => ModelTier::Premium,
            _ => ModelTier::Standard,
        }
    }
}

/// Get the active model tier (resolved once from env).
pub fn active_tier() -> ModelTier {
    *ACTIVE_TIER.get_or_init(ModelTier::from_env)
}

// MARK: - Gemini Models

/// Default model for LlmClient (used by chat, conversations, personas, knowledge graph).
pub fn gemini_default() -> &'static str {
    match active_tier() {
        ModelTier::Standard => "gemini-3-flash-preview",
        ModelTier::Premium => "gemini-3-flash-preview",
    }
}

/// Model for structured extraction tasks (conversations, knowledge graph).
pub fn gemini_extraction() -> &'static str {
    match active_tier() {
        ModelTier::Standard => "gemini-3-flash-preview",
        ModelTier::Premium => "gemini-pro-latest",
    }
}

/// Allowed models for the Gemini proxy (passthrough from Swift app).
/// These are the models the desktop app is allowed to request.
pub fn gemini_proxy_allowed() -> &'static [&'static str] {
    &[
        "gemini-3-flash-preview",
        "gemini-pro-latest",
        "gemini-embedding-001",
    ]
}

/// Model that rate-limited Pro requests degrade to.
pub fn gemini_degrade_target() -> &'static str {
    "gemini-3-flash-preview"
}

/// Tier description for logging.
pub fn tier_description() -> &'static str {
    match active_tier() {
        ModelTier::Standard => "Standard (cost-optimized)",
        ModelTier::Premium => "Premium (quality-optimized)",
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_tier_is_standard() {
        // Without OMI_MODEL_TIER set, should default to standard
        // (OnceLock may already be initialized, so test the from_env logic directly)
        let tier = ModelTier::from_env();
        // In test environment without the env var, this should be Standard
        assert_eq!(tier, ModelTier::Standard);
    }

    #[test]
    fn test_gemini_default_returns_flash() {
        // Standard tier always uses flash
        assert_eq!(gemini_default(), "gemini-3-flash-preview");
    }

    #[test]
    fn test_proxy_allowed_contains_expected_models() {
        let allowed = gemini_proxy_allowed();
        assert!(allowed.contains(&"gemini-3-flash-preview"));
        assert!(allowed.contains(&"gemini-pro-latest"));
        assert!(allowed.contains(&"gemini-embedding-001"));
        assert!(!allowed.contains(&"gemini-ultra"));
    }

    #[test]
    fn test_degrade_target_is_flash() {
        assert_eq!(gemini_degrade_target(), "gemini-3-flash-preview");
    }
}
