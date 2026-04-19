// Model QoS Tier System for Rust Backend
//
// Central model configuration with switchable tiers, mirroring the Swift ModelQoS.
// All LlmClient call sites should use these accessors instead of hardcoded model strings.
//
// Tier is read from OMI_MODEL_TIER env var at startup (default: "premium").

use std::sync::OnceLock;

/// Active tier, resolved once from OMI_MODEL_TIER env var.
static ACTIVE_TIER: OnceLock<ModelTier> = OnceLock::new();

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum ModelTier {
    /// Cost-optimized: Flash for all Gemini workloads, lower rate limits
    Premium,
    /// Quality-optimized: same models, higher rate limits
    Max,
}

impl ModelTier {
    fn from_env() -> Self {
        match std::env::var("OMI_MODEL_TIER").as_deref() {
            Ok("max") => ModelTier::Max,
            _ => ModelTier::Premium,
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
    gemini_default_for(active_tier())
}

fn gemini_default_for(tier: ModelTier) -> &'static str {
    match tier {
        ModelTier::Premium => "gemini-3-flash-preview",
        ModelTier::Max => "gemini-3-flash-preview",
    }
}

/// Model for structured extraction tasks (conversations, knowledge graph).
pub fn gemini_extraction() -> &'static str {
    gemini_extraction_for(active_tier())
}

fn gemini_extraction_for(_tier: ModelTier) -> &'static str {
    "gemini-3-flash-preview"
}

/// Allowed models for the Gemini proxy (passthrough from Swift app).
/// These are the models the desktop app is allowed to request.
pub fn gemini_proxy_allowed() -> &'static [&'static str] {
    &[
        "gemini-3-flash-preview",
        "gemini-embedding-001",
    ]
}

/// Model that rate-limited Pro requests degrade to.
pub fn gemini_degrade_target() -> &'static str {
    "gemini-3-flash-preview"
}

// MARK: - Rate Limit Thresholds (tier-aware)

/// Daily soft limit — at or above this, Pro requests degrade to Flash.
/// Premium: aggressive (30) since premium already sends Flash.
/// Max: generous (300) to allow Pro usage.
pub fn daily_soft_limit() -> u32 {
    daily_soft_limit_for(active_tier())
}

fn daily_soft_limit_for(tier: ModelTier) -> u32 {
    match tier {
        ModelTier::Premium => 30,
        ModelTier::Max => 300,
    }
}

/// Daily hard limit — at or above this, all requests are rejected (429).
pub fn daily_hard_limit() -> u32 {
    daily_hard_limit_for(active_tier())
}

fn daily_hard_limit_for(_tier: ModelTier) -> u32 {
    1500
}

/// Tier description for logging.
pub fn tier_description() -> &'static str {
    tier_description_for(active_tier())
}

fn tier_description_for(tier: ModelTier) -> &'static str {
    match tier {
        ModelTier::Premium => "Premium (cost-optimized)",
        ModelTier::Max => "Max (quality-optimized)",
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Mutex;

    /// Serialize env-var-mutating tests to avoid races under parallel execution.
    static ENV_LOCK: Mutex<()> = Mutex::new(());

    // --- ModelTier::from_env (serialized — shares process env) ---

    #[test]
    fn from_env_all_cases() {
        let _guard = ENV_LOCK.lock().unwrap();

        // Default (unset) → Premium
        std::env::remove_var("OMI_MODEL_TIER");
        assert_eq!(ModelTier::from_env(), ModelTier::Premium);

        // Explicit max → Max
        std::env::set_var("OMI_MODEL_TIER", "max");
        assert_eq!(ModelTier::from_env(), ModelTier::Max);

        // Invalid value → Premium fallback
        std::env::set_var("OMI_MODEL_TIER", "garbage");
        assert_eq!(ModelTier::from_env(), ModelTier::Premium);

        // Empty string → Premium fallback
        std::env::set_var("OMI_MODEL_TIER", "");
        assert_eq!(ModelTier::from_env(), ModelTier::Premium);

        std::env::remove_var("OMI_MODEL_TIER");
    }

    // --- gemini_default_for (both tiers) ---

    #[test]
    fn gemini_default_premium_is_flash() {
        assert_eq!(gemini_default_for(ModelTier::Premium), "gemini-3-flash-preview");
    }

    #[test]
    fn gemini_default_max_is_flash() {
        // Default model is Flash for both tiers (cheap baseline)
        assert_eq!(gemini_default_for(ModelTier::Max), "gemini-3-flash-preview");
    }

    // --- gemini_extraction_for (the tier-dependent branch) ---

    #[test]
    fn gemini_extraction_is_flash_for_both_tiers() {
        assert_eq!(gemini_extraction_for(ModelTier::Premium), "gemini-3-flash-preview");
        assert_eq!(gemini_extraction_for(ModelTier::Max), "gemini-3-flash-preview");
    }

    // --- tier_description_for ---

    #[test]
    fn tier_description_premium() {
        assert!(tier_description_for(ModelTier::Premium).contains("Premium"));
    }

    #[test]
    fn tier_description_max() {
        assert!(tier_description_for(ModelTier::Max).contains("Max"));
    }

    // --- Static accessors (pinned models) ---

    #[test]
    fn proxy_allowed_contains_expected_models() {
        let allowed = gemini_proxy_allowed();
        assert!(allowed.contains(&"gemini-3-flash-preview"));
        assert!(allowed.contains(&"gemini-embedding-001"));
        assert!(!allowed.contains(&"gemini-pro-latest"), "pro removed from allowlist");
        assert!(!allowed.contains(&"gemini-ultra"));
    }

    #[test]
    fn degrade_target_is_flash() {
        assert_eq!(gemini_degrade_target(), "gemini-3-flash-preview");
    }

    // --- Rate limit thresholds ---

    #[test]
    fn daily_soft_limit_premium_is_lower() {
        assert_eq!(daily_soft_limit_for(ModelTier::Premium), 30);
    }

    #[test]
    fn daily_soft_limit_max_is_higher() {
        assert_eq!(daily_soft_limit_for(ModelTier::Max), 300);
    }

    #[test]
    fn daily_hard_limit_same_for_both_tiers() {
        assert_eq!(daily_hard_limit_for(ModelTier::Premium), 1500);
        assert_eq!(daily_hard_limit_for(ModelTier::Max), 1500);
    }

    #[test]
    fn soft_limit_always_below_hard_limit() {
        for tier in [ModelTier::Premium, ModelTier::Max] {
            assert!(daily_soft_limit_for(tier) < daily_hard_limit_for(tier));
        }
    }
}
