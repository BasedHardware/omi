//! Model tier, allowlist, and provider-routing policy.

use std::borrow::Cow;
use std::sync::OnceLock;

static ACTIVE_TIER: OnceLock<ModelTier> = OnceLock::new();

/// Active Omi model tier.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ModelTier {
    /// Cost-optimized tier.
    Premium,
    /// Quality-optimized tier.
    Max,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[cfg_attr(any(target_os = "macos", target_os = "linux"), derive(eqswift::Enum))]
pub enum ModelWorkload {
    ClaudeChat,
    ClaudeFloatingBar,
    ClaudeSynthesis,
    ClaudeChatLabGrade,
    ClaudeChatLabQuery,
    ClaudeDefaultSelection,
    GeminiEmbedding,
    GeminiProactive,
    GeminiTaskExtraction,
    GeminiInsight,
}

impl ModelTier {
    fn from_env() -> Self {
        match std::env::var("OMI_MODEL_TIER").as_deref() {
            Ok("max") => Self::Max,
            _ => Self::Premium,
        }
    }

    /// Resolves a persisted tier value, defaulting to the cost-optimized tier.
    pub fn from_persisted(value: &str) -> Self {
        match value {
            "max" => Self::Max,
            _ => Self::Premium,
        }
    }

    /// Stable lower-case tier identifier.
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Premium => "premium",
            Self::Max => "max",
        }
    }
}

/// LLM provider selected by routing policy.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Provider {
    /// Google Vertex AI.
    VertexAi,
    /// Google AI Studio.
    AiStudio,
}

/// Gets the active tier, resolved once from `OMI_MODEL_TIER`.
pub fn active_tier() -> ModelTier {
    *ACTIVE_TIER.get_or_init(ModelTier::from_env)
}

/// Returns Gemini models accepted by the desktop proxy.
pub const fn gemini_proxy_allowed() -> &'static [&'static str] {
    &[
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-3-flash-preview",
        "gemini-embedding-001",
    ]
}

/// Returns the lowest-cost Gemini degradation target.
pub const fn gemini_degrade_target() -> &'static str {
    "gemini-2.5-flash"
}

const VERTEX_AI_MODELS: &[&str] = &["gemini-2.5-flash", "gemini-2.5-pro", "gemini-embedding-001"];

/// Returns whether a model is available on Vertex AI.
pub fn is_vertex_available(model: &str) -> bool {
    VERTEX_AI_MODELS.contains(&model)
}

/// Required request-body translation for a provider route.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BodyTransform {
    /// Send the body unchanged.
    None,
    /// Translate AI Studio embedding bodies to Vertex prediction bodies.
    EmbedToPredict,
}

/// Required response-body translation for a provider route.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ResponseTransform {
    /// Return the response unchanged.
    None,
    /// Translate Vertex prediction bodies to AI Studio embedding bodies.
    PredictToEmbed,
}

/// Provider routing decision for a model action pair.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProviderRoute {
    /// Provider selected for the request.
    pub provider: Provider,
    /// Vertex action override when its API action differs.
    pub vertex_action: Option<&'static str>,
    /// Request translation required by the route.
    pub request_transform: BodyTransform,
    /// Response translation required by the route.
    pub response_transform: ResponseTransform,
}

/// Resolves provider routing for one model/action pair.
pub fn resolve_route(model: &str, action: &str) -> ProviderRoute {
    if !is_vertex_available(model) {
        return ProviderRoute {
            provider: Provider::AiStudio,
            vertex_action: None,
            request_transform: BodyTransform::None,
            response_transform: ResponseTransform::None,
        };
    }

    match action {
        "embedContent" => ProviderRoute {
            provider: Provider::VertexAi,
            vertex_action: Some("predict"),
            request_transform: BodyTransform::EmbedToPredict,
            response_transform: ResponseTransform::PredictToEmbed,
        },
        "batchEmbedContents" => ProviderRoute {
            provider: Provider::AiStudio,
            vertex_action: None,
            request_transform: BodyTransform::None,
            response_transform: ResponseTransform::None,
        },
        _ => ProviderRoute {
            provider: Provider::VertexAi,
            vertex_action: None,
            request_transform: BodyTransform::None,
            response_transform: ResponseTransform::None,
        },
    }
}

/// Rewrites the retired preview model in a provider request path.
pub fn rewrite_preview_model(path: &str) -> Cow<'_, str> {
    if path.contains("gemini-3-flash-preview") {
        Cow::Owned(path.replace("gemini-3-flash-preview", "gemini-2.5-flash"))
    } else {
        Cow::Borrowed(path)
    }
}

/// Returns tier-specific daily soft limit.
pub fn daily_soft_limit() -> u32 {
    daily_soft_limit_for(active_tier())
}

fn daily_soft_limit_for(tier: ModelTier) -> u32 {
    match tier {
        ModelTier::Premium => 30,
        ModelTier::Max => 300,
    }
}

/// Returns the daily hard limit shared by all tiers.
pub const fn daily_hard_limit() -> u32 {
    1500
}

/// Returns the human-readable active tier description.
pub fn tier_description() -> &'static str {
    tier_description_for(active_tier())
}

/// Returns the human-readable description for a tier.
pub const fn tier_description_for(tier: ModelTier) -> &'static str {
    match tier {
        ModelTier::Premium => "Premium (cost-optimized)",
        ModelTier::Max => "Max (quality-optimized)",
    }
}

/// Returns the stable model identifier for one product workload.
pub const fn model_id_for(tier: ModelTier, workload: ModelWorkload) -> &'static str {
    match workload {
        ModelWorkload::ClaudeChat
        | ModelWorkload::ClaudeFloatingBar
        | ModelWorkload::ClaudeDefaultSelection => "claude-sonnet-4-6",
        ModelWorkload::ClaudeSynthesis | ModelWorkload::ClaudeChatLabGrade => {
            "claude-haiku-4-5-20251001"
        }
        ModelWorkload::ClaudeChatLabQuery => "claude-sonnet-4-20250514",
        ModelWorkload::GeminiEmbedding => "gemini-embedding-001",
        ModelWorkload::GeminiProactive
        | ModelWorkload::GeminiTaskExtraction
        | ModelWorkload::GeminiInsight => match tier {
            ModelTier::Premium => "gemini-2.5-flash",
            ModelTier::Max => "gemini-2.5-pro",
        },
    }
}

#[cfg(test)]
mod tests {
    use super::{
        daily_hard_limit, daily_soft_limit_for, model_id_for, resolve_route, rewrite_preview_model,
        BodyTransform, ModelTier, ModelWorkload, Provider, ResponseTransform,
    };

    #[test]
    fn resolve_route_should_translate_vertex_embeddings() {
        let route = resolve_route("gemini-embedding-001", "embedContent");
        assert_eq!(route.provider, Provider::VertexAi);
        assert_eq!(route.vertex_action, Some("predict"));
        assert_eq!(route.request_transform, BodyTransform::EmbedToPredict);
        assert_eq!(route.response_transform, ResponseTransform::PredictToEmbed);
    }

    #[test]
    fn resolve_route_should_keep_preview_models_on_ai_studio() {
        assert_eq!(
            resolve_route("gemini-3-flash-preview", "generateContent").provider,
            Provider::AiStudio
        );
    }

    #[test]
    fn rewrite_preview_model_should_preserve_the_request_shape() {
        assert_eq!(
            rewrite_preview_model("models/gemini-3-flash-preview:generateContent"),
            "models/gemini-2.5-flash:generateContent"
        );
    }

    #[test]
    fn soft_limits_should_stay_below_the_hard_limit() {
        assert!(daily_soft_limit_for(ModelTier::Premium) < daily_hard_limit());
        assert!(daily_soft_limit_for(ModelTier::Max) < daily_hard_limit());
    }

    #[test]
    fn model_ids_should_match_tier_and_workload_policy() {
        assert_eq!(
            model_id_for(ModelTier::Premium, ModelWorkload::ClaudeChat),
            "claude-sonnet-4-6"
        );
        assert_eq!(
            model_id_for(ModelTier::Premium, ModelWorkload::ClaudeFloatingBar),
            "claude-sonnet-4-6"
        );
        assert_eq!(
            model_id_for(ModelTier::Premium, ModelWorkload::ClaudeDefaultSelection),
            "claude-sonnet-4-6"
        );
        assert_eq!(
            model_id_for(ModelTier::Premium, ModelWorkload::ClaudeChatLabGrade),
            "claude-haiku-4-5-20251001"
        );
        assert_eq!(
            model_id_for(ModelTier::Premium, ModelWorkload::GeminiProactive),
            "gemini-2.5-flash"
        );
        assert_eq!(
            model_id_for(ModelTier::Premium, ModelWorkload::GeminiTaskExtraction),
            "gemini-2.5-flash"
        );
        assert_eq!(
            model_id_for(ModelTier::Premium, ModelWorkload::GeminiInsight),
            "gemini-2.5-flash"
        );
        assert_eq!(
            model_id_for(ModelTier::Max, ModelWorkload::GeminiProactive),
            "gemini-2.5-pro"
        );
        assert_eq!(
            model_id_for(ModelTier::Premium, ModelWorkload::GeminiEmbedding),
            "gemini-embedding-001"
        );
        assert_eq!(
            model_id_for(ModelTier::Max, ModelWorkload::ClaudeSynthesis),
            "claude-haiku-4-5-20251001"
        );
        assert_eq!(
            model_id_for(ModelTier::Max, ModelWorkload::ClaudeChatLabQuery),
            "claude-sonnet-4-20250514"
        );
    }
}
