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
    gemini_default_for(active_tier())
}

fn gemini_default_for(tier: ModelTier) -> &'static str {
    match tier {
        ModelTier::Standard => "gemini-3-flash-preview",
        ModelTier::Premium => "gemini-3-flash-preview",
    }
}

/// Model for structured extraction tasks (conversations, knowledge graph).
pub fn gemini_extraction() -> &'static str {
    gemini_extraction_for(active_tier())
}

fn gemini_extraction_for(tier: ModelTier) -> &'static str {
    match tier {
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

// MARK: - Rate Limit Thresholds (tier-aware)

/// Daily soft limit — at or above this, Pro requests degrade to Flash.
/// Standard: aggressive (30) since standard already sends Flash.
/// Premium: generous (300) to allow Pro usage.
pub fn daily_soft_limit() -> u32 {
    daily_soft_limit_for(active_tier())
}

fn daily_soft_limit_for(tier: ModelTier) -> u32 {
    match tier {
        ModelTier::Standard => 30,
        ModelTier::Premium => 300,
    }
}

/// Daily hard limit — at or above this, all requests are rejected (429).
pub fn daily_hard_limit() -> u32 {
    daily_hard_limit_for(active_tier())
}

fn daily_hard_limit_for(tier: ModelTier) -> u32 {
    match tier {
        ModelTier::Standard => 500,
        ModelTier::Premium => 1500,
    }
}

/// Tier description for logging.
pub fn tier_description() -> &'static str {
    tier_description_for(active_tier())
}

fn tier_description_for(tier: ModelTier) -> &'static str {
    match tier {
        ModelTier::Standard => "Standard (cost-optimized)",
        ModelTier::Premium => "Premium (quality-optimized)",
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Mutex;

    /// Serialize env-var–mutating tests to avoid races under parallel execution.
    static ENV_LOCK: Mutex<()> = Mutex::new(());

    // --- ModelTier::from_env (serialized — shares process env) ---

    #[test]
    fn from_env_all_cases() {
        let _guard = ENV_LOCK.lock().unwrap();

        // Default (unset) → Standard
        std::env::remove_var("OMI_MODEL_TIER");
        assert_eq!(ModelTier::from_env(), ModelTier::Standard);

        // Explicit premium → Premium
        std::env::set_var("OMI_MODEL_TIER", "premium");
        assert_eq!(ModelTier::from_env(), ModelTier::Premium);

        // Invalid value → Standard fallback
        std::env::set_var("OMI_MODEL_TIER", "garbage");
        assert_eq!(ModelTier::from_env(), ModelTier::Standard);

        // Empty string → Standard fallback
        std::env::set_var("OMI_MODEL_TIER", "");
        assert_eq!(ModelTier::from_env(), ModelTier::Standard);

        std::env::remove_var("OMI_MODEL_TIER");
    }

    // --- gemini_default_for (both tiers) ---

    #[test]
    fn gemini_default_standard_is_flash() {
        assert_eq!(gemini_default_for(ModelTier::Standard), "gemini-3-flash-preview");
    }

    #[test]
    fn gemini_default_premium_is_flash() {
        // Default model is Flash for both tiers (cheap baseline)
        assert_eq!(gemini_default_for(ModelTier::Premium), "gemini-3-flash-preview");
    }

    // --- gemini_extraction_for (the tier-dependent branch) ---

    #[test]
    fn gemini_extraction_standard_is_flash() {
        assert_eq!(gemini_extraction_for(ModelTier::Standard), "gemini-3-flash-preview");
    }

    #[test]
    fn gemini_extraction_premium_is_pro() {
        assert_eq!(gemini_extraction_for(ModelTier::Premium), "gemini-pro-latest");
    }

    // --- tier_description_for ---

    #[test]
    fn tier_description_standard() {
        assert!(tier_description_for(ModelTier::Standard).contains("Standard"));
    }

    #[test]
    fn tier_description_premium() {
        assert!(tier_description_for(ModelTier::Premium).contains("Premium"));
    }

    // --- Static accessors (pinned models) ---

    #[test]
    fn proxy_allowed_contains_expected_models() {
        let allowed = gemini_proxy_allowed();
        assert!(allowed.contains(&"gemini-3-flash-preview"));
        assert!(allowed.contains(&"gemini-pro-latest"));
        assert!(allowed.contains(&"gemini-embedding-001"));
        assert!(!allowed.contains(&"gemini-ultra"));
    }

    #[test]
    fn degrade_target_is_flash() {
        assert_eq!(gemini_degrade_target(), "gemini-3-flash-preview");
    }

    // --- Rate limit thresholds ---

    #[test]
    fn daily_soft_limit_standard_is_lower() {
        assert_eq!(daily_soft_limit_for(ModelTier::Standard), 30);
    }

    #[test]
    fn daily_soft_limit_premium_is_higher() {
        assert_eq!(daily_soft_limit_for(ModelTier::Premium), 300);
    }

    #[test]
    fn daily_hard_limit_standard() {
        assert_eq!(daily_hard_limit_for(ModelTier::Standard), 500);
    }

    #[test]
    fn daily_hard_limit_premium() {
        assert_eq!(daily_hard_limit_for(ModelTier::Premium), 1500);
    }

    #[test]
    fn soft_limit_always_below_hard_limit() {
        for tier in [ModelTier::Standard, ModelTier::Premium] {
            assert!(daily_soft_limit_for(tier) < daily_hard_limit_for(tier));
        }
    }
}
