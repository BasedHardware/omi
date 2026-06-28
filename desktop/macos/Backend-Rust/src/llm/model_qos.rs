// Model QoS Tier System for Rust Backend
//
// Central model configuration with switchable tiers, mirroring the Swift ModelQoS.
// All LlmClient call sites should use these accessors instead of hardcoded model strings.
//
// Design follows yuki's Python QoS pattern (backend/utils/llm/clients.py):
//   feature → (model, provider)
// Provider is explicit data, not inferred from model name. One dispatch point.
//
// Tier is read from OMI_MODEL_TIER env var at startup (default: "premium").

use std::sync::OnceLock;

/// Active tier, resolved once from OMI_MODEL_TIER env var.
static ACTIVE_TIER: OnceLock<ModelTier> = OnceLock::new();

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum ModelTier {
    /// Cost-optimized: Flash for Gemini, lower rate limits
    Premium,
    /// Quality-optimized: Pro for Gemini, higher rate limits
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

/// LLM provider for routing decisions.
/// Provider is data (in the profile), not scattered if-else logic.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Provider {
    /// Google Vertex AI (Bearer token auth, SA credentials)
    VertexAi,
    /// Google AI Studio (API key auth)
    AiStudio,
}

/// Get the active model tier (resolved once from env).
pub fn active_tier() -> ModelTier {
    *ACTIVE_TIER.get_or_init(ModelTier::from_env)
}

// MARK: - Gemini Models

/// Allowed models for the Gemini proxy (passthrough from Swift app).
/// These are the models the desktop app is allowed to request.
/// Includes gemini-3-flash-preview for backwards compatibility with older app versions
/// that have it hardcoded — those requests route to AI Studio (not Vertex AI).
pub fn gemini_proxy_allowed() -> &'static [&'static str] {
    &[
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-3-flash-preview",
        "gemini-embedding-001",
    ]
}

/// Model that rate-limited requests degrade to (always cheapest flash).
pub fn gemini_degrade_target() -> &'static str {
    "gemini-2.5-flash"
}

// MARK: - Provider Routing (model → provider)

/// Models available on Vertex AI (GA, confirmed working on based-hardware-dev).
/// Models NOT in this list must route through AI Studio even when USE_VERTEX_AI=true.
/// Note: gemini-embedding-001 uses `:predict` action on Vertex (not `:embedContent`),
/// and requires request/response body transformation — handled in the proxy.
const VERTEX_AI_MODELS: &[&str] = &[
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-embedding-001",
];

/// Check if a model is available on Vertex AI.
/// Used by the proxy to decide routing: Vertex AI vs AI Studio.
pub fn is_vertex_available(model: &str) -> bool {
    VERTEX_AI_MODELS.contains(&model)
}

// MARK: - Provider Route (model + action → routing decision)
//
// Centralizes all provider-specific behavior for a (model, action) pair.
// The proxy handler calls resolve_route() once and gets everything it needs:
// which provider, what Vertex action to use, whether body transforms are needed.
// No scattered if-else in the proxy — provider differences are data here.

/// How the request body should be transformed for the target provider.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum BodyTransform {
    /// Send body as-is (AI Studio format works on both providers for this action)
    None,
    /// Embedding: AI Studio embedContent body → Vertex AI predict body
    EmbedToPredict,
}

/// How the response body should be transformed back for the client.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum ResponseTransform {
    /// Return response as-is
    None,
    /// Embedding: Vertex AI predict response → AI Studio embedContent response
    PredictToEmbed,
}

/// Resolved routing decision for a (model, action) pair.
#[derive(Debug, Clone, PartialEq)]
pub struct ProviderRoute {
    /// Which provider to use
    pub provider: Provider,
    /// Vertex AI action override (e.g., "predict" instead of "embedContent").
    /// None means use the original action.
    pub vertex_action: Option<&'static str>,
    /// Request body transformation
    pub request_transform: BodyTransform,
    /// Response body transformation
    pub response_transform: ResponseTransform,
}

/// Resolve the provider route for a (model, action) pair.
///
/// This is the single dispatch point for all provider-specific behavior.
/// The proxy calls this once and follows the returned ProviderRoute.
pub fn resolve_route(model: &str, action: &str) -> ProviderRoute {
    // Models not on Vertex AI → always AI Studio, no transforms
    if !is_vertex_available(model) {
        return ProviderRoute {
            provider: Provider::AiStudio,
            vertex_action: None,
            request_transform: BodyTransform::None,
            response_transform: ResponseTransform::None,
        };
    }

    match action {
        // Single embed: Vertex AI uses :predict with different body format
        "embedContent" => ProviderRoute {
            provider: Provider::VertexAi,
            vertex_action: Some("predict"),
            request_transform: BodyTransform::EmbedToPredict,
            response_transform: ResponseTransform::PredictToEmbed,
        },
        // Batch embed: Vertex AI only supports single text, stay on AI Studio
        "batchEmbedContents" => ProviderRoute {
            provider: Provider::AiStudio,
            vertex_action: None,
            request_transform: BodyTransform::None,
            response_transform: ResponseTransform::None,
        },
        // All other actions (generateContent, streamGenerateContent): Vertex AI, no transforms
        _ => ProviderRoute {
            provider: Provider::VertexAi,
            vertex_action: None,
            request_transform: BodyTransform::None,
            response_transform: ResponseTransform::None,
        },
    }
}

/// Rewrite a preview model to its stable equivalent.
/// Old desktop app versions hardcode gemini-3-flash-preview — rewrite to gemini-2.5-flash.
pub fn rewrite_preview_model(path: &str) -> std::borrow::Cow<'_, str> {
    if path.contains("gemini-3-flash-preview") {
        std::borrow::Cow::Owned(path.replace("gemini-3-flash-preview", "gemini-2.5-flash"))
    } else {
        std::borrow::Cow::Borrowed(path)
    }
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

    // --- tier_description_for ---

    #[test]
    fn tier_description_premium() {
        assert!(tier_description_for(ModelTier::Premium).contains("Premium"));
    }

    #[test]
    fn tier_description_max() {
        assert!(tier_description_for(ModelTier::Max).contains("Max"));
    }

    // --- Proxy allowlist ---

    #[test]
    fn proxy_allowed_contains_expected_models() {
        let allowed = gemini_proxy_allowed();
        assert!(allowed.contains(&"gemini-2.5-flash"));
        assert!(allowed.contains(&"gemini-2.5-pro"));
        assert!(allowed.contains(&"gemini-3-flash-preview"), "kept for old app compat");
        assert!(allowed.contains(&"gemini-embedding-001"));
        assert!(!allowed.contains(&"gemini-pro-latest"), "legacy pro not in allowlist");
        assert!(!allowed.contains(&"gemini-ultra"));
    }

    #[test]
    fn degrade_target_is_flash() {
        assert_eq!(gemini_degrade_target(), "gemini-2.5-flash");
    }

    // --- Provider routing ---

    #[test]
    fn vertex_available_for_stable_models() {
        assert!(is_vertex_available("gemini-2.5-flash"));
        assert!(is_vertex_available("gemini-2.5-pro"));
        assert!(is_vertex_available("gemini-embedding-001"));
    }

    #[test]
    fn vertex_not_available_for_preview() {
        assert!(!is_vertex_available("gemini-3-flash-preview"));
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

    // --- ProviderRoute resolution ---

    #[test]
    fn route_flash_generate_content() {
        let route = resolve_route("gemini-2.5-flash", "generateContent");
        assert_eq!(route.provider, Provider::VertexAi);
        assert_eq!(route.vertex_action, None);
        assert_eq!(route.request_transform, BodyTransform::None);
        assert_eq!(route.response_transform, ResponseTransform::None);
    }

    #[test]
    fn route_pro_stream_generate_content() {
        let route = resolve_route("gemini-2.5-pro", "streamGenerateContent");
        assert_eq!(route.provider, Provider::VertexAi);
        assert_eq!(route.vertex_action, None);
        assert_eq!(route.request_transform, BodyTransform::None);
    }

    #[test]
    fn route_embed_content_uses_predict() {
        let route = resolve_route("gemini-embedding-001", "embedContent");
        assert_eq!(route.provider, Provider::VertexAi);
        assert_eq!(route.vertex_action, Some("predict"));
        assert_eq!(route.request_transform, BodyTransform::EmbedToPredict);
        assert_eq!(route.response_transform, ResponseTransform::PredictToEmbed);
    }

    #[test]
    fn route_batch_embed_stays_ai_studio() {
        let route = resolve_route("gemini-embedding-001", "batchEmbedContents");
        assert_eq!(route.provider, Provider::AiStudio);
        assert_eq!(route.vertex_action, None);
        assert_eq!(route.request_transform, BodyTransform::None);
    }

    #[test]
    fn route_preview_model_goes_to_ai_studio() {
        let route = resolve_route("gemini-3-flash-preview", "generateContent");
        assert_eq!(route.provider, Provider::AiStudio);
        assert_eq!(route.request_transform, BodyTransform::None);
    }

    // --- Preview model rewrite ---

    #[test]
    fn rewrite_preview_to_flash() {
        assert_eq!(
            rewrite_preview_model("models/gemini-3-flash-preview:generateContent"),
            "models/gemini-2.5-flash:generateContent"
        );
    }

    #[test]
    fn rewrite_preserves_stable_models() {
        let path = "models/gemini-2.5-flash:generateContent";
        assert_eq!(rewrite_preview_model(path), path);
    }

    #[test]
    fn rewrite_preserves_pro() {
        let path = "models/gemini-2.5-pro:streamGenerateContent";
        assert_eq!(rewrite_preview_model(path), path);
    }
}
