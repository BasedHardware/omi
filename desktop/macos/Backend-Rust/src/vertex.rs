// Vertex AI authentication and URL builder.
//
// When USE_VERTEX_AI=true, Gemini calls route through Vertex AI endpoints
// with service account Bearer auth instead of AI Studio API key auth.
//
// Auth: gcp_auth reads GOOGLE_APPLICATION_CREDENTIALS (service account JSON)
// and handles token caching + automatic refresh internally.

use std::sync::Arc;

const VERTEX_AI_SCOPE: &str = "https://www.googleapis.com/auth/cloud-platform";

/// Vertex AI auth provider. Wraps gcp_auth for token management.
/// gcp_auth handles caching and refresh internally — we don't add our own cache.
#[derive(Clone)]
pub struct VertexAuth {
    provider: Arc<dyn gcp_auth::TokenProvider>,
    pub project_id: String,
    pub location: String,
}

impl VertexAuth {
    /// Initialize from Application Default Credentials (GOOGLE_APPLICATION_CREDENTIALS).
    pub async fn new(
        project_id: String,
        location: String,
    ) -> Result<Self, Box<dyn std::error::Error + Send + Sync>> {
        let provider = gcp_auth::provider().await.map_err(|e| {
            format!(
                "Failed to initialize GCP auth (check GOOGLE_APPLICATION_CREDENTIALS): {}",
                e
            )
        })?;

        Ok(Self {
            provider: provider.into(),
            project_id,
            location,
        })
    }

    /// Get a valid bearer token. gcp_auth handles caching and refresh.
    pub async fn token(&self) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
        let token = self
            .provider
            .token(&[VERTEX_AI_SCOPE])
            .await
            .map_err(|e| format!("Failed to get Vertex AI token: {}", e))?;
        Ok(token.as_str().to_string())
    }

    /// Build Vertex AI URL for a Gemini model action.
    pub fn build_url(&self, model: &str, action: &str) -> String {
        build_vertex_url(&self.project_id, &self.location, model, action)
    }

    /// Build Vertex AI URL from an AI Studio-style path like "models/gemini-2.5-flash:generateContent".
    /// Returns the full Vertex AI URL, or None if the path can't be parsed.
    pub fn build_url_from_path(&self, path: &str) -> Option<String> {
        let (model, action) = parse_ai_studio_path(path)?;
        Some(self.build_url(model, action))
    }
}

/// Build a Vertex AI URL from components.
///
/// `https://{location}-aiplatform.googleapis.com/v1/projects/{project}/locations/{location}/publishers/google/models/{model}:{action}`
fn build_vertex_url(project: &str, location: &str, model: &str, action: &str) -> String {
    format!(
        "https://{location}-aiplatform.googleapis.com/v1/projects/{project}/locations/{location}/publishers/google/models/{model}:{action}",
        location = location,
        project = project,
        model = model,
        action = action,
    )
}

/// Parse an AI Studio-style path ("models/{model}:{action}") into (model, action).
fn parse_ai_studio_path(path: &str) -> Option<(&str, &str)> {
    let rest = path.strip_prefix("models/")?;
    rest.split_once(':')
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn build_url_generates_correct_vertex_endpoint() {
        let url = build_vertex_url("my-project", "us-central1", "gemini-2.5-flash", "generateContent");
        assert_eq!(
            url,
            "https://us-central1-aiplatform.googleapis.com/v1/projects/my-project/locations/us-central1/publishers/google/models/gemini-2.5-flash:generateContent"
        );
    }

    #[test]
    fn build_url_embedding_model() {
        let url = build_vertex_url("my-project", "us-central1", "gemini-embedding-001", "embedContent");
        assert!(url.contains("gemini-embedding-001:embedContent"));
        assert!(url.contains("/projects/my-project/"));
    }

    #[test]
    fn build_url_stream_action() {
        let url = build_vertex_url("my-project", "us-central1", "gemini-2.5-flash", "streamGenerateContent");
        assert!(url.contains("streamGenerateContent"));
    }

    #[test]
    fn build_url_custom_location() {
        let url = build_vertex_url("prod-project", "europe-west4", "gemini-2.5-flash", "generateContent");
        assert!(url.starts_with("https://europe-west4-aiplatform.googleapis.com/"));
        assert!(url.contains("/projects/prod-project/"));
        assert!(url.contains("/locations/europe-west4/"));
    }

    #[test]
    fn parse_path_generates_content() {
        let (model, action) = parse_ai_studio_path("models/gemini-2.5-flash:generateContent").unwrap();
        assert_eq!(model, "gemini-2.5-flash");
        assert_eq!(action, "generateContent");
        let url = build_vertex_url("p", "us-central1", model, action);
        assert!(url.contains("gemini-2.5-flash:generateContent"));
    }

    #[test]
    fn parse_path_embedding() {
        let (model, action) = parse_ai_studio_path("models/gemini-embedding-001:embedContent").unwrap();
        assert_eq!(model, "gemini-embedding-001");
        assert_eq!(action, "embedContent");
    }

    #[test]
    fn parse_path_stream() {
        let (model, action) = parse_ai_studio_path("models/gemini-2.5-flash:streamGenerateContent").unwrap();
        assert_eq!(model, "gemini-2.5-flash");
        assert_eq!(action, "streamGenerateContent");
    }

    #[test]
    fn parse_path_rejects_no_prefix() {
        assert!(parse_ai_studio_path("gemini-2.5-flash:generateContent").is_none());
    }

    #[test]
    fn parse_path_rejects_no_colon() {
        assert!(parse_ai_studio_path("models/gemini-2.5-flash").is_none());
    }

    #[test]
    fn parse_path_rejects_empty() {
        assert!(parse_ai_studio_path("").is_none());
    }

    #[test]
    fn build_url_batch_embed() {
        let url = build_vertex_url("p", "us-central1", "gemini-embedding-001", "batchEmbedContents");
        assert!(url.contains("batchEmbedContents"));
    }
}
