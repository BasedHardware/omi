// Configuration - Environment variables
// Copied from Python backend .env

use std::env;

/// Application configuration loaded from environment
#[derive(Clone)]
pub struct Config {
    /// Server port
    pub port: u16,
    /// Gemini API key for LLM calls
    pub gemini_api_key: Option<String>,
    /// Google Application Credentials path for Firestore
    pub google_application_credentials: Option<String>,
    /// Firebase project ID
    pub firebase_project_id: Option<String>,
    /// Firebase Web API key (for identity toolkit)
    pub firebase_api_key: Option<String>,
    /// Base API URL (for OAuth callbacks)
    pub base_api_url: Option<String>,
    /// Apple Sign-In Client ID (Services ID)
    pub apple_client_id: Option<String>,
    /// Apple Team ID
    pub apple_team_id: Option<String>,
    /// Apple Key ID (for client secret JWT)
    pub apple_key_id: Option<String>,
    /// Apple Private Key (PEM format)
    pub apple_private_key: Option<String>,
    /// Google OAuth Client ID
    pub google_client_id: Option<String>,
    /// Google OAuth Client Secret
    pub google_client_secret: Option<String>,
    /// Encryption secret for decrypting user data with enhanced protection level
    pub encryption_secret: Option<Vec<u8>>,
    /// Redis host for conversation visibility
    pub redis_host: Option<String>,
    /// Redis port
    pub redis_port: u16,
    /// Redis password
    pub redis_password: Option<String>,
    /// PostHog Personal API Key (for querying analytics)
    pub posthog_api_key: Option<String>,
    /// PostHog Project ID
    pub posthog_project_id: String,
    /// Sentry webhook HMAC-SHA256 secret for signature verification
    pub sentry_webhook_secret: Option<String>,
    /// Sentry API auth token for fetching event details
    pub sentry_auth_token: Option<String>,
    /// Firestore UID where Sentry feedback action items are created
    pub sentry_admin_uid: Option<String>,
    /// Anthropic API key for agent VMs (passed to VMs during provisioning)
    pub agent_anthropic_api_key: Option<String>,
}

impl Config {
    /// Load configuration from environment variables
    pub fn from_env() -> Self {
        Self {
            port: env::var("PORT")
                .ok()
                .and_then(|p| p.parse().ok())
                .unwrap_or(8080),
            gemini_api_key: env::var("GEMINI_API_KEY").ok(),
            google_application_credentials: env::var("GOOGLE_APPLICATION_CREDENTIALS").ok(),
            firebase_project_id: env::var("FIREBASE_PROJECT_ID").ok()
                .or_else(|| env::var("GCP_PROJECT_ID").ok()),
            firebase_api_key: env::var("FIREBASE_API_KEY").ok(),
            base_api_url: env::var("BASE_API_URL").ok(),
            apple_client_id: env::var("APPLE_CLIENT_ID").ok(),
            apple_team_id: env::var("APPLE_TEAM_ID").ok(),
            apple_key_id: env::var("APPLE_KEY_ID").ok(),
            apple_private_key: env::var("APPLE_PRIVATE_KEY").ok(),
            google_client_id: env::var("GOOGLE_CLIENT_ID").ok(),
            google_client_secret: env::var("GOOGLE_CLIENT_SECRET").ok(),
            encryption_secret: env::var("ENCRYPTION_SECRET")
                .ok()
                .map(|s| s.into_bytes()),
            redis_host: env::var("REDIS_DB_HOST").ok(),
            redis_port: env::var("REDIS_DB_PORT")
                .ok()
                .and_then(|p| p.parse().ok())
                .unwrap_or(6379),
            redis_password: env::var("REDIS_DB_PASSWORD").ok(),
            posthog_api_key: env::var("POSTHOG_PERSONAL_API_KEY").ok(),
            posthog_project_id: env::var("POSTHOG_PROJECT_ID")
                .unwrap_or_else(|_| "302298".to_string()),
            sentry_webhook_secret: env::var("SENTRY_WEBHOOK_SECRET").ok(),
            sentry_auth_token: env::var("SENTRY_AUTH_TOKEN").ok(),
            sentry_admin_uid: env::var("SENTRY_ADMIN_UID").ok(),
            agent_anthropic_api_key: env::var("AGENT_ANTHROPIC_API_KEY").ok(),
        }
    }

    /// Validate that required configuration is present
    pub fn validate(&self) -> Result<(), String> {
        if self.google_application_credentials.is_none() {
            tracing::warn!("GOOGLE_APPLICATION_CREDENTIALS not set - Firestore will use default credentials");
        }
        if self.gemini_api_key.is_none() {
            tracing::warn!("GEMINI_API_KEY not set - conversation processing will fail");
        }
        if self.redis_host.is_none() {
            tracing::warn!("REDIS_DB_HOST not set - conversation visibility/sharing will not work");
        }
        if self.encryption_secret.is_none() {
            tracing::warn!("ENCRYPTION_SECRET not set — encrypted user data will not be decryptable");
        }
        Ok(())
    }

    /// Get Redis connection URL
    pub fn redis_url(&self) -> Option<String> {
        self.redis_host.as_ref().map(|host| {
            if let Some(password) = &self.redis_password {
                // URL-encode the password to handle special characters
                let encoded_password = urlencoding::encode(password);
                format!("redis://default:{}@{}:{}", encoded_password, host, self.redis_port)
            } else {
                format!("redis://{}:{}", host, self.redis_port)
            }
        })
    }
}
