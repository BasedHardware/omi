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
    /// Crisp plugin identifier (for REST API authentication)
    pub crisp_plugin_identifier: Option<String>,
    /// Crisp plugin key (for REST API authentication)
    pub crisp_plugin_key: Option<String>,
    /// Crisp website ID
    pub crisp_website_id: Option<String>,
    /// Pinecone API key for vector embeddings
    pub pinecone_api_key: Option<String>,
    /// Pinecone host URL (e.g. https://index-name-xxx.svc.environment.pinecone.io)
    pub pinecone_host: Option<String>,
    /// GCE project ID for AgentVM provisioning (defaults to "based-hardware-dev")
    pub gce_project_id: String,
    /// GCE source image for AgentVM (defaults to "projects/{gce_project_id}/global/images/family/omi-agent")
    pub gce_source_image: String,
    /// GCS bucket for agent startup script (defaults to "based-hardware-agent")
    pub agent_gcs_bucket: String,
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
            crisp_plugin_identifier: env::var("CRISP_PLUGIN_IDENTIFIER").ok(),
            crisp_plugin_key: env::var("CRISP_PLUGIN_KEY").ok(),
            crisp_website_id: env::var("CRISP_WEBSITE_ID").ok(),
            pinecone_api_key: env::var("PINECONE_API_KEY").ok(),
            pinecone_host: env::var("PINECONE_HOST").ok(),
            gce_project_id: {
                let p = env::var("GCE_PROJECT_ID")
                    .or_else(|_| env::var("FIREBASE_PROJECT_ID"))
                    .or_else(|_| env::var("GCP_PROJECT_ID"))
                    .unwrap_or_else(|_| "based-hardware-dev".to_string());
                p
            },
            gce_source_image: {
                let gce_proj = env::var("GCE_PROJECT_ID")
                    .or_else(|_| env::var("FIREBASE_PROJECT_ID"))
                    .or_else(|_| env::var("GCP_PROJECT_ID"))
                    .unwrap_or_else(|_| "based-hardware-dev".to_string());
                env::var("GCE_SOURCE_IMAGE")
                    .unwrap_or_else(|_| format!("projects/{}/global/images/family/omi-agent", gce_proj))
            },
            agent_gcs_bucket: env::var("AGENT_GCS_BUCKET")
                .unwrap_or_else(|_| "based-hardware-dev-agent".to_string()),
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

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Mutex;

    // Env var tests must run serially to avoid races
    static ENV_LOCK: Mutex<()> = Mutex::new(());

    fn clear_config_env_vars() {
        for key in &[
            "PORT", "GEMINI_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS",
            "FIREBASE_PROJECT_ID", "FIREBASE_API_KEY", "GCP_PROJECT_ID",
            "GCE_PROJECT_ID", "GCE_SOURCE_IMAGE", "AGENT_GCS_BUCKET",
            "BASE_API_URL", "APPLE_CLIENT_ID", "APPLE_TEAM_ID",
            "APPLE_KEY_ID", "APPLE_PRIVATE_KEY", "GOOGLE_CLIENT_ID",
            "GOOGLE_CLIENT_SECRET", "ENCRYPTION_SECRET", "REDIS_DB_HOST",
            "REDIS_DB_PORT", "REDIS_DB_PASSWORD", "POSTHOG_PERSONAL_API_KEY",
            "POSTHOG_PROJECT_ID", "SENTRY_WEBHOOK_SECRET", "SENTRY_AUTH_TOKEN",
            "SENTRY_ADMIN_UID", "CRISP_PLUGIN_IDENTIFIER", "CRISP_PLUGIN_KEY",
            "CRISP_WEBSITE_ID", "PINECONE_API_KEY", "PINECONE_HOST",
        ] {
            env::remove_var(key);
        }
    }

    #[test]
    fn test_defaults_use_dev_project() {
        let _lock = ENV_LOCK.lock().unwrap();
        clear_config_env_vars();

        let config = Config::from_env();

        // All defaults must point to dev, never prod
        assert_eq!(config.gce_project_id, "based-hardware-dev");
        assert_eq!(config.agent_gcs_bucket, "based-hardware-dev-agent");
        assert!(config.gce_source_image.contains("based-hardware-dev"));
        assert!(!config.gce_project_id.contains("based-hardware-prod"));
        assert!(config.firebase_project_id.is_none(), "no default firebase project without env var");
    }

    #[test]
    fn test_gce_project_id_precedence() {
        let _lock = ENV_LOCK.lock().unwrap();
        clear_config_env_vars();

        // GCE_PROJECT_ID takes priority
        env::set_var("GCE_PROJECT_ID", "gce-proj");
        env::set_var("FIREBASE_PROJECT_ID", "fb-proj");
        env::set_var("GCP_PROJECT_ID", "gcp-proj");
        let config = Config::from_env();
        assert_eq!(config.gce_project_id, "gce-proj");

        // Without GCE_PROJECT_ID, falls back to FIREBASE_PROJECT_ID
        env::remove_var("GCE_PROJECT_ID");
        let config = Config::from_env();
        assert_eq!(config.gce_project_id, "fb-proj");

        // Without both, falls back to GCP_PROJECT_ID
        env::remove_var("FIREBASE_PROJECT_ID");
        let config = Config::from_env();
        assert_eq!(config.gce_project_id, "gcp-proj");

        clear_config_env_vars();
    }

    #[test]
    fn test_firebase_project_id_precedence() {
        let _lock = ENV_LOCK.lock().unwrap();
        clear_config_env_vars();

        // FIREBASE_PROJECT_ID takes priority
        env::set_var("FIREBASE_PROJECT_ID", "fb-proj");
        env::set_var("GCP_PROJECT_ID", "gcp-proj");
        let config = Config::from_env();
        assert_eq!(config.firebase_project_id, Some("fb-proj".to_string()));

        // Falls back to GCP_PROJECT_ID
        env::remove_var("FIREBASE_PROJECT_ID");
        let config = Config::from_env();
        assert_eq!(config.firebase_project_id, Some("gcp-proj".to_string()));

        clear_config_env_vars();
    }

    #[test]
    fn test_port_default_and_override() {
        let _lock = ENV_LOCK.lock().unwrap();
        clear_config_env_vars();

        let config = Config::from_env();
        assert_eq!(config.port, 8080);

        env::set_var("PORT", "9090");
        let config = Config::from_env();
        assert_eq!(config.port, 9090);

        // Invalid port falls back to default
        env::set_var("PORT", "not-a-number");
        let config = Config::from_env();
        assert_eq!(config.port, 8080);

        clear_config_env_vars();
    }

    #[test]
    fn test_no_prod_defaults_anywhere() {
        let _lock = ENV_LOCK.lock().unwrap();
        clear_config_env_vars();

        let config = Config::from_env();

        // Ensure no field defaults to prod project
        let gce = &config.gce_project_id;
        let gce_img = &config.gce_source_image;
        let bucket = &config.agent_gcs_bucket;

        assert!(!gce.contains("based-hardware-prod"), "gce_project_id must not default to prod");
        assert!(!gce_img.contains("based-hardware-prod"), "gce_source_image must not default to prod");
        assert!(!bucket.contains("based-hardware-prod"), "agent_gcs_bucket must not default to prod");

        // Also verify no bare "based-hardware" without -dev suffix
        // (the old prod default was just "based-hardware")
        assert_ne!(gce.as_str(), "based-hardware", "gce_project_id must not default to prod 'based-hardware'");
        assert_ne!(bucket.as_str(), "based-hardware-agent", "agent_gcs_bucket must not default to prod");
    }
}
