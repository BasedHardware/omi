#![deny(dead_code, unreachable_pub)]

// Firestore service - Port from Python backend (database.py)
// Uses Firestore REST API for simplicity and compatibility

mod action_items_repository;
mod agent_vm_repository;
mod conversations_repository;
mod desktop_releases_repository;
mod llm_usage_repository;
mod screen_activity_repository;
mod users_repository;
mod values;

use chrono::{DateTime, Utc};
use jsonwebtoken::{encode, Algorithm, EncodingKey, Header};
use reqwest::Client;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::sync::Arc;
use tokio::sync::RwLock;

use crate::models::ActionItemDB;

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

/// A freshly minted access token plus the lifetime its issuer reported.
struct FetchedToken {
    token: String,
    /// Seconds of remaining life, as reported by the token endpoint.
    expires_in: Option<i64>,
}

/// Lifetime assumed when a token endpoint omits `expires_in`.
const DEFAULT_TOKEN_LIFETIME_SECS: i64 = 3600;

/// GCE metadata server token endpoint. The server hands back a *shared* token
/// whose remaining life is frequently far below an hour, so its `expires_in`
/// is the only correct cache lifetime — assuming a full hour serves an expired
/// token until the local cache happens to lapse.
const METADATA_TOKEN_URL: &str =
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token";

/// Firestore collection paths
/// Copied from Python database.py
const USERS_COLLECTION: &str = "users";
const CONVERSATIONS_SUBCOLLECTION: &str = "conversations";
const ACTION_ITEMS_SUBCOLLECTION: &str = "action_items";
const LLM_USAGE_SUBCOLLECTION: &str = "llm_usage";
const SCREEN_ACTIVITY_SUBCOLLECTION: &str = "screen_activity";
const REALTIME_SESSIONS_SUBCOLLECTION: &str = "realtime_sessions";

/// Generate a document ID from a seed string using SHA256 hash
/// Copied from Python document_id_from_seed
fn document_id_from_seed(seed: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(seed.as_bytes());
    let result = hasher.finalize();
    hex::encode(&result[..10]) // First 20 hex chars (10 bytes)
}

/// Firestore REST API client
pub(crate) struct FirestoreService {
    client: Client,
    project_id: String,
    credentials: Option<ServiceAccountCredentials>,
    cached_token: Arc<RwLock<Option<CachedToken>>>,
    metadata_token_url: String,
}

impl FirestoreService {
    /// Create a new Firestore service
    pub(crate) async fn new(
        project_id: String,
    ) -> Result<Self, Box<dyn std::error::Error + Send + Sync>> {
        let client = Client::new();

        // Load service account credentials from GOOGLE_APPLICATION_CREDENTIALS
        let credentials = Self::load_credentials()?;

        let service = Self {
            client,
            project_id,
            credentials,
            cached_token: Arc::new(RwLock::new(None)),
            metadata_token_url: METADATA_TOKEN_URL.to_string(),
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
        let fetched = self.fetch_new_access_token().await?;

        // Cache it until the issuer's own expiry; the read path above keeps a
        // 60s safety margin. Never assume a lifetime the issuer did not grant.
        {
            let mut cache = self.cached_token.write().await;
            *cache = Some(CachedToken {
                token: fetched.token.clone(),
                expires_at: Utc::now().timestamp()
                    + fetched.expires_in.unwrap_or(DEFAULT_TOKEN_LIFETIME_SECS),
            });
        }

        Ok(fetched.token)
    }

    /// Fetch a new access token from Google OAuth
    async fn fetch_new_access_token(
        &self,
    ) -> Result<FetchedToken, Box<dyn std::error::Error + Send + Sync>> {
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
    ) -> Result<FetchedToken, Box<dyn std::error::Error + Send + Sync>> {
        let response = self
            .client
            .get(&self.metadata_token_url)
            .header("Metadata-Flavor", "Google")
            .timeout(std::time::Duration::from_secs(2))
            .send()
            .await?;

        if response.status().is_success() {
            #[derive(Deserialize)]
            struct TokenResponse {
                access_token: String,
                expires_in: Option<i64>,
            }
            let token: TokenResponse = response.json().await?;
            return Ok(FetchedToken {
                token: token.access_token,
                expires_in: token.expires_in,
            });
        }

        Err("Metadata server not available".into())
    }

    /// Get access token using service account credentials (OAuth2 JWT flow)
    async fn get_token_from_service_account(
        &self,
        creds: &ServiceAccountCredentials,
    ) -> Result<FetchedToken, Box<dyn std::error::Error + Send + Sync>> {
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
            expires_in: Option<i64>,
        }

        let token_response: TokenResponse = response
            .json()
            .await
            .map_err(|e| format!("Failed to parse token response: {}", e))?;

        Ok(FetchedToken {
            token: token_response.access_token,
            expires_in: token_response.expires_in,
        })
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
    pub(crate) async fn build_compute_request(
        &self,
        method: reqwest::Method,
        url: &str,
    ) -> Result<reqwest::RequestBuilder, Box<dyn std::error::Error + Send + Sync>> {
        self.build_request(method, url).await
    }
}

// ---------------------------------------------------------------------------
// Pure parsing functions (extracted from FirestoreService for testability)
// ---------------------------------------------------------------------------

/// Parse BYOK state from a Firestore user document JSON.
/// Returns `ByokState::default()` (inactive) if the byok field is missing or malformed.
fn parse_byok_state_from_doc(doc: &Value) -> crate::byok::ByokState {
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
fn parse_effective_plan_from_doc(doc: &Value) -> String {
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
    // Tests may unwrap: the crate-level unwrap_used deny targets production
    // code; a test failing on unwrap is the test doing its job.
    #![allow(clippy::unwrap_used)]
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};

    /// Serve the metadata-server token shape with a caller-chosen lifetime and
    /// count how many times a token was minted.
    async fn spawn_token_server(expires_in: i64) -> (String, Arc<AtomicUsize>) {
        let hits = Arc::new(AtomicUsize::new(0));
        let served = hits.clone();
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let app = axum::Router::new().route(
            "/token",
            axum::routing::get(move || {
                let served = served.clone();
                async move {
                    let minted = served.fetch_add(1, Ordering::SeqCst);
                    axum::Json(serde_json::json!({
                        "access_token": format!("token-{}", minted),
                        "expires_in": expires_in,
                        "token_type": "Bearer",
                    }))
                }
            }),
        );
        tokio::spawn(async move {
            axum::serve(listener, app).await.unwrap();
        });
        (format!("http://{}/token", address), hits)
    }

    fn service_with_metadata_url(metadata_token_url: String) -> FirestoreService {
        FirestoreService {
            client: Client::builder().no_proxy().build().unwrap(),
            project_id: "test-project".to_string(),
            credentials: None,
            cached_token: Arc::new(RwLock::new(None)),
            metadata_token_url,
        }
    }

    /// The metadata server hands back a shared token that is often minutes from
    /// expiry. Caching it for a hardcoded 55 minutes kept an already-expired
    /// token in use — every Firestore call then failed UNAUTHENTICATED
    /// (ACCESS_TOKEN_EXPIRED) until the local cache lapsed. The issuer's
    /// `expires_in` has to win.
    #[tokio::test]
    async fn short_lived_metadata_token_is_not_cached_past_its_expiry() {
        let (url, hits) = spawn_token_server(30).await;
        let service = service_with_metadata_url(url);

        let first = service.get_access_token().await.unwrap();
        let second = service.get_access_token().await.unwrap();

        // 30s of life is inside the 60s freshness margin, so the second call
        // must mint a new token instead of serving the stale one.
        assert_eq!(hits.load(Ordering::SeqCst), 2);
        assert_eq!(first, "token-0");
        assert_eq!(second, "token-1");
    }

    #[tokio::test]
    async fn long_lived_metadata_token_is_reused_from_cache() {
        let (url, hits) = spawn_token_server(3600).await;
        let service = service_with_metadata_url(url);

        let first = service.get_access_token().await.unwrap();
        let second = service.get_access_token().await.unwrap();

        assert_eq!(hits.load(Ordering::SeqCst), 1);
        assert_eq!(first, second);
    }

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
