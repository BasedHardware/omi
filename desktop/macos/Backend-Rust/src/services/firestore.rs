// Firestore service - Port from Python backend (database.py)
// Uses Firestore REST API for simplicity and compatibility

mod action_items_repository;
mod advice_repository;
mod agent_vm_repository;
mod apps_repository;
mod chat_repository;
mod conversations_repository;
mod desktop_releases_repository;
mod focus_repository;
mod folders_repository;
mod folders_values;
mod goals_repository;
mod knowledge_graph_repository;
mod llm_usage_repository;
mod memories_repository;
mod messages_repository;
mod people_repository;
mod persona_repository;
mod screen_activity_repository;
mod users_repository;
mod values;

use base64::Engine;
use chrono::{DateTime, Utc};
use jsonwebtoken::{encode, Algorithm, EncodingKey, Header};
use reqwest::Client;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::sync::Arc;
use tokio::sync::RwLock;

use crate::encryption;

use crate::models::{
    AIUserProfile, ActionItemDB, AdviceCategory, AdviceDB, AdviceSettingsData, App, AppReview,
    AppSummary, AssistantSettingsData, Category, Conversation, DailySummarySettings,
    DistractionEntry, FloatingBarSettingsData, FocusSessionDB, FocusSettingsData, FocusStats,
    FocusStatus, Folder, GoalDB, GoalHistoryEntry, GoalType, Memory, MemoryCategory, MemoryDB,
    MemorySettingsData, MessageDB, NotificationSettings, PersonaDB, SharedAssistantSettingsData,
    Structured, TaskSettingsData, TranscriptSegment, TranscriptionPreferences, UserProfile,
};

/// Service account credentials from JSON file
#[derive(Debug, Clone, Deserialize)]
struct ServiceAccountCredentials {
    client_email: String,
    private_key: String,
    token_uri: Option<String>,
}

/// JWT claims for Google OAuth2
#[derive(Debug, Serialize)]
struct GoogleJwtClaims {
    iss: String,   // Service account email
    scope: String, // OAuth scopes
    aud: String,   // Token endpoint
    iat: i64,      // Issued at
    exp: i64,      // Expiration
}

/// Cached access token with expiration
struct CachedToken {
    token: String,
    expires_at: i64,
}

/// Firestore collection paths
/// Copied from Python database.py
pub const USERS_COLLECTION: &str = "users";
pub const CONVERSATIONS_SUBCOLLECTION: &str = "conversations";
pub const ACTION_ITEMS_SUBCOLLECTION: &str = "action_items";
pub const MEMORIES_SUBCOLLECTION: &str = "memories";
pub const APPS_COLLECTION: &str = "plugins_data";
pub const ENABLED_APPS_SUBCOLLECTION: &str = "enabled_plugins";
pub const FOCUS_SESSIONS_SUBCOLLECTION: &str = "focus_sessions";
pub const ADVICE_SUBCOLLECTION: &str = "advice";
pub const MESSAGES_SUBCOLLECTION: &str = "messages";
pub const FOLDERS_SUBCOLLECTION: &str = "folders";
pub const CHAT_SESSIONS_SUBCOLLECTION: &str = "chat_sessions";
pub const GOALS_SUBCOLLECTION: &str = "goals";
pub const KG_NODES_SUBCOLLECTION: &str = "knowledge_nodes";
pub const KG_EDGES_SUBCOLLECTION: &str = "knowledge_edges";
pub const STAGED_TASKS_SUBCOLLECTION: &str = "staged_tasks";
pub const PEOPLE_SUBCOLLECTION: &str = "people";
pub const LLM_USAGE_SUBCOLLECTION: &str = "llm_usage";
pub const SCREEN_ACTIVITY_SUBCOLLECTION: &str = "screen_activity";
pub const REALTIME_SESSIONS_SUBCOLLECTION: &str = "realtime_sessions";

/// Generate a document ID from a seed string using SHA256 hash
/// Copied from Python document_id_from_seed
pub fn document_id_from_seed(seed: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(seed.as_bytes());
    let result = hasher.finalize();
    hex::encode(&result[..10]) // First 20 hex chars (10 bytes)
}

/// Firestore REST API client
pub struct FirestoreService {
    client: Client,
    project_id: String,
    credentials: Option<ServiceAccountCredentials>,
    cached_token: Arc<RwLock<Option<CachedToken>>>,
    /// Encryption secret for decrypting user data with enhanced protection level
    encryption_secret: Option<Vec<u8>>,
}

impl FirestoreService {
    #[cfg(test)]
    pub(super) fn new_for_contract(encryption_secret: Option<Vec<u8>>) -> Self {
        Self {
            client: Client::new(),
            project_id: "contract-tests".to_string(),
            credentials: None,
            cached_token: Arc::new(RwLock::new(None)),
            encryption_secret,
        }
    }

    /// Create a new Firestore service
    pub async fn new(
        project_id: String,
        encryption_secret: Option<Vec<u8>>,
    ) -> Result<Self, Box<dyn std::error::Error + Send + Sync>> {
        let client = Client::new();

        // Load service account credentials from GOOGLE_APPLICATION_CREDENTIALS
        let credentials = Self::load_credentials()?;

        let service = Self {
            client,
            project_id,
            credentials,
            cached_token: Arc::new(RwLock::new(None)),
            encryption_secret,
        };

        // Pre-fetch an access token
        if let Err(e) = service.get_access_token().await {
            tracing::warn!("Failed to get initial access token: {}", e);
        }

        Ok(service)
    }

    /// Load service account credentials from JSON file
    fn load_credentials(
    ) -> Result<Option<ServiceAccountCredentials>, Box<dyn std::error::Error + Send + Sync>> {
        // Check GOOGLE_APPLICATION_CREDENTIALS environment variable
        let creds_path = match std::env::var("GOOGLE_APPLICATION_CREDENTIALS") {
            Ok(path) => path,
            Err(_) => {
                // Try default location in current directory
                if std::path::Path::new("google-credentials.json").exists() {
                    "google-credentials.json".to_string()
                } else {
                    tracing::warn!("No GOOGLE_APPLICATION_CREDENTIALS set and no google-credentials.json found");
                    return Ok(None);
                }
            }
        };

        tracing::info!("Loading service account credentials from: {}", creds_path);

        let creds_json = std::fs::read_to_string(&creds_path)
            .map_err(|e| format!("Failed to read credentials file {}: {}", creds_path, e))?;

        let credentials: ServiceAccountCredentials = serde_json::from_str(&creds_json)
            .map_err(|e| format!("Failed to parse credentials JSON: {}", e))?;

        tracing::info!(
            "Loaded credentials for service account: {}",
            credentials.client_email
        );

        Ok(Some(credentials))
    }

    /// Get access token, using cache if valid or refreshing if needed
    async fn get_access_token(&self) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
        // Check cached token
        {
            let cache = self.cached_token.read().await;
            if let Some(cached) = cache.as_ref() {
                let now = Utc::now().timestamp();
                // Use token if it has at least 60 seconds left
                if cached.expires_at > now + 60 {
                    return Ok(cached.token.clone());
                }
            }
        }

        // Need to refresh token
        let token = self.fetch_new_access_token().await?;

        // Cache it (tokens are valid for 1 hour, we'll refresh after 55 minutes)
        {
            let mut cache = self.cached_token.write().await;
            *cache = Some(CachedToken {
                token: token.clone(),
                expires_at: Utc::now().timestamp() + 3300, // 55 minutes
            });
        }

        Ok(token)
    }

    /// Fetch a new access token from Google OAuth
    async fn fetch_new_access_token(
        &self,
    ) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
        // Use service account credentials first (has full permissions)
        if let Some(creds) = &self.credentials {
            let token = self.get_token_from_service_account(creds).await?;
            tracing::info!("Got access token from service account");
            return Ok(token);
        }

        // Fall back to metadata server (for GKE/Cloud Run without credentials file)
        if let Ok(token) = self.try_metadata_server().await {
            tracing::info!("Got access token from GCP metadata server");
            return Ok(token);
        }

        Err("No valid authentication method available. Set GOOGLE_APPLICATION_CREDENTIALS or run on GCP.".into())
    }

    /// Try to get token from GCP metadata server
    async fn try_metadata_server(
        &self,
    ) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
        let metadata_url =
            "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token";

        let response = self
            .client
            .get(metadata_url)
            .header("Metadata-Flavor", "Google")
            .timeout(std::time::Duration::from_secs(2))
            .send()
            .await?;

        if response.status().is_success() {
            #[derive(Deserialize)]
            struct TokenResponse {
                access_token: String,
            }
            let token: TokenResponse = response.json().await?;
            return Ok(token.access_token);
        }

        Err("Metadata server not available".into())
    }

    /// Get access token using service account credentials (OAuth2 JWT flow)
    async fn get_token_from_service_account(
        &self,
        creds: &ServiceAccountCredentials,
    ) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
        let now = Utc::now().timestamp();
        let token_uri = creds
            .token_uri
            .as_deref()
            .unwrap_or("https://oauth2.googleapis.com/token");

        // Create JWT claims
        let claims = GoogleJwtClaims {
            iss: creds.client_email.clone(),
            scope: "https://www.googleapis.com/auth/datastore https://www.googleapis.com/auth/cloud-platform".to_string(),
            aud: token_uri.to_string(),
            iat: now,
            exp: now + 3600, // 1 hour
        };

        // Sign JWT with service account private key (RS256)
        let key = EncodingKey::from_rsa_pem(creds.private_key.as_bytes())
            .map_err(|e| format!("Failed to parse private key: {}", e))?;

        let jwt = encode(&Header::new(Algorithm::RS256), &claims, &key)
            .map_err(|e| format!("Failed to encode JWT: {}", e))?;

        // Exchange JWT for access token
        let response = self
            .client
            .post(token_uri)
            .form(&[
                ("grant_type", "urn:ietf:params:oauth:grant-type:jwt-bearer"),
                ("assertion", &jwt),
            ])
            .send()
            .await
            .map_err(|e| format!("Token request failed: {}", e))?;

        if !response.status().is_success() {
            let error_text = response.text().await.unwrap_or_default();
            return Err(format!("Token exchange failed: {}", error_text).into());
        }

        #[derive(Deserialize)]
        struct TokenResponse {
            access_token: String,
        }

        let token_response: TokenResponse = response
            .json()
            .await
            .map_err(|e| format!("Failed to parse token response: {}", e))?;

        Ok(token_response.access_token)
    }

    /// Refresh access token (for manual refresh if needed)
    pub async fn refresh_token(&self) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        // Clear cache to force refresh
        {
            let mut cache = self.cached_token.write().await;
            *cache = None;
        }
        self.get_access_token().await?;
        Ok(())
    }

    /// Build Firestore REST API base URL
    fn base_url(&self) -> String {
        format!(
            "https://firestore.googleapis.com/v1/projects/{}/databases/(default)/documents",
            self.project_id
        )
    }

    /// Build request with auth header
    async fn build_request(
        &self,
        method: reqwest::Method,
        url: &str,
    ) -> Result<reqwest::RequestBuilder, Box<dyn std::error::Error + Send + Sync>> {
        let mut req = self.client.request(method, url);
        let token = self.get_access_token().await?;
        req = req.bearer_auth(token);
        Ok(req)
    }

    /// Build authenticated request for GCE Compute Engine API (public for agent routes)
    pub async fn build_compute_request(
        &self,
        method: reqwest::Method,
        url: &str,
    ) -> Result<reqwest::RequestBuilder, Box<dyn std::error::Error + Send + Sync>> {
        self.build_request(method, url).await
    }
}

impl Default for Structured {
    fn default() -> Self {
        Self {
            title: String::new(),
            overview: String::new(),
            emoji: "🧠".to_string(),
            category: Category::Other,
            action_items: vec![],
            events: vec![],
        }
    }
}

// ---------------------------------------------------------------------------
// Pure parsing functions (extracted from FirestoreService for testability)
// ---------------------------------------------------------------------------

/// Parse BYOK state from a Firestore user document JSON.
/// Returns `ByokState::default()` (inactive) if the byok field is missing or malformed.
pub(super) fn parse_byok_state_from_doc(doc: &Value) -> crate::byok::ByokState {
    let fields = match doc.get("fields") {
        Some(f) => f,
        None => return crate::byok::ByokState::default(),
    };

    let byok_fields = match fields
        .get("byok")
        .and_then(|v| v.get("mapValue"))
        .and_then(|v| v.get("fields"))
    {
        Some(f) => f,
        None => return crate::byok::ByokState::default(),
    };

    let active = byok_fields
        .get("active")
        .and_then(|v| v.get("booleanValue"))
        .and_then(|v| v.as_bool())
        .unwrap_or(false);

    let mut fingerprints = std::collections::HashMap::new();
    if let Some(fp_fields) = byok_fields
        .get("fingerprints")
        .and_then(|v| v.get("mapValue"))
        .and_then(|v| v.get("fields"))
        .and_then(|v| v.as_object())
    {
        for (provider, val) in fp_fields {
            if let Some(fp_str) = val.get("stringValue").and_then(|v| v.as_str()) {
                fingerprints.insert(provider.clone(), fp_str.to_string());
            }
        }
    }

    let last_seen_at = byok_fields
        .get("last_seen_at")
        .and_then(|v| v.get("timestampValue"))
        .and_then(|v| v.as_str())
        .and_then(|ts| chrono::DateTime::parse_from_rfc3339(ts).ok())
        .map(|dt| dt.with_timezone(&chrono::Utc));

    crate::byok::ByokState {
        active,
        fingerprints,
        last_seen_at,
    }
}

/// Parse effective subscription plan from a Firestore user document JSON.
/// Returns "basic" if the subscription field is missing, malformed, or expired.
pub(super) fn parse_effective_plan_from_doc(doc: &Value) -> String {
    let fields = match doc.get("fields") {
        Some(f) => f,
        None => return "basic".to_string(),
    };

    let sub_fields = match fields
        .get("subscription")
        .and_then(|v| v.get("mapValue"))
        .and_then(|v| v.get("fields"))
    {
        Some(f) => f,
        None => return "basic".to_string(),
    };

    let mut plan = sub_fields
        .get("plan")
        .and_then(|v| v.get("stringValue"))
        .and_then(|v| v.as_str())
        .unwrap_or("basic")
        .to_string();

    if plan == "free" {
        plan = "basic".to_string();
    }

    if plan == "basic" {
        return plan;
    }

    // Paid plan: check current_period_end
    match sub_fields
        .get("current_period_end")
        .and_then(|v| v.get("integerValue"))
        .and_then(|v| v.as_str())
        .and_then(|s| s.parse::<i64>().ok())
    {
        Some(period_end) => {
            let now_epoch = chrono::Utc::now().timestamp();
            if period_end < now_epoch {
                "basic".to_string()
            } else {
                plan
            }
        }
        None => "basic".to_string(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_document_id_from_seed() {
        let id = document_id_from_seed("test content");
        assert_eq!(id.len(), 20);
        assert_eq!(id, document_id_from_seed("test content"));
        assert_ne!(id, document_id_from_seed("different content"));
    }

    // --- Firestore BYOK state parsing tests ---

    #[test]
    fn parse_byok_state_full_document() {
        let doc = json!({
            "fields": {
                "byok": {
                    "mapValue": {
                        "fields": {
                            "active": { "booleanValue": true },
                            "fingerprints": {
                                "mapValue": {
                                    "fields": {
                                        "openai": { "stringValue": "abc123" },
                                        "anthropic": { "stringValue": "def456" }
                                    }
                                }
                            },
                            "last_seen_at": {
                                "timestampValue": "2026-05-18T10:00:00Z"
                            }
                        }
                    }
                }
            }
        });
        let state = parse_byok_state_from_doc(&doc);
        assert!(state.active);
        assert_eq!(state.fingerprints.len(), 2);
        assert_eq!(
            state.fingerprints.get("openai"),
            Some(&"abc123".to_string())
        );
        assert_eq!(
            state.fingerprints.get("anthropic"),
            Some(&"def456".to_string())
        );
        assert!(state.last_seen_at.is_some());
    }

    #[test]
    fn parse_byok_state_missing_byok_field() {
        let doc = json!({ "fields": { "name": { "stringValue": "Alice" } } });
        let state = parse_byok_state_from_doc(&doc);
        assert!(!state.active);
        assert!(state.fingerprints.is_empty());
        assert!(state.last_seen_at.is_none());
    }

    #[test]
    fn parse_byok_state_missing_fields() {
        let doc = json!({});
        let state = parse_byok_state_from_doc(&doc);
        assert!(!state.active);
    }

    #[test]
    fn parse_byok_state_active_false() {
        let doc = json!({
            "fields": {
                "byok": {
                    "mapValue": {
                        "fields": {
                            "active": { "booleanValue": false }
                        }
                    }
                }
            }
        });
        let state = parse_byok_state_from_doc(&doc);
        assert!(!state.active);
        assert!(state.fingerprints.is_empty());
    }

    #[test]
    fn parse_byok_state_no_fingerprints() {
        let doc = json!({
            "fields": {
                "byok": {
                    "mapValue": {
                        "fields": {
                            "active": { "booleanValue": true },
                            "last_seen_at": { "timestampValue": "2026-05-18T10:00:00Z" }
                        }
                    }
                }
            }
        });
        let state = parse_byok_state_from_doc(&doc);
        assert!(state.active);
        assert!(state.fingerprints.is_empty());
    }

    #[test]
    fn parse_byok_state_malformed_timestamp() {
        let doc = json!({
            "fields": {
                "byok": {
                    "mapValue": {
                        "fields": {
                            "active": { "booleanValue": true },
                            "last_seen_at": { "timestampValue": "not-a-date" }
                        }
                    }
                }
            }
        });
        let state = parse_byok_state_from_doc(&doc);
        assert!(state.active);
        assert!(state.last_seen_at.is_none());
    }

    // --- Firestore subscription plan parsing tests ---

    #[test]
    fn parse_plan_pro_with_future_expiry() {
        let future_ts = chrono::Utc::now().timestamp() + 86400; // +1 day
        let doc = json!({
            "fields": {
                "subscription": {
                    "mapValue": {
                        "fields": {
                            "plan": { "stringValue": "pro" },
                            "current_period_end": { "integerValue": future_ts.to_string() }
                        }
                    }
                }
            }
        });
        assert_eq!(parse_effective_plan_from_doc(&doc), "pro");
    }

    #[test]
    fn parse_plan_pro_expired() {
        let past_ts = chrono::Utc::now().timestamp() - 86400; // -1 day
        let doc = json!({
            "fields": {
                "subscription": {
                    "mapValue": {
                        "fields": {
                            "plan": { "stringValue": "pro" },
                            "current_period_end": { "integerValue": past_ts.to_string() }
                        }
                    }
                }
            }
        });
        assert_eq!(parse_effective_plan_from_doc(&doc), "basic");
    }

    #[test]
    fn parse_plan_pro_missing_period_end() {
        let doc = json!({
            "fields": {
                "subscription": {
                    "mapValue": {
                        "fields": {
                            "plan": { "stringValue": "pro" }
                        }
                    }
                }
            }
        });
        assert_eq!(parse_effective_plan_from_doc(&doc), "basic");
    }

    #[test]
    fn parse_plan_basic() {
        let doc = json!({
            "fields": {
                "subscription": {
                    "mapValue": {
                        "fields": {
                            "plan": { "stringValue": "basic" }
                        }
                    }
                }
            }
        });
        assert_eq!(parse_effective_plan_from_doc(&doc), "basic");
    }

    #[test]
    fn parse_plan_free_migrated_to_basic() {
        let doc = json!({
            "fields": {
                "subscription": {
                    "mapValue": {
                        "fields": {
                            "plan": { "stringValue": "free" }
                        }
                    }
                }
            }
        });
        assert_eq!(parse_effective_plan_from_doc(&doc), "basic");
    }

    #[test]
    fn parse_plan_missing_subscription() {
        let doc = json!({ "fields": {} });
        assert_eq!(parse_effective_plan_from_doc(&doc), "basic");
    }

    #[test]
    fn parse_plan_missing_fields_key() {
        let doc = json!({});
        assert_eq!(parse_effective_plan_from_doc(&doc), "basic");
    }

    #[test]
    fn parse_plan_enterprise_valid() {
        let future_ts = chrono::Utc::now().timestamp() + 86400;
        let doc = json!({
            "fields": {
                "subscription": {
                    "mapValue": {
                        "fields": {
                            "plan": { "stringValue": "enterprise" },
                            "current_period_end": { "integerValue": future_ts.to_string() }
                        }
                    }
                }
            }
        });
        assert_eq!(parse_effective_plan_from_doc(&doc), "enterprise");
    }
}
