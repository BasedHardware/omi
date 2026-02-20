// Firestore service - Port from Python backend (database.py)
// Uses Firestore REST API for simplicity and compatibility

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
    ActionItemDB, AdviceCategory, AdviceDB, App, AppReview, AppSummary, Category,
    ChatSessionDB, Conversation, DailySummarySettings, DistractionEntry, Folder, FocusSessionDB,
    FocusStats, FocusStatus, GoalDB, GoalHistoryEntry, GoalType, Memory, MemoryCategory, MemoryDB, MessageDB,
    NotificationSettings, PersonaDB, Structured, TranscriptSegment, TranscriptionPreferences,
    AIUserProfile, UserProfile,
    AssistantSettingsData, SharedAssistantSettingsData, FocusSettingsData, TaskSettingsData,
    AdviceSettingsData, MemorySettingsData,
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
    iss: String,      // Service account email
    scope: String,    // OAuth scopes
    aud: String,      // Token endpoint
    iat: i64,         // Issued at
    exp: i64,         // Expiration
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
pub const KG_NODES_SUBCOLLECTION: &str = "kg_nodes";
pub const KG_EDGES_SUBCOLLECTION: &str = "kg_edges";
pub const STAGED_TASKS_SUBCOLLECTION: &str = "staged_tasks";
pub const PEOPLE_SUBCOLLECTION: &str = "people";

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
    fn load_credentials() -> Result<Option<ServiceAccountCredentials>, Box<dyn std::error::Error + Send + Sync>> {
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

        tracing::info!("Loaded credentials for service account: {}", credentials.client_email);

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
    async fn fetch_new_access_token(&self) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
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
    async fn try_metadata_server(&self) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
        let metadata_url =
            "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token";

        let response = self.client
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
        let token_uri = creds.token_uri.as_deref().unwrap_or("https://oauth2.googleapis.com/token");

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
        let response = self.client
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

        let token_response: TokenResponse = response.json().await
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
    async fn build_request(&self, method: reqwest::Method, url: &str) -> Result<reqwest::RequestBuilder, Box<dyn std::error::Error + Send + Sync>> {
        let mut req = self.client.request(method, url);
        let token = self.get_access_token().await?;
        req = req.bearer_auth(token);
        Ok(req)
    }

    /// Build authenticated request for GCE Compute Engine API (public for agent routes)
    pub async fn build_compute_request(&self, method: reqwest::Method, url: &str) -> Result<reqwest::RequestBuilder, Box<dyn std::error::Error + Send + Sync>> {
        self.build_request(method, url).await
    }

    // =========================================================================
    // CONVERSATIONS
    // =========================================================================

    /// Get conversations for a user
    /// Path: users/{uid}/conversations
    /// Ported from Python: database/conversations.py get_conversations()
    pub async fn get_conversations(
        &self,
        uid: &str,
        limit: usize,
        offset: usize,
        include_discarded: bool,
        statuses: &[String],
        starred: Option<bool>,
        folder_id: Option<&str>,
        start_date: Option<&str>,
        end_date: Option<&str>,
    ) -> Result<Vec<Conversation>, Box<dyn std::error::Error + Send + Sync>> {
        // Build filters array (match Python behavior)
        let mut filters: Vec<Value> = Vec::new();

        // Python: if not include_discarded: where(discarded == False)
        // Only filter when include_discarded is false
        if !include_discarded {
            filters.push(json!({
                "fieldFilter": {
                    "field": {"fieldPath": "discarded"},
                    "op": "EQUAL",
                    "value": {"booleanValue": false}
                }
            }));
        }

        // Python: if len(statuses) > 0: where(status in statuses)
        if !statuses.is_empty() {
            filters.push(json!({
                "fieldFilter": {
                    "field": {"fieldPath": "status"},
                    "op": "IN",
                    "value": {
                        "arrayValue": {
                            "values": statuses.iter().map(|s| json!({"stringValue": s})).collect::<Vec<_>>()
                        }
                    }
                }
            }));
        }

        // Filter by starred status
        if let Some(starred_val) = starred {
            filters.push(json!({
                "fieldFilter": {
                    "field": {"fieldPath": "starred"},
                    "op": "EQUAL",
                    "value": {"booleanValue": starred_val}
                }
            }));
        }

        // Filter by folder_id
        if let Some(fid) = folder_id {
            filters.push(json!({
                "fieldFilter": {
                    "field": {"fieldPath": "folder_id"},
                    "op": "EQUAL",
                    "value": {"stringValue": fid}
                }
            }));
        }

        // Filter by date range
        if let Some(start) = start_date {
            filters.push(json!({
                "fieldFilter": {
                    "field": {"fieldPath": "created_at"},
                    "op": "GREATER_THAN_OR_EQUAL",
                    "value": {"timestampValue": start}
                }
            }));
        }

        if let Some(end) = end_date {
            filters.push(json!({
                "fieldFilter": {
                    "field": {"fieldPath": "created_at"},
                    "op": "LESS_THAN",
                    "value": {"timestampValue": end}
                }
            }));
        }

        // Build the where clause based on number of filters
        let where_clause = if filters.is_empty() {
            None
        } else if filters.len() == 1 {
            Some(filters.into_iter().next().unwrap())
        } else {
            // Multiple filters need compositeFilter with AND
            Some(json!({
                "compositeFilter": {
                    "op": "AND",
                    "filters": filters
                }
            }))
        };

        // Build structured query
        let mut structured_query = json!({
            "from": [{"collectionId": CONVERSATIONS_SUBCOLLECTION}],
            "orderBy": [{"field": {"fieldPath": "created_at"}, "direction": "DESCENDING"}],
            "limit": limit,
            "offset": offset
        });

        if let Some(where_filter) = where_clause {
            structured_query["where"] = where_filter;
        }

        let query = json!({
            "structuredQuery": structured_query
        });

        let parent = format!(
            "{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid
        );

        tracing::debug!("Firestore query: {}", serde_json::to_string_pretty(&query).unwrap_or_default());

        let response = self
            .build_request(reqwest::Method::POST, &format!("{}:runQuery", parent))
            .await?
            .json(&query)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            tracing::error!("Firestore query error: {}", error_text);
            return Err(format!("Firestore query failed: {}", error_text).into());
        }

        let results: Vec<Value> = response.json().await?;
        let conversations: Vec<Conversation> = results
            .into_iter()
            .filter_map(|doc| {
                doc.get("document")
                    .and_then(|d| match self.parse_conversation(d, uid) {
                        Ok(conv) => Some(conv),
                        Err(e) => {
                            tracing::warn!("Failed to parse conversation: {}", e);
                            None
                        }
                    })
            })
            .collect();

        tracing::info!("Retrieved {} conversations for user {}", conversations.len(), uid);
        Ok(conversations)
    }

    /// Get count of conversations for a user using Firestore aggregation query
    pub async fn get_conversations_count(
        &self,
        uid: &str,
        include_discarded: bool,
        statuses: &[String],
    ) -> Result<i64, Box<dyn std::error::Error + Send + Sync>> {
        let parent = format!(
            "{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid
        );

        // Build filters (same as get_conversations)
        let mut filters: Vec<Value> = Vec::new();

        if !include_discarded {
            filters.push(json!({
                "fieldFilter": {
                    "field": {"fieldPath": "discarded"},
                    "op": "EQUAL",
                    "value": {"booleanValue": false}
                }
            }));
        }

        if !statuses.is_empty() {
            filters.push(json!({
                "fieldFilter": {
                    "field": {"fieldPath": "status"},
                    "op": "IN",
                    "value": {
                        "arrayValue": {
                            "values": statuses.iter().map(|s| json!({"stringValue": s})).collect::<Vec<_>>()
                        }
                    }
                }
            }));
        }

        let where_clause = if filters.is_empty() {
            None
        } else if filters.len() == 1 {
            Some(filters.into_iter().next().unwrap())
        } else {
            Some(json!({
                "compositeFilter": {
                    "op": "AND",
                    "filters": filters
                }
            }))
        };

        let mut structured_query = json!({
            "from": [{"collectionId": CONVERSATIONS_SUBCOLLECTION}]
        });

        if let Some(where_filter) = where_clause {
            structured_query["where"] = where_filter;
        }

        let query = json!({
            "structuredAggregationQuery": {
                "structuredQuery": structured_query,
                "aggregations": [{
                    "alias": "count",
                    "count": {}
                }]
            }
        });

        let response = self
            .build_request(reqwest::Method::POST, &format!("{}:runAggregationQuery", parent))
            .await?
            .json(&query)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            tracing::error!("Firestore aggregation query error: {}", error_text);
            return Err(format!("Firestore aggregation query failed: {}", error_text).into());
        }

        let results: Vec<Value> = response.json().await?;

        // Parse the count from aggregation result
        // Response format: [{"result": {"aggregateFields": {"count": {"integerValue": "123"}}}}]
        let count = results
            .first()
            .and_then(|r| r.get("result"))
            .and_then(|r| r.get("aggregateFields"))
            .and_then(|f| f.get("count"))
            .and_then(|c| c.get("integerValue"))
            .and_then(|v| v.as_str())
            .and_then(|s| s.parse::<i64>().ok())
            .unwrap_or(0);

        tracing::info!("Conversations count for user {}: {}", uid, count);
        Ok(count)
    }

    /// Get a single conversation
    pub async fn get_conversation(
        &self,
        uid: &str,
        conversation_id: &str,
    ) -> Result<Option<Conversation>, Box<dyn std::error::Error + Send + Sync>> {
        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            CONVERSATIONS_SUBCOLLECTION,
            conversation_id
        );

        let response = self
            .build_request(reqwest::Method::GET, &url)
            .await?
            .send()
            .await?;

        if response.status() == reqwest::StatusCode::NOT_FOUND {
            return Ok(None);
        }

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore error: {}", error_text).into());
        }

        let doc: Value = response.json().await?;
        let conversation = self.parse_conversation(&doc, uid)?;
        Ok(Some(conversation))
    }

    /// Save a conversation
    pub async fn save_conversation(
        &self,
        uid: &str,
        conversation: &Conversation,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            CONVERSATIONS_SUBCOLLECTION,
            conversation.id
        );

        let doc = self.conversation_to_firestore(conversation, uid);

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore save error: {}", error_text).into());
        }

        tracing::info!("Saved conversation {} for user {}", conversation.id, uid);
        Ok(())
    }

    /// Add an app result to a conversation
    pub async fn add_app_result(
        &self,
        uid: &str,
        conversation_id: &str,
        app_id: &str,
        content: &str,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        // First get the current conversation to append to apps_results
        let current = self.get_conversation(uid, conversation_id).await?;
        let mut apps_results = current
            .map(|c| c.apps_results)
            .unwrap_or_default();

        // Remove existing result for this app if present, then add new one
        apps_results.retain(|r| r.app_id.as_deref() != Some(app_id));
        apps_results.push(crate::models::AppResult {
            app_id: Some(app_id.to_string()),
            content: content.to_string(),
        });

        // Build the update document
        let url = format!(
            "{}/{}/{}/{}/{}?updateMask.fieldPaths=apps_results",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            CONVERSATIONS_SUBCOLLECTION,
            conversation_id
        );

        let apps_results_value: Vec<Value> = apps_results
            .iter()
            .map(|r| {
                json!({
                    "mapValue": {
                        "fields": {
                            "app_id": { "stringValue": r.app_id.as_deref().unwrap_or("") },
                            "content": { "stringValue": &r.content }
                        }
                    }
                })
            })
            .collect();

        let doc = json!({
            "fields": {
                "apps_results": {
                    "arrayValue": {
                        "values": apps_results_value
                    }
                }
            }
        });

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore update error: {}", error_text).into());
        }

        tracing::info!("Added app result for app {} to conversation {}", app_id, conversation_id);
        Ok(())
    }

    /// Set the starred status of a conversation
    pub async fn set_conversation_starred(
        &self,
        uid: &str,
        conversation_id: &str,
        starred: bool,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let url = format!(
            "{}/{}/{}/{}/{}?updateMask.fieldPaths=starred",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            CONVERSATIONS_SUBCOLLECTION,
            conversation_id
        );

        let doc = json!({
            "fields": {
                "starred": {"booleanValue": starred}
            }
        });

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore update error: {}", error_text).into());
        }

        tracing::info!(
            "Set conversation {} starred={} for user {}",
            conversation_id,
            starred,
            uid
        );
        Ok(())
    }

    /// Set the visibility of a conversation (for sharing)
    pub async fn set_conversation_visibility(
        &self,
        uid: &str,
        conversation_id: &str,
        visibility: &str,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let url = format!(
            "{}/{}/{}/{}/{}?updateMask.fieldPaths=visibility",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            CONVERSATIONS_SUBCOLLECTION,
            conversation_id
        );

        let doc = json!({
            "fields": {
                "visibility": {"stringValue": visibility}
            }
        });

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore update error: {}", error_text).into());
        }

        tracing::info!(
            "Set conversation {} visibility='{}' for user {}",
            conversation_id,
            visibility,
            uid
        );
        Ok(())
    }

    /// Delete a conversation
    pub async fn delete_conversation(
        &self,
        uid: &str,
        conversation_id: &str,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            CONVERSATIONS_SUBCOLLECTION,
            conversation_id
        );

        let response = self
            .build_request(reqwest::Method::DELETE, &url)
            .await?
            .send()
            .await?;

        if !response.status().is_success() && response.status() != reqwest::StatusCode::NOT_FOUND {
            let error_text = response.text().await?;
            return Err(format!("Firestore delete error: {}", error_text).into());
        }

        tracing::info!("Deleted conversation {} for user {}", conversation_id, uid);
        Ok(())
    }

    /// Update a conversation's title
    pub async fn update_conversation_title(
        &self,
        uid: &str,
        conversation_id: &str,
        title: &str,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let url = format!(
            "{}/{}/{}/{}/{}?updateMask.fieldPaths=structured.title",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            CONVERSATIONS_SUBCOLLECTION,
            conversation_id
        );

        let doc = json!({
            "fields": {
                "structured": {
                    "mapValue": {
                        "fields": {
                            "title": {"stringValue": title}
                        }
                    }
                }
            }
        });

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore update error: {}", error_text).into());
        }

        tracing::info!(
            "Updated conversation {} title for user {}",
            conversation_id,
            uid
        );
        Ok(())
    }

    // =========================================================================
    // MEMORIES
    // =========================================================================

    /// Get memories for a user with optional filtering
    /// Copied from Python get_memories
    /// Enriches memories with source from linked conversations
    pub async fn get_memories_filtered(
        &self,
        uid: &str,
        limit: usize,
        offset: usize,
        category: Option<&str>,
        tags: Option<&[String]>,
        include_dismissed: bool,
    ) -> Result<Vec<MemoryDB>, Box<dyn std::error::Error + Send + Sync>> {
        let parent = format!("{}/{}/{}", self.base_url(), USERS_COLLECTION, uid);

        // Build filters
        let mut filters: Vec<Value> = Vec::new();

        // Filter by category if specified
        if let Some(cat) = category {
            filters.push(json!({
                "fieldFilter": {
                    "field": {"fieldPath": "category"},
                    "op": "EQUAL",
                    "value": {"stringValue": cat}
                }
            }));
        }

        // Filter by first tag in Firestore (ARRAY_CONTAINS supports one tag per query).
        // Additional tags (if any) are still filtered in-memory below.
        if let Some(filter_tags) = tags {
            if let Some(first_tag) = filter_tags.first() {
                filters.push(json!({
                    "fieldFilter": {
                        "field": {"fieldPath": "tags"},
                        "op": "ARRAY_CONTAINS",
                        "value": {"stringValue": first_tag}
                    }
                }));
            }
        }

        // NOTE: We do NOT filter is_dismissed in Firestore query because existing memories
        // don't have this field. Firestore only returns documents where the field EXISTS and
        // matches the value. Instead, we filter in-memory below (matching Python behavior).

        // Build the where clause
        let where_clause = if filters.is_empty() {
            None
        } else if filters.len() == 1 {
            Some(filters.into_iter().next().unwrap())
        } else {
            Some(json!({
                "compositeFilter": {
                    "op": "AND",
                    "filters": filters
                }
            }))
        };

        // Fetch from Firestore in a loop to handle post-query filtering (rejected, dismissed, tags).
        // These can't be reliably filtered in Firestore (fields may not exist on all docs),
        // so we filter in Rust. Keep fetching until we have enough or Firestore is exhausted.
        let order_by = json!([
            {"field": {"fieldPath": "scoring"}, "direction": "DESCENDING"},
            {"field": {"fieldPath": "created_at"}, "direction": "DESCENDING"}
        ]);
        let mut memories: Vec<MemoryDB> = Vec::new();
        let mut current_offset = offset;
        let fetch_batch = limit.max(500);

        loop {
            let mut structured_query = json!({
                "from": [{"collectionId": MEMORIES_SUBCOLLECTION}],
                "orderBy": order_by.clone(),
                "limit": fetch_batch,
                "offset": current_offset
            });

            if let Some(ref where_filter) = where_clause {
                structured_query["where"] = where_filter.clone();
            }

            let query = json!({
                "structuredQuery": structured_query
            });

            let response = self
                .build_request(reqwest::Method::POST, &format!("{}:runQuery", parent))
                .await?
                .json(&query)
                .send()
                .await?;

            if !response.status().is_success() {
                let error_text = response.text().await?;
                tracing::error!("Firestore query error: {}", error_text);
                break;
            }

            let results: Vec<Value> = response.json().await?;
            let fetched_count = results.iter().filter(|doc| doc.get("document").is_some()).count();

            let batch: Vec<MemoryDB> = results
                .into_iter()
                .filter_map(|doc| {
                    doc.get("document")
                        .and_then(|d| self.parse_memory(d, uid).ok())
                })
                // Filter out rejected memories (matches Python behavior)
                .filter(|m| m.user_review != Some(false))
                // Filter out dismissed memories in-memory (not in Firestore query, since existing
                // memories don't have is_dismissed field - Firestore requires field to exist for filters)
                .filter(|m| include_dismissed || !m.is_dismissed)
                // Filter by remaining tags in-memory (first tag is already filtered by Firestore ARRAY_CONTAINS)
                .filter(|m| {
                    match tags {
                        Some(filter_tags) if filter_tags.len() > 1 => {
                            filter_tags[1..].iter().all(|tag| m.tags.contains(tag))
                        }
                        _ => true,
                    }
                })
                .collect();

            memories.extend(batch);
            current_offset += fetched_count;

            // Stop if Firestore returned fewer than requested (no more data)
            if fetched_count < fetch_batch {
                break;
            }

            // Stop if we have enough items
            if memories.len() >= limit {
                memories.truncate(limit);
                break;
            }
        }

        // Enrich memories with source from linked conversations
        self.enrich_memories_with_source(uid, &mut memories).await;

        Ok(memories)
    }

    /// Get memories for a user (simple version for backward compatibility)
    /// Copied from Python get_memories
    /// Enriches memories with source from linked conversations
    pub async fn get_memories(
        &self,
        uid: &str,
        limit: usize,
    ) -> Result<Vec<MemoryDB>, Box<dyn std::error::Error + Send + Sync>> {
        self.get_memories_filtered(uid, limit, 0, None, None, false).await
    }

    /// Batch fetch conversations and populate source and input_device_name fields on memories
    async fn enrich_memories_with_source(&self, uid: &str, memories: &mut [MemoryDB]) {
        use std::collections::{HashMap, HashSet};

        // Collect unique conversation IDs
        let conversation_ids: HashSet<&str> = memories
            .iter()
            .filter_map(|m| m.conversation_id.as_deref())
            .collect();

        if conversation_ids.is_empty() {
            return;
        }

        // Fetch conversations in parallel (limit to avoid too many concurrent requests)
        // Store both source and input_device_name
        let mut source_map: HashMap<String, (String, Option<String>)> = HashMap::new();

        // Batch fetch - fetch up to 10 at a time
        let ids: Vec<&str> = conversation_ids.into_iter().collect();
        for chunk in ids.chunks(10) {
            let futures: Vec<_> = chunk
                .iter()
                .map(|id| self.get_conversation(uid, id))
                .collect();

            let results = futures::future::join_all(futures).await;

            for (id, result) in chunk.iter().zip(results) {
                if let Ok(Some(conv)) = result {
                    let source_str = format!("{:?}", conv.source).to_lowercase();
                    source_map.insert(id.to_string(), (source_str, conv.input_device_name.clone()));
                }
            }
        }

        // Populate source and input_device_name fields on memories
        for memory in memories.iter_mut() {
            if let Some(conv_id) = &memory.conversation_id {
                if let Some((source, device_name)) = source_map.get(conv_id) {
                    memory.source = Some(source.clone());
                    memory.input_device_name = device_name.clone();
                }
            }
        }
    }

    /// Get a single memory by ID
    pub async fn get_memory(
        &self,
        uid: &str,
        memory_id: &str,
    ) -> Result<Option<MemoryDB>, Box<dyn std::error::Error + Send + Sync>> {
        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            MEMORIES_SUBCOLLECTION,
            memory_id
        );

        let response = self
            .build_request(reqwest::Method::GET, &url)
            .await?
            .send()
            .await?;

        if response.status() == reqwest::StatusCode::NOT_FOUND {
            return Ok(None);
        }

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore error: {}", error_text).into());
        }

        let doc: Value = response.json().await?;
        let memory = self.parse_memory(&doc, uid)?;
        Ok(Some(memory))
    }

    /// Delete a memory by ID
    pub async fn delete_memory(
        &self,
        uid: &str,
        memory_id: &str,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            MEMORIES_SUBCOLLECTION,
            memory_id
        );

        let response = self
            .build_request(reqwest::Method::DELETE, &url)
            .await?
            .send()
            .await?;

        if !response.status().is_success() && response.status() != reqwest::StatusCode::NOT_FOUND {
            let error_text = response.text().await?;
            return Err(format!("Firestore delete error: {}", error_text).into());
        }

        tracing::info!("Deleted memory {} for user {}", memory_id, uid);
        Ok(())
    }

    /// Update memory content
    pub async fn update_memory_content(
        &self,
        uid: &str,
        memory_id: &str,
        content: &str,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let url = format!(
            "{}/{}/{}/{}/{}?updateMask.fieldPaths=content&updateMask.fieldPaths=updated_at",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            MEMORIES_SUBCOLLECTION,
            memory_id
        );

        let now = Utc::now();
        let doc = json!({
            "fields": {
                "content": {"stringValue": content},
                "updated_at": {"timestampValue": now.to_rfc3339()}
            }
        });

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore update error: {}", error_text).into());
        }

        tracing::info!("Updated memory content {} for user {}", memory_id, uid);
        Ok(())
    }

    /// Update memory visibility
    pub async fn update_memory_visibility(
        &self,
        uid: &str,
        memory_id: &str,
        visibility: &str,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let url = format!(
            "{}/{}/{}/{}/{}?updateMask.fieldPaths=visibility&updateMask.fieldPaths=updated_at",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            MEMORIES_SUBCOLLECTION,
            memory_id
        );

        let now = Utc::now();
        let doc = json!({
            "fields": {
                "visibility": {"stringValue": visibility},
                "updated_at": {"timestampValue": now.to_rfc3339()}
            }
        });

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore update error: {}", error_text).into());
        }

        tracing::info!("Updated memory visibility {} for user {}", memory_id, uid);
        Ok(())
    }

    /// Review a memory (approve/reject)
    pub async fn review_memory(
        &self,
        uid: &str,
        memory_id: &str,
        value: bool,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let url = format!(
            "{}/{}/{}/{}/{}?updateMask.fieldPaths=reviewed&updateMask.fieldPaths=user_review&updateMask.fieldPaths=updated_at",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            MEMORIES_SUBCOLLECTION,
            memory_id
        );

        let now = Utc::now();
        let doc = json!({
            "fields": {
                "reviewed": {"booleanValue": true},
                "user_review": {"booleanValue": value},
                "updated_at": {"timestampValue": now.to_rfc3339()}
            }
        });

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore update error: {}", error_text).into());
        }

        tracing::info!("Reviewed memory {} for user {} with value {}", memory_id, uid, value);
        Ok(())
    }

    /// Create a memory (manual or extracted)
    pub async fn create_memory(
        &self,
        uid: &str,
        content: &str,
        visibility: &str,
        category: Option<MemoryCategory>,
        confidence: Option<f64>,
        source_app: Option<&str>,
        context_summary: Option<&str>,
        tags: &[String],
        reasoning: Option<&str>,
        current_activity: Option<&str>,
        source: Option<&str>,
        window_title: Option<&str>,
    ) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
        let memory_id = document_id_from_seed(content);
        let now = Utc::now();

        // Determine if this is a manual memory
        let is_manual = category.is_none() || matches!(category, Some(MemoryCategory::Manual));
        let actual_category = category.unwrap_or(MemoryCategory::Manual);
        let scoring = MemoryDB::calculate_scoring(&actual_category, &now, is_manual);

        let category_str = match actual_category {
            MemoryCategory::System => "system",
            MemoryCategory::Interesting => "interesting",
            MemoryCategory::Manual => "manual",
            // Legacy categories - preserve original value
            MemoryCategory::Core => "core",
            MemoryCategory::Hobbies => "hobbies",
            MemoryCategory::Lifestyle => "lifestyle",
            MemoryCategory::Interests => "interests",
        };

        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            MEMORIES_SUBCOLLECTION,
            memory_id
        );

        // Build tags array for Firestore
        let tags_values: Vec<Value> = tags
            .iter()
            .map(|t| json!({"stringValue": t}))
            .collect();

        // Build fields - always include base fields
        // CRITICAL: Include all fields that Python expects (matching save_memories)
        let mut fields = json!({
            // CRITICAL: id field required - Python model requires this
            "id": {"stringValue": &memory_id},
            // CRITICAL: uid field required - Python model requires this
            "uid": {"stringValue": uid},
            "content": {"stringValue": content},
            "category": {"stringValue": category_str},
            "created_at": {"timestampValue": now.to_rfc3339()},
            "updated_at": {"timestampValue": now.to_rfc3339()},
            "reviewed": {"booleanValue": is_manual},
            "user_review": {"booleanValue": is_manual},
            "visibility": {"stringValue": visibility},
            "manually_added": {"booleanValue": is_manual},
            "scoring": {"stringValue": scoring},
            "is_read": {"booleanValue": false},
            "is_dismissed": {"booleanValue": false},
            // Additional fields for Python compatibility
            "edited": {"booleanValue": false},
            "is_locked": {"booleanValue": false},
            "kg_extracted": {"booleanValue": false},
            "tags": {"arrayValue": {"values": tags_values}}
        });

        // Add optional fields if present
        if let Some(conf) = confidence {
            fields["confidence"] = json!({"doubleValue": conf});
        }
        if let Some(app) = source_app {
            fields["source_app"] = json!({"stringValue": app});
        }
        if let Some(summary) = context_summary {
            fields["context_summary"] = json!({"stringValue": summary});
        }
        if let Some(reason) = reasoning {
            fields["reasoning"] = json!({"stringValue": reason});
        }
        if let Some(activity) = current_activity {
            fields["current_activity"] = json!({"stringValue": activity});
        }
        if let Some(src) = source {
            fields["source"] = json!({"stringValue": src});
        }
        if let Some(wt) = window_title {
            fields["window_title"] = json!({"stringValue": wt});
        }

        let doc = json!({ "fields": fields });

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore create error: {}", error_text).into());
        }

        tracing::info!("Created memory {} for user {} (category: {})", memory_id, uid, category_str);
        Ok(memory_id)
    }

    /// Create a manual memory (convenience wrapper)
    pub async fn create_manual_memory(
        &self,
        uid: &str,
        content: &str,
        visibility: &str,
    ) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
        self.create_memory(uid, content, visibility, None, None, None, None, &[], None, None, None, None).await
    }

    /// Update memory read/dismissed status
    pub async fn update_memory_read_status(
        &self,
        uid: &str,
        memory_id: &str,
        is_read: Option<bool>,
        is_dismissed: Option<bool>,
    ) -> Result<MemoryDB, Box<dyn std::error::Error + Send + Sync>> {
        let mut update_fields = vec!["updated_at"];
        let mut fields = json!({
            "updated_at": {"timestampValue": Utc::now().to_rfc3339()}
        });

        if let Some(read) = is_read {
            update_fields.push("is_read");
            fields["is_read"] = json!({"booleanValue": read});
        }
        if let Some(dismissed) = is_dismissed {
            update_fields.push("is_dismissed");
            fields["is_dismissed"] = json!({"booleanValue": dismissed});
        }

        let update_mask = update_fields
            .iter()
            .map(|f| format!("updateMask.fieldPaths={}", f))
            .collect::<Vec<_>>()
            .join("&");

        let url = format!(
            "{}/{}/{}/{}/{}?{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            MEMORIES_SUBCOLLECTION,
            memory_id,
            update_mask
        );

        let doc = json!({ "fields": fields });

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore update error: {}", error_text).into());
        }

        tracing::info!("Updated memory {} read status for user {}", memory_id, uid);

        // Fetch and return the updated memory
        self.get_memory(uid, memory_id)
            .await?
            .ok_or_else(|| "Memory not found after update".into())
    }

    /// Mark all memories as read
    pub async fn mark_all_memories_read(
        &self,
        uid: &str,
    ) -> Result<usize, Box<dyn std::error::Error + Send + Sync>> {
        // First get all unread memories
        let parent = format!("{}/{}/{}", self.base_url(), USERS_COLLECTION, uid);

        let query = json!({
            "structuredQuery": {
                "from": [{"collectionId": MEMORIES_SUBCOLLECTION}],
                "where": {
                    "fieldFilter": {
                        "field": {"fieldPath": "is_read"},
                        "op": "EQUAL",
                        "value": {"booleanValue": false}
                    }
                },
                "limit": 500
            }
        });

        let response = self
            .build_request(reqwest::Method::POST, &format!("{}:runQuery", parent))
            .await?
            .json(&query)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore query error: {}", error_text).into());
        }

        let results: Vec<Value> = response.json().await?;
        let memory_ids: Vec<String> = results
            .iter()
            .filter_map(|doc| {
                doc.get("document")
                    .and_then(|d| d.get("name"))
                    .and_then(|n| n.as_str())
                    .map(|s| s.split('/').last().unwrap_or("").to_string())
            })
            .filter(|id| !id.is_empty())
            .collect();

        let count = memory_ids.len();

        // Update each memory
        for memory_id in memory_ids {
            let url = format!(
                "{}/{}/{}/{}/{}?updateMask.fieldPaths=is_read&updateMask.fieldPaths=updated_at",
                self.base_url(),
                USERS_COLLECTION,
                uid,
                MEMORIES_SUBCOLLECTION,
                memory_id
            );

            let doc = json!({
                "fields": {
                    "is_read": {"booleanValue": true},
                    "updated_at": {"timestampValue": Utc::now().to_rfc3339()}
                }
            });

            let _ = self
                .build_request(reqwest::Method::PATCH, &url)
                .await?
                .json(&doc)
                .send()
                .await;
        }

        tracing::info!("Marked {} memories as read for user {}", count, uid);
        Ok(count)
    }

    /// Update visibility of all memories for a user
    pub async fn update_all_memories_visibility(
        &self,
        uid: &str,
        visibility: &str,
    ) -> Result<usize, Box<dyn std::error::Error + Send + Sync>> {
        // Get all memories
        let parent = format!("{}/{}/{}", self.base_url(), USERS_COLLECTION, uid);

        let query = json!({
            "structuredQuery": {
                "from": [{"collectionId": MEMORIES_SUBCOLLECTION}],
                "limit": 1000
            }
        });

        let response = self
            .build_request(reqwest::Method::POST, &format!("{}:runQuery", parent))
            .await?
            .json(&query)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore query error: {}", error_text).into());
        }

        let results: Vec<Value> = response.json().await?;
        let memory_ids: Vec<String> = results
            .iter()
            .filter_map(|doc| {
                doc.get("document")
                    .and_then(|d| d.get("name"))
                    .and_then(|n| n.as_str())
                    .map(|s| s.split('/').last().unwrap_or("").to_string())
            })
            .filter(|id| !id.is_empty())
            .collect();

        let count = memory_ids.len();

        // Update each memory's visibility
        for memory_id in memory_ids {
            let url = format!(
                "{}/{}/{}/{}/{}?updateMask.fieldPaths=visibility&updateMask.fieldPaths=updated_at",
                self.base_url(),
                USERS_COLLECTION,
                uid,
                MEMORIES_SUBCOLLECTION,
                memory_id
            );

            let doc = json!({
                "fields": {
                    "visibility": {"stringValue": visibility},
                    "updated_at": {"timestampValue": Utc::now().to_rfc3339()}
                }
            });

            let _ = self
                .build_request(reqwest::Method::PATCH, &url)
                .await?
                .json(&doc)
                .send()
                .await;
        }

        tracing::info!(
            "Updated visibility to '{}' for {} memories for user {}",
            visibility,
            count,
            uid
        );
        Ok(count)
    }

    /// Delete all memories for a user
    pub async fn delete_all_memories(
        &self,
        uid: &str,
    ) -> Result<usize, Box<dyn std::error::Error + Send + Sync>> {
        // Get all memories
        let parent = format!("{}/{}/{}", self.base_url(), USERS_COLLECTION, uid);

        let query = json!({
            "structuredQuery": {
                "from": [{"collectionId": MEMORIES_SUBCOLLECTION}],
                "limit": 1000
            }
        });

        let response = self
            .build_request(reqwest::Method::POST, &format!("{}:runQuery", parent))
            .await?
            .json(&query)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore query error: {}", error_text).into());
        }

        let results: Vec<Value> = response.json().await?;
        let memory_ids: Vec<String> = results
            .iter()
            .filter_map(|doc| {
                doc.get("document")
                    .and_then(|d| d.get("name"))
                    .and_then(|n| n.as_str())
                    .map(|s| s.split('/').last().unwrap_or("").to_string())
            })
            .filter(|id| !id.is_empty())
            .collect();

        let count = memory_ids.len();

        // Delete each memory
        for memory_id in memory_ids {
            let url = format!(
                "{}/{}/{}/{}/{}",
                self.base_url(),
                USERS_COLLECTION,
                uid,
                MEMORIES_SUBCOLLECTION,
                memory_id
            );

            let _ = self
                .build_request(reqwest::Method::DELETE, &url)
                .await?
                .send()
                .await;
        }

        tracing::info!("Deleted {} memories for user {}", count, uid);
        Ok(count)
    }

    /// Save memories to Firestore
    /// Memory IDs are generated from content hash to enable deduplication
    /// Copied from Python save_memories
    pub async fn save_memories(
        &self,
        uid: &str,
        conversation_id: &str,
        memories: &[Memory],
    ) -> Result<Vec<String>, Box<dyn std::error::Error + Send + Sync>> {
        let mut saved_ids = Vec::new();
        let now = Utc::now();

        for memory in memories {
            let memory_id = document_id_from_seed(&memory.content);
            let scoring = MemoryDB::calculate_scoring(&memory.category, &now, false);

            let url = format!(
                "{}/{}/{}/{}/{}",
                self.base_url(),
                USERS_COLLECTION,
                uid,
                MEMORIES_SUBCOLLECTION,
                memory_id
            );

            let doc = json!({
                "fields": {
                    // CRITICAL: Include id field - Python model requires this
                    "id": {"stringValue": memory_id},
                    // Include uid - Python model requires this
                    "uid": {"stringValue": uid},
                    "content": {"stringValue": memory.content},
                    "category": {"stringValue": format!("{:?}", memory.category).to_lowercase()},
                    "created_at": {"timestampValue": now.to_rfc3339()},
                    "updated_at": {"timestampValue": now.to_rfc3339()},
                    "conversation_id": {"stringValue": conversation_id},
                    // Legacy field - same as conversation_id, used by get_memory_ids_for_conversation
                    "memory_id": {"stringValue": conversation_id},
                    "reviewed": {"booleanValue": false},
                    // CRITICAL: user_review must exist - Python filters on memory['user_review'] is not False
                    // None/null means not yet reviewed by user (different from False which means rejected)
                    "user_review": {"nullValue": null},
                    "visibility": {"stringValue": "private"},
                    "manually_added": {"booleanValue": false},
                    "edited": {"booleanValue": false},
                    "is_locked": {"booleanValue": false},
                    "kg_extracted": {"booleanValue": false},
                    "scoring": {"stringValue": scoring},
                    // Empty tags array
                    "tags": {"arrayValue": {"values": []}}
                }
            });

            let response = self
                .build_request(reqwest::Method::PATCH, &url)
                .await?
                .json(&doc)
                .send()
                .await?;

            if response.status().is_success() {
                saved_ids.push(memory_id);
            } else {
                tracing::warn!("Failed to save memory: {}", response.text().await?);
            }
        }

        tracing::info!(
            "Saved {} memories for conversation {}",
            saved_ids.len(),
            conversation_id
        );
        Ok(saved_ids)
    }

    // =========================================================================
    // ACTION ITEMS
    // =========================================================================

    /// Get action items for a user
    /// Path: users/{uid}/action_items
    #[allow(clippy::too_many_arguments)]
    pub async fn get_action_items(
        &self,
        uid: &str,
        limit: usize,
        offset: usize,
        completed_filter: Option<bool>,
        conversation_id: Option<&str>,
        start_date: Option<&str>,
        end_date: Option<&str>,
        due_start_date: Option<&str>,
        due_end_date: Option<&str>,
        sort_by: Option<&str>,
        include_deleted: Option<bool>,
    ) -> Result<Vec<ActionItemDB>, Box<dyn std::error::Error + Send + Sync>> {
        let parent = format!("{}/{}/{}", self.base_url(), USERS_COLLECTION, uid);

        // Build filters
        let mut filters: Vec<Value> = Vec::new();

        if let Some(completed) = completed_filter {
            filters.push(json!({
                "fieldFilter": {
                    "field": {"fieldPath": "completed"},
                    "op": "EQUAL",
                    "value": {"booleanValue": completed}
                }
            }));
        }

        // Conversation ID filter
        if let Some(conv_id) = conversation_id {
            filters.push(json!({
                "fieldFilter": {
                    "field": {"fieldPath": "conversation_id"},
                    "op": "EQUAL",
                    "value": {"stringValue": conv_id}
                }
            }));
        }

        // Date range filters for created_at
        if let Some(start) = start_date {
            filters.push(json!({
                "fieldFilter": {
                    "field": {"fieldPath": "created_at"},
                    "op": "GREATER_THAN_OR_EQUAL",
                    "value": {"timestampValue": start}
                }
            }));
        }

        if let Some(end) = end_date {
            filters.push(json!({
                "fieldFilter": {
                    "field": {"fieldPath": "created_at"},
                    "op": "LESS_THAN_OR_EQUAL",
                    "value": {"timestampValue": end}
                }
            }));
        }

        // Date range filters for due_at
        if let Some(due_start) = due_start_date {
            filters.push(json!({
                "fieldFilter": {
                    "field": {"fieldPath": "due_at"},
                    "op": "GREATER_THAN_OR_EQUAL",
                    "value": {"timestampValue": due_start}
                }
            }));
        }

        if let Some(due_end) = due_end_date {
            filters.push(json!({
                "fieldFilter": {
                    "field": {"fieldPath": "due_at"},
                    "op": "LESS_THAN_OR_EQUAL",
                    "value": {"timestampValue": due_end}
                }
            }));
        }

        // Build the where clause
        let where_clause = if filters.is_empty() {
            None
        } else if filters.len() == 1 {
            Some(filters.into_iter().next().unwrap())
        } else {
            Some(json!({
                "compositeFilter": {
                    "op": "AND",
                    "filters": filters
                }
            }))
        };

        // Build order by clause based on sort_by parameter
        let order_by = match sort_by {
            Some("due_at") => json!([
                {"field": {"fieldPath": "due_at"}, "direction": "ASCENDING"},
                {"field": {"fieldPath": "created_at"}, "direction": "DESCENDING"}
            ]),
            Some("priority") => json!([
                {"field": {"fieldPath": "priority"}, "direction": "DESCENDING"},
                {"field": {"fieldPath": "created_at"}, "direction": "DESCENDING"}
            ]),
            _ => json!([
                {"field": {"fieldPath": "created_at"}, "direction": "DESCENDING"}
            ]),
        };

        // Fetch from Firestore in a loop to handle post-query deleted filtering.
        // Since `deleted` can't be reliably filtered in Firestore (most docs lack the field),
        // we filter in Rust. But this means a single Firestore page may yield fewer items
        // than requested after filtering, so we keep fetching until we have enough or Firestore
        // is exhausted.
        let mut action_items: Vec<ActionItemDB> = Vec::new();
        let mut current_offset = offset;
        let fetch_batch = limit.max(500); // fetch in large batches to minimize round-trips

        loop {
            let mut structured_query = json!({
                "from": [{"collectionId": ACTION_ITEMS_SUBCOLLECTION}],
                "orderBy": order_by.clone(),
                "limit": fetch_batch,
                "offset": current_offset
            });

            if let Some(ref where_filter) = where_clause {
                structured_query["where"] = where_filter.clone();
            }

            let query = json!({
                "structuredQuery": structured_query
            });

            let response = self
                .build_request(reqwest::Method::POST, &format!("{}:runQuery", parent))
                .await?
                .json(&query)
                .send()
                .await?;

            if !response.status().is_success() {
                let error_text = response.text().await?;
                tracing::error!("Firestore query error: {}", error_text);
                break;
            }

            let results: Vec<Value> = response.json().await?;
            let fetched_count = results.iter().filter(|doc| doc.get("document").is_some()).count();

            let batch: Vec<ActionItemDB> = results
                .into_iter()
                .filter_map(|doc| {
                    doc.get("document")
                        .and_then(|d| self.parse_action_item(d).ok())
                })
                // Filter based on deleted status
                .filter(|item| {
                    if include_deleted == Some(true) {
                        item.deleted == Some(true)
                    } else {
                        item.deleted != Some(true)
                    }
                })
                .collect();

            action_items.extend(batch);
            current_offset += fetched_count;

            // Stop if Firestore returned fewer than requested (no more data)
            if fetched_count < fetch_batch {
                break;
            }

            // Stop if we have enough items
            if action_items.len() >= limit {
                action_items.truncate(limit);
                break;
            }
        }

        // Enrich action items that have conversation_id but no source
        self.enrich_action_items_with_source(uid, &mut action_items).await;

        // Post-query sort matching Python backend behavior (used by iOS/Flutter app):
        // 1. Items WITH due_at come first (sorted by due_at ascending)
        // 2. Items WITHOUT due_at come last
        // 3. Tie-breaker: created_at descending (newest first)
        action_items.sort_by(|a, b| {
            match (&a.due_at, &b.due_at) {
                (Some(due_a), Some(due_b)) => {
                    due_a.cmp(due_b).then_with(|| b.created_at.cmp(&a.created_at))
                }
                (Some(_), None) => std::cmp::Ordering::Less,
                (None, Some(_)) => std::cmp::Ordering::Greater,
                (None, None) => b.created_at.cmp(&a.created_at),
            }
        });

        Ok(action_items)
    }

    /// Batch fetch conversations and populate source field on action items
    /// For items with conversation_id but no source, derives source as "transcription:{conversation.source}"
    async fn enrich_action_items_with_source(&self, uid: &str, action_items: &mut [ActionItemDB]) {
        use std::collections::{HashMap, HashSet};

        // Collect unique conversation IDs from items that need enrichment
        // (have conversation_id but no source)
        let conversation_ids: HashSet<&str> = action_items
            .iter()
            .filter(|item| item.source.is_none() && item.conversation_id.is_some())
            .filter_map(|item| item.conversation_id.as_deref())
            .collect();

        if conversation_ids.is_empty() {
            return;
        }

        tracing::debug!(
            "Enriching {} action items with source from {} conversations",
            action_items.iter().filter(|i| i.source.is_none()).count(),
            conversation_ids.len()
        );

        // Fetch conversations in parallel (limit to avoid too many concurrent requests)
        let mut source_map: HashMap<String, String> = HashMap::new();

        // Batch fetch - fetch up to 10 at a time
        let ids: Vec<&str> = conversation_ids.into_iter().collect();
        for chunk in ids.chunks(10) {
            let futures: Vec<_> = chunk
                .iter()
                .map(|id| self.get_conversation(uid, id))
                .collect();

            let results = futures::future::join_all(futures).await;

            for (id, result) in chunk.iter().zip(results) {
                if let Ok(Some(conv)) = result {
                    // Format as "transcription:{source}" to match expected values
                    // e.g., "transcription:omi", "transcription:desktop"
                    let source_str = format!("transcription:{:?}", conv.source).to_lowercase();
                    source_map.insert(id.to_string(), source_str);
                }
            }
        }

        // Populate source field on action items that don't have one
        for item in action_items.iter_mut() {
            if item.source.is_none() {
                if let Some(conv_id) = &item.conversation_id {
                    item.source = source_map.get(conv_id).cloned();
                }
            }
        }
    }

    /// Get a single action item by ID
    pub async fn get_action_item_by_id(
        &self,
        uid: &str,
        item_id: &str,
    ) -> Result<Option<ActionItemDB>, Box<dyn std::error::Error + Send + Sync>> {
        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            ACTION_ITEMS_SUBCOLLECTION,
            item_id
        );

        let response = self
            .build_request(reqwest::Method::GET, &url)
            .await?
            .send()
            .await?;

        if response.status() == reqwest::StatusCode::NOT_FOUND {
            return Ok(None);
        }

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore get error: {}", error_text).into());
        }

        let doc: Value = response.json().await?;
        let mut action_item = self.parse_action_item(&doc)?;

        // Enrich with source from conversation if needed
        if action_item.source.is_none() {
            if let Some(conv_id) = &action_item.conversation_id {
                if let Ok(Some(conv)) = self.get_conversation(uid, conv_id).await {
                    action_item.source = Some(format!("transcription:{:?}", conv.source).to_lowercase());
                }
            }
        }

        Ok(Some(action_item))
    }

    /// Update an action item
    pub async fn update_action_item(
        &self,
        uid: &str,
        item_id: &str,
        completed: Option<bool>,
        description: Option<&str>,
        due_at: Option<DateTime<Utc>>,
        priority: Option<&str>,
        category: Option<&str>,
        goal_id: Option<&str>,
        relevance_score: Option<i32>,
        sort_order: Option<i32>,
        indent_level: Option<i32>,
        recurrence_rule: Option<&str>,
    ) -> Result<ActionItemDB, Box<dyn std::error::Error + Send + Sync>> {
        // Build update mask and fields
        let mut field_paths: Vec<&str> = vec!["updated_at"];
        let mut fields = json!({
            "updated_at": {"timestampValue": Utc::now().to_rfc3339()}
        });

        if let Some(c) = completed {
            field_paths.push("completed");
            fields["completed"] = json!({"booleanValue": c});

            // Set or clear completed_at based on completion status
            field_paths.push("completed_at");
            if c {
                fields["completed_at"] = json!({"timestampValue": Utc::now().to_rfc3339()});
            } else {
                // Clear completed_at when marking as incomplete (matches Python backend behavior)
                fields["completed_at"] = json!({"nullValue": null});
            }
        }

        if let Some(d) = description {
            field_paths.push("description");
            fields["description"] = json!({"stringValue": d});
        }

        if let Some(due) = due_at {
            field_paths.push("due_at");
            fields["due_at"] = json!({"timestampValue": due.to_rfc3339()});
        }

        if let Some(pri) = priority {
            field_paths.push("priority");
            fields["priority"] = json!({"stringValue": pri});
        }

        if let Some(cat) = category {
            field_paths.push("category");
            fields["category"] = json!({"stringValue": cat});
        }

        if let Some(gid) = goal_id {
            field_paths.push("goal_id");
            fields["goal_id"] = json!({"stringValue": gid});
        }

        if let Some(score) = relevance_score {
            field_paths.push("relevance_score");
            fields["relevance_score"] = json!({"integerValue": score.to_string()});
        }

        if let Some(order) = sort_order {
            field_paths.push("sort_order");
            fields["sort_order"] = json!({"integerValue": order.to_string()});
        }

        if let Some(indent) = indent_level {
            field_paths.push("indent_level");
            fields["indent_level"] = json!({"integerValue": indent.to_string()});
        }

        if let Some(rule) = recurrence_rule {
            field_paths.push("recurrence_rule");
            if rule.is_empty() {
                fields["recurrence_rule"] = json!({"nullValue": null});
            } else {
                fields["recurrence_rule"] = json!({"stringValue": rule});
            }
        }

        let update_mask = field_paths
            .iter()
            .map(|p| format!("updateMask.fieldPaths={}", p))
            .collect::<Vec<_>>()
            .join("&");

        let url = format!(
            "{}/{}/{}/{}/{}?{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            ACTION_ITEMS_SUBCOLLECTION,
            item_id,
            update_mask
        );

        let doc = json!({"fields": fields});

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore update error: {}", error_text).into());
        }

        // Parse and return the updated document
        let updated_doc: Value = response.json().await?;
        let mut action_item = self.parse_action_item(&updated_doc)?;

        // Enrich with source from conversation if needed
        if action_item.source.is_none() {
            if let Some(conv_id) = &action_item.conversation_id {
                if let Ok(Some(conv)) = self.get_conversation(uid, conv_id).await {
                    action_item.source = Some(format!("transcription:{:?}", conv.source).to_lowercase());
                }
            }
        }

        tracing::info!("Updated action item {} for user {}", item_id, uid);
        Ok(action_item)
    }

    /// Delete an action item
    pub async fn delete_action_item(
        &self,
        uid: &str,
        item_id: &str,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            ACTION_ITEMS_SUBCOLLECTION,
            item_id
        );

        let response = self
            .build_request(reqwest::Method::DELETE, &url)
            .await?
            .send()
            .await?;

        if !response.status().is_success() && response.status() != reqwest::StatusCode::NOT_FOUND {
            let error_text = response.text().await?;
            return Err(format!("Firestore delete error: {}", error_text).into());
        }

        tracing::info!("Deleted action item {} for user {}", item_id, uid);
        Ok(())
    }

    /// Soft-delete an action item (mark as deleted without removing from Firestore)
    pub async fn soft_delete_action_item(
        &self,
        uid: &str,
        item_id: &str,
        deleted_by: &str,
        reason: &str,
        kept_task_id: &str,
    ) -> Result<ActionItemDB, Box<dyn std::error::Error + Send + Sync>> {
        let field_paths = vec![
            "deleted", "deleted_by", "deleted_at", "deleted_reason", "kept_task_id", "updated_at",
        ];

        let fields = json!({
            "deleted": {"booleanValue": true},
            "deleted_by": {"stringValue": deleted_by},
            "deleted_at": {"timestampValue": Utc::now().to_rfc3339()},
            "deleted_reason": {"stringValue": reason},
            "kept_task_id": {"stringValue": kept_task_id},
            "updated_at": {"timestampValue": Utc::now().to_rfc3339()}
        });

        let update_mask = field_paths
            .iter()
            .map(|p| format!("updateMask.fieldPaths={}", p))
            .collect::<Vec<_>>()
            .join("&");

        let url = format!(
            "{}/{}/{}/{}/{}?{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            ACTION_ITEMS_SUBCOLLECTION,
            item_id,
            update_mask
        );

        let doc = json!({"fields": fields});

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore soft-delete error: {}", error_text).into());
        }

        let updated_doc: Value = response.json().await?;
        let action_item = self.parse_action_item(&updated_doc)?;

        tracing::info!("Soft-deleted action item {} for user {} (by: {}, reason: {})", item_id, uid, deleted_by, reason);
        Ok(action_item)
    }

    /// Save action items to Firestore
    /// Create a single action item (for API/desktop creation)
    pub async fn create_action_item(
        &self,
        uid: &str,
        description: &str,
        due_at: Option<DateTime<Utc>>,
        source: Option<&str>,
        priority: Option<&str>,
        metadata: Option<&str>,
        category: Option<&str>,
        relevance_score: Option<i32>,
        from_staged: Option<bool>,
        recurrence_rule: Option<&str>,
        recurrence_parent_id: Option<&str>,
    ) -> Result<ActionItemDB, Box<dyn std::error::Error + Send + Sync>> {
        let item_id = uuid::Uuid::new_v4().to_string();
        let now = Utc::now();

        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            ACTION_ITEMS_SUBCOLLECTION,
            item_id
        );

        let mut fields = json!({
            "description": {"stringValue": description},
            "completed": {"booleanValue": false},
            "created_at": {"timestampValue": now.to_rfc3339()},
            "updated_at": {"timestampValue": now.to_rfc3339()}
        });

        if let Some(due) = due_at {
            fields["due_at"] = json!({"timestampValue": due.to_rfc3339()});
        }

        if let Some(src) = source {
            fields["source"] = json!({"stringValue": src});
        }

        if let Some(pri) = priority {
            fields["priority"] = json!({"stringValue": pri});
        }

        if let Some(meta) = metadata {
            fields["metadata"] = json!({"stringValue": meta});
        }

        if let Some(cat) = category {
            fields["category"] = json!({"stringValue": cat});
        }

        if let Some(score) = relevance_score {
            fields["relevance_score"] = json!({"integerValue": score.to_string()});
        }

        if let Some(staged) = from_staged {
            fields["from_staged"] = json!({"booleanValue": staged});
        }

        if let Some(rule) = recurrence_rule {
            fields["recurrence_rule"] = json!({"stringValue": rule});
        }

        if let Some(pid) = recurrence_parent_id {
            fields["recurrence_parent_id"] = json!({"stringValue": pid});
        }

        let doc = json!({"fields": fields});

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore create error: {}", error_text).into());
        }

        // Parse and return the created document
        let created_doc: Value = response.json().await?;
        let action_item = self.parse_action_item(&created_doc)?;

        tracing::info!(
            "Created action item {} for user {} with source={:?}",
            item_id,
            uid,
            source
        );
        Ok(action_item)
    }

    /// Batch update relevance scores for multiple action items using Firestore commit API.
    /// Processes up to 500 writes per commit (Firestore limit).
    pub async fn batch_update_scores(
        &self,
        uid: &str,
        scores: &[(String, i32)],
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let now = Utc::now();

        for chunk in scores.chunks(500) {
            let writes: Vec<Value> = chunk
                .iter()
                .map(|(item_id, score)| {
                    let doc_name = format!(
                        "projects/{}/databases/(default)/documents/{}/{}/{}/{}",
                        self.project_id, USERS_COLLECTION, uid, ACTION_ITEMS_SUBCOLLECTION, item_id
                    );
                    json!({
                        "update": {
                            "name": doc_name,
                            "fields": {
                                "relevance_score": {"integerValue": score.to_string()},
                                "updated_at": {"timestampValue": now.to_rfc3339()}
                            }
                        },
                        "updateMask": {
                            "fieldPaths": ["relevance_score", "updated_at"]
                        }
                    })
                })
                .collect();

            let commit_url = format!(
                "https://firestore.googleapis.com/v1/projects/{}/databases/(default)/documents:commit",
                self.project_id
            );

            let body = json!({ "writes": writes });

            let response = self
                .build_request(reqwest::Method::POST, &commit_url)
                .await?
                .json(&body)
                .send()
                .await?;

            if !response.status().is_success() {
                let error_text = response.text().await?;
                return Err(format!("Firestore batch commit error: {}", error_text).into());
            }
        }

        tracing::info!(
            "Batch updated {} relevance scores for user {}",
            scores.len(),
            uid
        );
        Ok(())
    }

    /// Batch update sort orders and indent levels for multiple action items using Firestore commit API.
    pub async fn batch_update_sort_orders(
        &self,
        uid: &str,
        items: &[(String, i32, i32)], // (item_id, sort_order, indent_level)
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let now = Utc::now();

        for chunk in items.chunks(500) {
            let writes: Vec<Value> = chunk
                .iter()
                .map(|(item_id, sort_order, indent_level)| {
                    let doc_name = format!(
                        "projects/{}/databases/(default)/documents/{}/{}/{}/{}",
                        self.project_id, USERS_COLLECTION, uid, ACTION_ITEMS_SUBCOLLECTION, item_id
                    );
                    json!({
                        "update": {
                            "name": doc_name,
                            "fields": {
                                "sort_order": {"integerValue": sort_order.to_string()},
                                "indent_level": {"integerValue": indent_level.to_string()},
                                "updated_at": {"timestampValue": now.to_rfc3339()}
                            }
                        },
                        "updateMask": {
                            "fieldPaths": ["sort_order", "indent_level", "updated_at"]
                        }
                    })
                })
                .collect();

            let commit_url = format!(
                "https://firestore.googleapis.com/v1/projects/{}/databases/(default)/documents:commit",
                self.project_id
            );

            let body = json!({ "writes": writes });

            let response = self
                .build_request(reqwest::Method::POST, &commit_url)
                .await?
                .json(&body)
                .send()
                .await?;

            if !response.status().is_success() {
                let error_text = response.text().await?;
                return Err(format!("Firestore batch commit error: {}", error_text).into());
            }
        }

        tracing::info!(
            "Batch updated {} sort orders for user {}",
            items.len(),
            uid
        );
        Ok(())
    }

    // =========================================================================
    // STAGED TASKS
    // =========================================================================

    /// Create a staged task in the staged_tasks subcollection.
    /// Same schema as action_items but stored separately for promotion workflow.
    pub async fn create_staged_task(
        &self,
        uid: &str,
        description: &str,
        due_at: Option<DateTime<Utc>>,
        source: Option<&str>,
        priority: Option<&str>,
        metadata: Option<&str>,
        category: Option<&str>,
        relevance_score: Option<i32>,
    ) -> Result<ActionItemDB, Box<dyn std::error::Error + Send + Sync>> {
        // Reject empty descriptions
        let description = description.trim();
        if description.is_empty() {
            return Err("Cannot create staged task with empty description".into());
        }

        // Check for exact-match duplicate (case-insensitive)
        let existing = self.get_staged_tasks(uid, 200, 0).await.unwrap_or_default();
        let desc_lower = description.to_lowercase();
        if existing.iter().any(|t| t.description.trim().to_lowercase() == desc_lower) {
            tracing::info!(
                "Skipping duplicate staged task for user {}: {}",
                uid,
                &description[..description.len().min(80)]
            );
            // Return the existing item instead of creating a duplicate
            let existing_item = existing
                .into_iter()
                .find(|t| t.description.trim().to_lowercase() == desc_lower)
                .unwrap();
            return Ok(existing_item);
        }

        let item_id = uuid::Uuid::new_v4().to_string();
        let now = Utc::now();

        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            STAGED_TASKS_SUBCOLLECTION,
            item_id
        );

        let mut fields = json!({
            "description": {"stringValue": description},
            "completed": {"booleanValue": false},
            "created_at": {"timestampValue": now.to_rfc3339()},
            "updated_at": {"timestampValue": now.to_rfc3339()}
        });

        if let Some(due) = due_at {
            fields["due_at"] = json!({"timestampValue": due.to_rfc3339()});
        }
        if let Some(src) = source {
            fields["source"] = json!({"stringValue": src});
        }
        if let Some(pri) = priority {
            fields["priority"] = json!({"stringValue": pri});
        }
        if let Some(meta) = metadata {
            fields["metadata"] = json!({"stringValue": meta});
        }
        if let Some(cat) = category {
            fields["category"] = json!({"stringValue": cat});
        }
        if let Some(score) = relevance_score {
            fields["relevance_score"] = json!({"integerValue": score.to_string()});
        }

        let doc = json!({"fields": fields});

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore create staged task error: {}", error_text).into());
        }

        let created_doc: Value = response.json().await?;
        let item = self.parse_action_item(&created_doc)?;

        tracing::info!(
            "Created staged task {} for user {} with source={:?}",
            item_id,
            uid,
            source
        );
        Ok(item)
    }

    /// Migrate action items that were created by the old conversation extraction path
    /// (have conversation_id but no source field) to staged_tasks.
    /// Returns (migrated_count, deleted_count).
    pub async fn migrate_conversation_action_items_to_staged(
        &self,
        uid: &str,
    ) -> Result<(usize, usize), Box<dyn std::error::Error + Send + Sync>> {
        // Fetch all incomplete, non-deleted action items.
        // NOTE: get_action_items runs enrich_action_items_with_source which populates
        // the source field from the conversation. So we can't check source.is_none()
        // after that. Instead, we filter by conversation_id.is_some() — all items with
        // a conversation_id were created by the old save_action_items path (confirmed
        // 0 false positives: no items have both conversation_id AND a real source in Firestore).
        let all_items = self
            .get_action_items(uid, 10000, 0, Some(false), None, None, None, None, None, None, None)
            .await?;

        // Filter: has conversation_id → created by old save_action_items path
        let bad_items: Vec<ActionItemDB> = all_items
            .into_iter()
            .filter(|item| item.conversation_id.is_some())
            .collect();

        if bad_items.is_empty() {
            tracing::info!("No conversation action items to migrate for user {}", uid);
            return Ok((0, 0));
        }

        tracing::info!(
            "Found {} conversation action items to migrate for user {}",
            bad_items.len(),
            uid
        );

        // Use batch_migrate_to_staged for fast batch commits (250 items per batch)
        let migrated = self.batch_migrate_to_staged(uid, &bad_items).await?;

        tracing::info!(
            "Migration complete for user {}: {} migrated out of {} candidates",
            uid,
            migrated,
            bad_items.len()
        );

        Ok((migrated, migrated))
    }

    /// Get staged tasks ordered by relevance_score ASC (best ranked first).
    /// Filters out deleted and completed tasks.
    pub async fn get_staged_tasks(
        &self,
        uid: &str,
        limit: usize,
        offset: usize,
    ) -> Result<Vec<ActionItemDB>, Box<dyn std::error::Error + Send + Sync>> {
        let parent = format!("{}/{}/{}", self.base_url(), USERS_COLLECTION, uid);

        // Query non-completed staged tasks ordered by relevance_score ASC
        let filters = vec![
            json!({
                "fieldFilter": {
                    "field": {"fieldPath": "completed"},
                    "op": "EQUAL",
                    "value": {"booleanValue": false}
                }
            }),
        ];

        let query = json!({
            "structuredQuery": {
                "from": [{"collectionId": STAGED_TASKS_SUBCOLLECTION}],
                "where": {
                    "compositeFilter": {
                        "op": "AND",
                        "filters": filters
                    }
                },
                "orderBy": [
                    {"field": {"fieldPath": "relevance_score"}, "direction": "ASCENDING"},
                    {"field": {"fieldPath": "created_at"}, "direction": "DESCENDING"}
                ],
                "limit": limit + offset
            }
        });

        let query_url = format!("{}:runQuery", parent);
        let response = self
            .build_request(reqwest::Method::POST, &query_url)
            .await?
            .json(&query)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore query staged tasks error: {}", error_text).into());
        }

        let results: Vec<Value> = response.json().await?;
        let items: Vec<ActionItemDB> = results
            .iter()
            .filter_map(|r| r.get("document"))
            .filter_map(|doc| self.parse_action_item(doc).ok())
            .filter(|item| item.deleted != Some(true))
            .skip(offset)
            .collect();

        Ok(items)
    }

    /// Hard-delete a staged task (permanently remove from Firestore).
    pub async fn delete_staged_task(
        &self,
        uid: &str,
        item_id: &str,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            STAGED_TASKS_SUBCOLLECTION,
            item_id
        );

        let response = self
            .build_request(reqwest::Method::DELETE, &url)
            .await?
            .send()
            .await?;

        if !response.status().is_success() && response.status() != reqwest::StatusCode::NOT_FOUND {
            let error_text = response.text().await?;
            return Err(format!("Firestore delete staged task error: {}", error_text).into());
        }

        tracing::info!("Deleted staged task {} for user {}", item_id, uid);
        Ok(())
    }

    /// Batch update relevance scores for staged tasks.
    pub async fn batch_update_staged_scores(
        &self,
        uid: &str,
        scores: &[(String, i32)],
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let now = Utc::now();

        for chunk in scores.chunks(500) {
            let writes: Vec<Value> = chunk
                .iter()
                .map(|(item_id, score)| {
                    let doc_name = format!(
                        "projects/{}/databases/(default)/documents/{}/{}/{}/{}",
                        self.project_id, USERS_COLLECTION, uid, STAGED_TASKS_SUBCOLLECTION, item_id
                    );
                    json!({
                        "update": {
                            "name": doc_name,
                            "fields": {
                                "relevance_score": {"integerValue": score.to_string()},
                                "updated_at": {"timestampValue": now.to_rfc3339()}
                            }
                        },
                        "updateMask": {
                            "fieldPaths": ["relevance_score", "updated_at"]
                        }
                    })
                })
                .collect();

            let commit_url = format!(
                "https://firestore.googleapis.com/v1/projects/{}/databases/(default)/documents:commit",
                self.project_id
            );

            let body = json!({ "writes": writes });

            let response = self
                .build_request(reqwest::Method::POST, &commit_url)
                .await?
                .json(&body)
                .send()
                .await?;

            if !response.status().is_success() {
                let error_text = response.text().await?;
                return Err(format!("Firestore batch commit staged scores error: {}", error_text).into());
            }
        }

        tracing::info!(
            "Batch updated {} staged task scores for user {}",
            scores.len(),
            uid
        );
        Ok(())
    }

    /// Batch migrate tasks from action_items to staged_tasks using Firestore commit API.
    /// Each task is created in staged_tasks and deleted from action_items atomically.
    /// Processes 250 tasks per commit (each needs 2 writes, Firestore limit is 500).
    pub async fn batch_migrate_to_staged(
        &self,
        uid: &str,
        tasks: &[ActionItemDB],
    ) -> Result<usize, Box<dyn std::error::Error + Send + Sync>> {
        let now = Utc::now();
        let mut migrated_count = 0;

        // 250 tasks per batch (each task = 2 writes: create + delete, limit 500)
        for chunk in tasks.chunks(250) {
            let mut writes: Vec<Value> = Vec::new();

            for task in chunk {
                let staged_id = uuid::Uuid::new_v4().to_string();
                let staged_doc_name = format!(
                    "projects/{}/databases/(default)/documents/{}/{}/{}/{}",
                    self.project_id, USERS_COLLECTION, uid, STAGED_TASKS_SUBCOLLECTION, staged_id
                );

                let mut fields = json!({
                    "description": {"stringValue": &task.description},
                    "completed": {"booleanValue": false},
                    "created_at": {"timestampValue": now.to_rfc3339()},
                    "updated_at": {"timestampValue": now.to_rfc3339()}
                });
                if let Some(ref due) = task.due_at {
                    fields["due_at"] = json!({"timestampValue": due.to_rfc3339()});
                }
                if let Some(ref src) = task.source {
                    fields["source"] = json!({"stringValue": src});
                }
                if let Some(ref pri) = task.priority {
                    fields["priority"] = json!({"stringValue": pri});
                }
                if let Some(ref meta) = task.metadata {
                    fields["metadata"] = json!({"stringValue": meta});
                }
                if let Some(ref cat) = task.category {
                    fields["category"] = json!({"stringValue": cat});
                }
                if let Some(score) = task.relevance_score {
                    fields["relevance_score"] = json!({"integerValue": score.to_string()});
                }

                // Write 1: Create in staged_tasks
                writes.push(json!({
                    "update": {
                        "name": staged_doc_name,
                        "fields": fields
                    }
                }));

                // Write 2: Delete from action_items
                let action_doc_name = format!(
                    "projects/{}/databases/(default)/documents/{}/{}/{}/{}",
                    self.project_id, USERS_COLLECTION, uid, ACTION_ITEMS_SUBCOLLECTION, task.id
                );
                writes.push(json!({
                    "delete": action_doc_name
                }));
            }

            let commit_url = format!(
                "https://firestore.googleapis.com/v1/projects/{}/databases/(default)/documents:commit",
                self.project_id
            );

            let body = json!({ "writes": writes });

            let response = self
                .build_request(reqwest::Method::POST, &commit_url)
                .await?
                .json(&body)
                .send()
                .await?;

            if !response.status().is_success() {
                let error_text = response.text().await?;
                return Err(format!("Firestore batch migrate commit error: {}", error_text).into());
            }

            migrated_count += chunk.len();
            tracing::info!(
                "Batch migrated {} tasks ({} total so far) for user {}",
                chunk.len(),
                migrated_count,
                uid
            );
        }

        Ok(migrated_count)
    }

    /// Count active AI action items promoted from staged_tasks (from_staged=true, not completed, not deleted).
    /// Used by the promotion system to determine if more tasks should be promoted.
    pub async fn count_active_ai_action_items(
        &self,
        uid: &str,
    ) -> Result<usize, Box<dyn std::error::Error + Send + Sync>> {
        let parent = format!("{}/{}/{}", self.base_url(), USERS_COLLECTION, uid);

        // Composite filter: from_staged=true AND completed=false at Firestore level
        // so we don't miss items when users have thousands of action_items
        let query = json!({
            "structuredQuery": {
                "from": [{"collectionId": ACTION_ITEMS_SUBCOLLECTION}],
                "where": {
                    "compositeFilter": {
                        "op": "AND",
                        "filters": [
                            {
                                "fieldFilter": {
                                    "field": {"fieldPath": "completed"},
                                    "op": "EQUAL",
                                    "value": {"booleanValue": false}
                                }
                            },
                            {
                                "fieldFilter": {
                                    "field": {"fieldPath": "from_staged"},
                                    "op": "EQUAL",
                                    "value": {"booleanValue": true}
                                }
                            }
                        ]
                    }
                },
                "limit": 100
            }
        });

        let query_url = format!("{}:runQuery", parent);
        let response = self
            .build_request(reqwest::Method::POST, &query_url)
            .await?
            .json(&query)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore count AI items error: {}", error_text).into());
        }

        let results: Vec<Value> = response.json().await?;
        let count = results
            .iter()
            .filter_map(|r| r.get("document"))
            .filter_map(|doc| self.parse_action_item(doc).ok())
            .filter(|item| {
                item.deleted != Some(true)
                    && item.from_staged == Some(true)
            })
            .count();

        Ok(count)
    }

    /// Get active AI action items promoted from staged_tasks (from_staged=true, not completed, not deleted).
    /// Returns the actual items for dedup comparison during promotion.
    /// Uses a composite filter to query from_staged=true AND completed=false at the Firestore level.
    pub async fn get_active_ai_action_items(
        &self,
        uid: &str,
    ) -> Result<Vec<ActionItemDB>, Box<dyn std::error::Error + Send + Sync>> {
        let parent = format!("{}/{}/{}", self.base_url(), USERS_COLLECTION, uid);

        let query = json!({
            "structuredQuery": {
                "from": [{"collectionId": ACTION_ITEMS_SUBCOLLECTION}],
                "where": {
                    "compositeFilter": {
                        "op": "AND",
                        "filters": [
                            {
                                "fieldFilter": {
                                    "field": {"fieldPath": "completed"},
                                    "op": "EQUAL",
                                    "value": {"booleanValue": false}
                                }
                            },
                            {
                                "fieldFilter": {
                                    "field": {"fieldPath": "from_staged"},
                                    "op": "EQUAL",
                                    "value": {"booleanValue": true}
                                }
                            }
                        ]
                    }
                },
                "limit": 100
            }
        });

        let query_url = format!("{}:runQuery", parent);
        let response = self
            .build_request(reqwest::Method::POST, &query_url)
            .await?
            .json(&query)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore get active AI items error: {}", error_text).into());
        }

        let results: Vec<Value> = response.json().await?;
        let items: Vec<ActionItemDB> = results
            .iter()
            .filter_map(|r| r.get("document"))
            .filter_map(|doc| self.parse_action_item(doc).ok())
            .filter(|item| {
                item.deleted != Some(true)
                    && item.from_staged == Some(true)
            })
            .collect();

        Ok(items)
    }

    /// Get a single staged task by ID.
    pub async fn get_staged_task_by_id(
        &self,
        uid: &str,
        item_id: &str,
    ) -> Result<Option<ActionItemDB>, Box<dyn std::error::Error + Send + Sync>> {
        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            STAGED_TASKS_SUBCOLLECTION,
            item_id
        );

        let response = self
            .build_request(reqwest::Method::GET, &url)
            .await?
            .send()
            .await?;

        if response.status() == reqwest::StatusCode::NOT_FOUND {
            return Ok(None);
        }

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore get staged task error: {}", error_text).into());
        }

        let doc: Value = response.json().await?;
        let item = self.parse_action_item(&doc)?;
        Ok(Some(item))
    }

    // =========================================================================
    // APPS
    // =========================================================================

    /// Get all apps with optional filters
    pub async fn get_apps(
        &self,
        uid: &str,
        limit: usize,
        offset: usize,
        capability: Option<&str>,
        category: Option<&str>,
    ) -> Result<Vec<AppSummary>, Box<dyn std::error::Error + Send + Sync>> {
        let parent = self.base_url();

        // Build filters (matching Python backend: approved=True AND private=False)
        let mut filters: Vec<Value> = vec![
            // Only approved apps
            json!({
                "fieldFilter": {
                    "field": {"fieldPath": "approved"},
                    "op": "EQUAL",
                    "value": {"booleanValue": true}
                }
            }),
            // Only public apps (not private)
            json!({
                "fieldFilter": {
                    "field": {"fieldPath": "private"},
                    "op": "EQUAL",
                    "value": {"booleanValue": false}
                }
            }),
        ];

        if let Some(cat) = category {
            filters.push(json!({
                "fieldFilter": {
                    "field": {"fieldPath": "category"},
                    "op": "EQUAL",
                    "value": {"stringValue": cat}
                }
            }));
        }

        // Build where clause
        let where_clause = if filters.len() == 1 {
            filters.into_iter().next()
        } else {
            Some(json!({
                "compositeFilter": {
                    "op": "AND",
                    "filters": filters
                }
            }))
        };

        // Note: We don't use orderBy in the query because it would require a composite index
        // Instead, we fetch all matching apps and sort in memory (matching Python backend behavior)
        let mut structured_query = json!({
            "from": [{"collectionId": APPS_COLLECTION}]
        });

        if let Some(where_filter) = where_clause {
            structured_query["where"] = where_filter;
        }

        let query = json!({
            "structuredQuery": structured_query
        });

        let response = self
            .build_request(reqwest::Method::POST, &format!("{}:runQuery", parent))
            .await?
            .json(&query)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            tracing::error!("Firestore query error: {}", error_text);
            return Ok(vec![]);
        }

        let results: Vec<Value> = response.json().await?;

        // Get user's enabled apps to mark them
        let enabled_app_ids = self.get_enabled_app_ids(uid).await.unwrap_or_default();

        let mut apps: Vec<AppSummary> = results
            .into_iter()
            .filter_map(|doc| {
                doc.get("document")
                    .and_then(|d| self.parse_app_summary(d).ok())
            })
            .collect();

        // Filter by capability if specified
        if let Some(cap) = capability {
            apps.retain(|app| app.capabilities.contains(&cap.to_string()));
        }

        // Mark enabled apps
        for app in &mut apps {
            app.enabled = enabled_app_ids.contains(&app.id);
        }

        // Sort by installs descending (in memory, to avoid needing composite index)
        apps.sort_by(|a, b| b.installs.cmp(&a.installs));

        // Apply pagination
        let start = offset.min(apps.len());
        let end = (offset + limit).min(apps.len());
        Ok(apps[start..end].to_vec())
    }

    /// Get approved public apps
    pub async fn get_approved_apps(
        &self,
        uid: &str,
        limit: usize,
        offset: usize,
    ) -> Result<Vec<AppSummary>, Box<dyn std::error::Error + Send + Sync>> {
        self.get_apps(uid, limit, offset, None, None).await
    }

    /// Get popular apps (apps marked with is_popular=true, matching Python backend behavior)
    pub async fn get_popular_apps(
        &self,
        uid: &str,
        limit: usize,
    ) -> Result<Vec<AppSummary>, Box<dyn std::error::Error + Send + Sync>> {
        let parent = self.base_url();

        // Query for apps where approved=true AND is_popular=true (matching Python backend)
        let filters = vec![
            json!({
                "fieldFilter": {
                    "field": {"fieldPath": "approved"},
                    "op": "EQUAL",
                    "value": {"booleanValue": true}
                }
            }),
            json!({
                "fieldFilter": {
                    "field": {"fieldPath": "is_popular"},
                    "op": "EQUAL",
                    "value": {"booleanValue": true}
                }
            }),
        ];

        let where_clause = json!({
            "compositeFilter": {
                "op": "AND",
                "filters": filters
            }
        });

        let query = json!({
            "structuredQuery": {
                "from": [{"collectionId": APPS_COLLECTION}],
                "where": where_clause
            }
        });

        let response = self
            .build_request(reqwest::Method::POST, &format!("{}:runQuery", parent))
            .await?
            .json(&query)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            tracing::error!("Firestore query error for popular apps: {}", error_text);
            return Ok(vec![]);
        }

        let results: Vec<Value> = response.json().await?;

        // Get user's enabled apps to mark them
        let enabled_app_ids = self.get_enabled_app_ids(uid).await.unwrap_or_default();

        let mut apps: Vec<AppSummary> = results
            .into_iter()
            .filter_map(|doc| {
                doc.get("document")
                    .and_then(|d| self.parse_app_summary(d).ok())
            })
            .collect();

        // Mark enabled apps
        for app in &mut apps {
            app.enabled = enabled_app_ids.contains(&app.id);
        }

        // Sort by installs descending (matching Python backend behavior)
        apps.sort_by(|a, b| b.installs.cmp(&a.installs));

        apps.truncate(limit);
        Ok(apps)
    }

    /// Search apps with filters
    pub async fn search_apps(
        &self,
        uid: &str,
        query: Option<&str>,
        category: Option<&str>,
        capability: Option<&str>,
        min_rating: Option<i32>,
        my_apps: bool,
        installed_only: bool,
        limit: usize,
        offset: usize,
    ) -> Result<Vec<AppSummary>, Box<dyn std::error::Error + Send + Sync>> {
        // Start with all apps
        let mut apps = self.get_apps(uid, 500, 0, capability, category).await?;

        // Filter by query (name/description)
        if let Some(q) = query {
            let q_lower = q.to_lowercase();
            apps.retain(|app| {
                app.name.to_lowercase().contains(&q_lower)
                    || app.description.to_lowercase().contains(&q_lower)
            });
        }

        // Filter by minimum rating
        if let Some(min) = min_rating {
            apps.retain(|app| app.rating_avg.unwrap_or(0.0) >= min as f64);
        }

        // Filter by my apps (apps owned by the user)
        if my_apps {
            // For now, we don't have uid in AppSummary, so skip this filter
            // In a full implementation, we'd need to check app.uid == uid
        }

        // Filter by installed only
        if installed_only {
            apps.retain(|app| app.enabled);
        }

        // Apply pagination
        let start = offset.min(apps.len());
        let end = (offset + limit).min(apps.len());
        Ok(apps[start..end].to_vec())
    }

    /// Get a single app by ID
    pub async fn get_app(
        &self,
        uid: &str,
        app_id: &str,
    ) -> Result<Option<App>, Box<dyn std::error::Error + Send + Sync>> {
        let url = format!("{}/{}/{}", self.base_url(), APPS_COLLECTION, app_id);

        let response = self
            .build_request(reqwest::Method::GET, &url)
            .await?
            .send()
            .await?;

        if response.status() == reqwest::StatusCode::NOT_FOUND {
            return Ok(None);
        }

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore error: {}", error_text).into());
        }

        let doc: Value = response.json().await?;
        let mut app = self.parse_app(&doc)?;

        // Check if enabled for user
        let enabled_ids = self.get_enabled_app_ids(uid).await.unwrap_or_default();
        app.enabled = enabled_ids.contains(&app.id);

        Ok(Some(app))
    }

    /// Get reviews for an app
    pub async fn get_app_reviews(
        &self,
        app_id: &str,
    ) -> Result<Vec<AppReview>, Box<dyn std::error::Error + Send + Sync>> {
        let parent = format!("{}/{}/{}", self.base_url(), APPS_COLLECTION, app_id);

        let query = json!({
            "structuredQuery": {
                "from": [{"collectionId": "reviews"}],
                "orderBy": [{"field": {"fieldPath": "rated_at"}, "direction": "DESCENDING"}],
                "limit": 100
            }
        });

        let response = self
            .build_request(reqwest::Method::POST, &format!("{}:runQuery", parent))
            .await?
            .json(&query)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            tracing::error!("Firestore query error: {}", error_text);
            return Ok(vec![]);
        }

        let results: Vec<Value> = response.json().await?;
        let reviews = results
            .into_iter()
            .filter_map(|doc| {
                doc.get("document")
                    .and_then(|d| self.parse_app_review(d).ok())
            })
            .collect();

        Ok(reviews)
    }

    /// Enable an app for a user
    pub async fn enable_app(
        &self,
        uid: &str,
        app_id: &str,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            ENABLED_APPS_SUBCOLLECTION,
            app_id
        );

        let now = Utc::now();
        let doc = json!({
            "fields": {
                "app_id": {"stringValue": app_id},
                "enabled_at": {"timestampValue": now.to_rfc3339()}
            }
        });

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Failed to enable app: {}", error_text).into());
        }

        // Increment install count on the app
        self.increment_app_installs(app_id).await?;

        tracing::info!("Enabled app {} for user {}", app_id, uid);
        Ok(())
    }

    /// Disable an app for a user
    pub async fn disable_app(
        &self,
        uid: &str,
        app_id: &str,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            ENABLED_APPS_SUBCOLLECTION,
            app_id
        );

        let response = self
            .build_request(reqwest::Method::DELETE, &url)
            .await?
            .send()
            .await?;

        if !response.status().is_success() && response.status() != reqwest::StatusCode::NOT_FOUND {
            let error_text = response.text().await?;
            return Err(format!("Failed to disable app: {}", error_text).into());
        }

        tracing::info!("Disabled app {} for user {}", app_id, uid);
        Ok(())
    }

    /// Get user's enabled app IDs
    async fn get_enabled_app_ids(
        &self,
        uid: &str,
    ) -> Result<Vec<String>, Box<dyn std::error::Error + Send + Sync>> {
        let parent = format!("{}/{}/{}", self.base_url(), USERS_COLLECTION, uid);

        let query = json!({
            "structuredQuery": {
                "from": [{"collectionId": ENABLED_APPS_SUBCOLLECTION}],
                "limit": 500
            }
        });

        let response = self
            .build_request(reqwest::Method::POST, &format!("{}:runQuery", parent))
            .await?
            .json(&query)
            .send()
            .await?;

        if !response.status().is_success() {
            return Ok(vec![]);
        }

        let results: Vec<Value> = response.json().await?;
        let ids = results
            .into_iter()
            .filter_map(|doc| {
                let d = doc.get("document")?;
                let name = d.get("name")?.as_str()?;
                Some(name.split('/').last()?.to_string())
            })
            .collect();

        Ok(ids)
    }

    /// Get user's enabled apps as summaries
    pub async fn get_enabled_apps(
        &self,
        uid: &str,
    ) -> Result<Vec<AppSummary>, Box<dyn std::error::Error + Send + Sync>> {
        let enabled_ids = self.get_enabled_app_ids(uid).await?;

        let mut apps = Vec::new();
        for app_id in enabled_ids {
            if let Ok(Some(app)) = self.get_app(uid, &app_id).await {
                let mut summary = AppSummary::from(app);
                summary.enabled = true;
                apps.push(summary);
            }
        }

        Ok(apps)
    }

    /// Get user's enabled apps with full App details (for integration triggers)
    pub async fn get_enabled_apps_full(
        &self,
        uid: &str,
    ) -> Result<Vec<App>, Box<dyn std::error::Error + Send + Sync>> {
        let enabled_ids = self.get_enabled_app_ids(uid).await?;

        let mut apps = Vec::new();
        for app_id in enabled_ids {
            if let Ok(Some(mut app)) = self.get_app(uid, &app_id).await {
                app.enabled = true;
                apps.push(app);
            }
        }

        Ok(apps)
    }

    /// Increment app install count
    async fn increment_app_installs(
        &self,
        app_id: &str,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        // First get current installs
        let app = match self.get_app("", app_id).await? {
            Some(a) => a,
            None => return Ok(()),
        };

        let new_installs = app.installs + 1;

        let url = format!(
            "{}/{}/{}?updateMask.fieldPaths=installs",
            self.base_url(),
            APPS_COLLECTION,
            app_id
        );

        let doc = json!({
            "fields": {
                "installs": {"integerValue": new_installs.to_string()}
            }
        });

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            tracing::warn!("Failed to increment app installs: {}", response.text().await?);
        }

        Ok(())
    }

    /// Submit a review for an app
    pub async fn submit_app_review(
        &self,
        uid: &str,
        app_id: &str,
        score: i32,
        review: &str,
    ) -> Result<AppReview, Box<dyn std::error::Error + Send + Sync>> {
        let url = format!(
            "{}/{}/{}/reviews/{}",
            self.base_url(),
            APPS_COLLECTION,
            app_id,
            uid
        );

        let now = Utc::now();
        let doc = json!({
            "fields": {
                "uid": {"stringValue": uid},
                "score": {"integerValue": score.to_string()},
                "review": {"stringValue": review},
                "rated_at": {"timestampValue": now.to_rfc3339()}
            }
        });

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Failed to submit review: {}", error_text).into());
        }

        // Update app's rating average and count
        self.update_app_rating(app_id).await?;

        Ok(AppReview {
            uid: uid.to_string(),
            score,
            review: review.to_string(),
            response: None,
            rated_at: now,
            edited_at: None,
        })
    }

    /// Update app's rating average and count
    async fn update_app_rating(
        &self,
        app_id: &str,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let reviews = self.get_app_reviews(app_id).await?;

        if reviews.is_empty() {
            return Ok(());
        }

        let total: i32 = reviews.iter().map(|r| r.score).sum();
        let count = reviews.len() as i32;
        let avg = total as f64 / count as f64;

        let url = format!(
            "{}/{}/{}?updateMask.fieldPaths=rating_avg&updateMask.fieldPaths=rating_count",
            self.base_url(),
            APPS_COLLECTION,
            app_id
        );

        let doc = json!({
            "fields": {
                "rating_avg": {"doubleValue": avg},
                "rating_count": {"integerValue": count.to_string()}
            }
        });

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            tracing::warn!("Failed to update app rating: {}", response.text().await?);
        }

        Ok(())
    }

    /// Parse Firestore document to App
    fn parse_app(
        &self,
        doc: &Value,
    ) -> Result<App, Box<dyn std::error::Error + Send + Sync>> {
        let fields = doc.get("fields").ok_or("Missing fields in document")?;
        let name = doc.get("name").and_then(|n| n.as_str()).unwrap_or("");
        let id = name.split('/').last().unwrap_or("").to_string();

        Ok(App {
            id,
            name: self.parse_string(fields, "name").unwrap_or_default(),
            description: self.parse_string(fields, "description").unwrap_or_default(),
            image: self.parse_string(fields, "image").unwrap_or_default(),
            category: self.parse_string(fields, "category").unwrap_or_else(|| "other".to_string()),
            author: self.parse_string(fields, "author").unwrap_or_default(),
            email: self.parse_string(fields, "email"),
            capabilities: self.parse_string_array(fields, "capabilities"),
            uid: self.parse_string(fields, "uid"),
            approved: self.parse_bool(fields, "approved").unwrap_or(false),
            private: self.parse_bool(fields, "private").unwrap_or(false),
            status: self.parse_string(fields, "status").unwrap_or_else(|| "under-review".to_string()),
            chat_prompt: self.parse_string(fields, "chat_prompt"),
            memory_prompt: self.parse_string(fields, "memory_prompt"),
            persona_prompt: self.parse_string(fields, "persona_prompt"),
            external_integration: None, // TODO: Parse nested object
            proactive_notification: None, // TODO: Parse nested object
            chat_tools: vec![], // TODO: Parse array of nested objects
            installs: self.parse_int(fields, "installs").unwrap_or(0),
            rating_avg: self.parse_float(fields, "rating_avg"),
            rating_count: self.parse_int(fields, "rating_count").unwrap_or(0),
            is_paid: self.parse_bool(fields, "is_paid").unwrap_or(false),
            price: self.parse_float(fields, "price"),
            payment_plan: self.parse_string(fields, "payment_plan"),
            username: self.parse_string(fields, "username"),
            twitter: self.parse_string(fields, "twitter"),
            created_at: self.parse_timestamp_optional(fields, "created_at"),
            enabled: false, // Will be set by caller
        })
    }

    /// Parse Firestore document to AppSummary
    fn parse_app_summary(
        &self,
        doc: &Value,
    ) -> Result<AppSummary, Box<dyn std::error::Error + Send + Sync>> {
        let fields = doc.get("fields").ok_or("Missing fields in document")?;
        let name = doc.get("name").and_then(|n| n.as_str()).unwrap_or("");
        let id = name.split('/').last().unwrap_or("").to_string();

        // Parse has_auth_steps from external_integration.auth_steps
        // Structure: external_integration: { mapValue: { fields: { auth_steps: { arrayValue: { values: [...] } } } } }
        let has_auth_steps = fields
            .get("external_integration")
            .and_then(|ei| ei.get("mapValue"))
            .and_then(|mv| mv.get("fields"))
            .and_then(|f| f.get("auth_steps"))
            .and_then(|as_| as_.get("arrayValue"))
            .and_then(|av| av.get("values"))
            .and_then(|v| v.as_array())
            .map(|arr| !arr.is_empty())
            .unwrap_or(false);

        Ok(AppSummary {
            id,
            name: self.parse_string(fields, "name").unwrap_or_default(),
            description: self.parse_string(fields, "description").unwrap_or_default(),
            image: self.parse_string(fields, "image").unwrap_or_default(),
            category: self.parse_string(fields, "category").unwrap_or_else(|| "other".to_string()),
            author: self.parse_string(fields, "author").unwrap_or_default(),
            capabilities: self.parse_string_array(fields, "capabilities"),
            approved: self.parse_bool(fields, "approved").unwrap_or(false),
            private: self.parse_bool(fields, "private").unwrap_or(false),
            installs: self.parse_int(fields, "installs").unwrap_or(0),
            rating_avg: self.parse_float(fields, "rating_avg"),
            rating_count: self.parse_int(fields, "rating_count").unwrap_or(0),
            is_paid: self.parse_bool(fields, "is_paid").unwrap_or(false),
            price: self.parse_float(fields, "price"),
            enabled: false, // Will be set by caller
            has_auth_steps,
        })
    }

    /// Parse Firestore document to AppReview
    fn parse_app_review(
        &self,
        doc: &Value,
    ) -> Result<AppReview, Box<dyn std::error::Error + Send + Sync>> {
        let fields = doc.get("fields").ok_or("Missing fields")?;
        let name = doc.get("name").and_then(|n| n.as_str()).unwrap_or("");
        let uid = name.split('/').last().unwrap_or("").to_string();

        Ok(AppReview {
            uid,
            score: self.parse_int(fields, "score").unwrap_or(0),
            review: self.parse_string(fields, "review").unwrap_or_default(),
            response: self.parse_string(fields, "response"),
            rated_at: self.parse_timestamp_optional(fields, "rated_at").unwrap_or_else(Utc::now),
            edited_at: self.parse_timestamp_optional(fields, "edited_at"),
        })
    }

    /// Parse string array from Firestore
    fn parse_string_array(&self, fields: &Value, key: &str) -> Vec<String> {
        fields
            .get(key)
            .and_then(|v| v.get("arrayValue"))
            .and_then(|a| a.get("values"))
            .and_then(|v| v.as_array())
            .map(|arr| {
                arr.iter()
                    .filter_map(|v| v.get("stringValue")?.as_str().map(|s| s.to_string()))
                    .collect()
            })
            .unwrap_or_default()
    }

    // =========================================================================
    // PARSING HELPERS
    // =========================================================================

    /// Parse Firestore document to Conversation
    /// Decrypts transcript_segments and photos if data_protection_level is "enhanced"
    fn parse_conversation(
        &self,
        doc: &Value,
        uid: &str,
    ) -> Result<Conversation, Box<dyn std::error::Error + Send + Sync>> {
        let fields = doc
            .get("fields")
            .ok_or("Missing fields in document")?;
        let name = doc.get("name").and_then(|n| n.as_str()).unwrap_or("");
        let id = name.split('/').last().unwrap_or("").to_string();

        // Use created_at as fallback for missing timestamps
        let created_at = self.parse_timestamp_optional(fields, "created_at")
            .unwrap_or_else(Utc::now);
        let started_at = self.parse_timestamp_optional(fields, "started_at")
            .unwrap_or(created_at);
        let finished_at = self.parse_timestamp_optional(fields, "finished_at")
            .unwrap_or(created_at);

        // Parse apps_results
        let apps_results = self.parse_apps_results(fields);

        Ok(Conversation {
            id,
            created_at,
            started_at,
            finished_at,
            source: self.parse_string(fields, "source")
                .and_then(|s| serde_json::from_str(&format!("\"{}\"", s)).ok())
                .unwrap_or_default(),
            language: self.parse_string(fields, "language").unwrap_or_default(),
            status: self.parse_string(fields, "status")
                .and_then(|s| serde_json::from_str(&format!("\"{}\"", s)).ok())
                .unwrap_or_default(),
            discarded: self.parse_bool(fields, "discarded").unwrap_or(false),
            deleted: self.parse_bool(fields, "deleted").unwrap_or(false),
            starred: self.parse_bool(fields, "starred").unwrap_or(false),
            is_locked: self.parse_bool(fields, "is_locked").unwrap_or(false),
            folder_id: self.parse_string(fields, "folder_id"),
            structured: self.parse_structured(fields)?,
            transcript_segments: self.parse_transcript_segments(fields, uid)?,
            apps_results,
            geolocation: self.parse_geolocation(fields),
            photos: self.parse_photos(fields, uid),
            input_device_name: self.parse_string(fields, "input_device_name"),
        })
    }

    /// Parse apps_results array from Firestore fields
    fn parse_apps_results(&self, fields: &Value) -> Vec<crate::models::AppResult> {
        let array = match fields.get("apps_results")
            .and_then(|a| a.get("arrayValue"))
            .and_then(|a| a.get("values"))
            .and_then(|a| a.as_array())
        {
            Some(arr) => arr,
            None => return vec![],
        };

        array.iter().filter_map(|item| {
            let map_fields = item.get("mapValue")?.get("fields")?;
            let app_id = self.parse_string(map_fields, "app_id");
            let content = self.parse_string(map_fields, "content").unwrap_or_default();
            Some(crate::models::AppResult { app_id, content })
        }).collect()
    }

    /// Parse Firestore document to ActionItemDB
    fn parse_action_item(
        &self,
        doc: &Value,
    ) -> Result<ActionItemDB, Box<dyn std::error::Error + Send + Sync>> {
        let fields = doc.get("fields").ok_or("Missing fields")?;
        let name = doc.get("name").and_then(|n| n.as_str()).unwrap_or("");
        let id = name.split('/').last().unwrap_or("").to_string();

        Ok(ActionItemDB {
            id,
            description: self.parse_string(fields, "description").unwrap_or_default(),
            completed: self.parse_bool(fields, "completed").unwrap_or(false),
            created_at: self.parse_timestamp_optional(fields, "created_at").unwrap_or_else(Utc::now),
            updated_at: self.parse_timestamp_optional(fields, "updated_at"),
            due_at: self.parse_timestamp_optional(fields, "due_at"),
            completed_at: self.parse_timestamp_optional(fields, "completed_at"),
            conversation_id: self.parse_string(fields, "conversation_id"),
            source: self.parse_string(fields, "source"),
            priority: self.parse_string(fields, "priority"),
            metadata: self.parse_string(fields, "metadata"),
            deleted: self.parse_bool(fields, "deleted").ok(),
            deleted_by: self.parse_string(fields, "deleted_by"),
            deleted_at: self.parse_timestamp_optional(fields, "deleted_at"),
            deleted_reason: self.parse_string(fields, "deleted_reason"),
            kept_task_id: self.parse_string(fields, "kept_task_id"),
            category: self.parse_string(fields, "category"),
            goal_id: self.parse_string(fields, "goal_id"),
            relevance_score: self.parse_int(fields, "relevance_score"),
            sort_order: self.parse_int(fields, "sort_order"),
            indent_level: self.parse_int(fields, "indent_level"),
            from_staged: self.parse_bool(fields, "from_staged").ok(),
            recurrence_rule: self.parse_string(fields, "recurrence_rule"),
            recurrence_parent_id: self.parse_string(fields, "recurrence_parent_id"),
        })
    }

    /// Parse Firestore document to MemoryDB
    /// Decrypts content if data_protection_level is "enhanced" and encryption secret is available.
    fn parse_memory(
        &self,
        doc: &Value,
        uid: &str,
    ) -> Result<MemoryDB, Box<dyn std::error::Error + Send + Sync>> {
        let fields = doc.get("fields").ok_or("Missing fields")?;
        let name = doc.get("name").and_then(|n| n.as_str()).unwrap_or("");
        let id = name.split('/').last().unwrap_or("").to_string();

        // Get raw content
        let mut content = self.parse_string(fields, "content").unwrap_or_default();

        // Check if content is encrypted (data_protection_level = "enhanced")
        let data_protection_level = self.parse_string(fields, "data_protection_level");
        if data_protection_level.as_deref() == Some("enhanced") {
            if let Some(ref secret) = self.encryption_secret {
                match encryption::decrypt(&content, uid, secret) {
                    Ok(decrypted) => content = decrypted,
                    Err(e) => {
                        tracing::warn!("Failed to decrypt memory {}: {}", id, e);
                        content = "[Encrypted content — decryption failed]".to_string();
                    }
                }
            } else {
                tracing::warn!(
                    "Memory {} has enhanced protection but no encryption secret configured",
                    id
                );
                content = "[Encrypted content — decryption failed]".to_string();
            }
        }

        Ok(MemoryDB {
            id: id.clone(),
            uid: "".to_string(), // Not stored in document
            content,
            category: self.parse_string(fields, "category")
                .and_then(|s| serde_json::from_str(&format!("\"{}\"", s)).ok())
                .unwrap_or_default(),
            created_at: self.parse_timestamp(fields, "created_at")?,
            updated_at: self.parse_timestamp(fields, "updated_at")?,
            conversation_id: self.parse_string(fields, "conversation_id"),
            reviewed: self.parse_bool(fields, "reviewed").unwrap_or(false),
            user_review: self.parse_bool(fields, "user_review").ok(),
            visibility: self.parse_string(fields, "visibility").unwrap_or_else(|| "private".to_string()),
            manually_added: self.parse_bool(fields, "manually_added").unwrap_or(false),
            scoring: self.parse_string(fields, "scoring"),
            source: self.parse_string(fields, "source"), // Can be stored directly for tips, or enriched from conversation
            input_device_name: None, // Enriched later from linked conversation
            confidence: self.parse_float(fields, "confidence"),
            source_app: self.parse_string(fields, "source_app"),
            context_summary: self.parse_string(fields, "context_summary"),
            is_read: self.parse_bool(fields, "is_read").unwrap_or(false),
            is_dismissed: self.parse_bool(fields, "is_dismissed").unwrap_or(false),
            tags: self.parse_string_array(fields, "tags"),
            reasoning: self.parse_string(fields, "reasoning"),
            current_activity: self.parse_string(fields, "current_activity"),
            window_title: self.parse_string(fields, "window_title"),
        })
    }

    /// Parse structured data from conversation
    fn parse_structured(
        &self,
        fields: &Value,
    ) -> Result<Structured, Box<dyn std::error::Error + Send + Sync>> {
        let structured = fields.get("structured").and_then(|s| s.get("mapValue")).and_then(|m| m.get("fields"));

        if let Some(s) = structured {
            let title = self.parse_string(s, "title").unwrap_or_default();
            if title.is_empty() {
                tracing::warn!(
                    "DEBUG parse_structured: title is empty! structured fields: {}",
                    serde_json::to_string_pretty(s).unwrap_or_default()
                );
            }
            Ok(Structured {
                title,
                overview: self.parse_string(s, "overview").unwrap_or_default(),
                emoji: self.parse_string(s, "emoji").unwrap_or_else(|| "🧠".to_string()),
                category: self.parse_string(s, "category")
                    .and_then(|c| serde_json::from_str(&format!("\"{}\"", c)).ok())
                    .unwrap_or_default(),
                action_items: self.parse_action_items_from_structured(s),
                events: self.parse_events_from_structured(s),
            })
        } else {
            tracing::warn!(
                "DEBUG parse_structured: no structured field found! fields: {}",
                serde_json::to_string_pretty(fields).unwrap_or_default()
            );
            Ok(Structured::default())
        }
    }

    /// Parse action_items array from structured field
    fn parse_action_items_from_structured(&self, structured_fields: &Value) -> Vec<crate::models::ActionItem> {
        let array = match structured_fields.get("action_items")
            .and_then(|a| a.get("arrayValue"))
            .and_then(|a| a.get("values"))
            .and_then(|a| a.as_array())
        {
            Some(arr) => arr,
            None => return vec![],
        };

        array.iter().filter_map(|item| {
            let map_fields = item.get("mapValue")?.get("fields")?;
            let description = self.parse_string(map_fields, "description").unwrap_or_default();
            let completed = self.parse_bool(map_fields, "completed").unwrap_or(false);
            let due_at = self.parse_timestamp_optional(map_fields, "due_at");
            Some(crate::models::ActionItem { description, completed, due_at, confidence: None, priority: None })
        }).collect()
    }

    /// Parse events array from structured field
    fn parse_events_from_structured(&self, structured_fields: &Value) -> Vec<crate::models::Event> {
        let array = match structured_fields.get("events")
            .and_then(|a| a.get("arrayValue"))
            .and_then(|a| a.get("values"))
            .and_then(|a| a.as_array())
        {
            Some(arr) => arr,
            None => return vec![],
        };

        array.iter().filter_map(|item| {
            let map_fields = item.get("mapValue")?.get("fields")?;
            let title = self.parse_string(map_fields, "title").unwrap_or_default();
            let description = self.parse_string(map_fields, "description").unwrap_or_default();
            let start = self.parse_timestamp_optional(map_fields, "start")?;
            let duration = self.parse_int(map_fields, "duration").unwrap_or(30);
            Some(crate::models::Event { title, description, start, duration })
        }).collect()
    }

    /// Parse geolocation from conversation fields
    fn parse_geolocation(&self, fields: &Value) -> Option<crate::models::Geolocation> {
        let geo = fields.get("geolocation")?.get("mapValue")?.get("fields")?;

        Some(crate::models::Geolocation {
            google_place_id: self.parse_string(geo, "google_place_id"),
            latitude: self.parse_float(geo, "latitude").unwrap_or(0.0),
            longitude: self.parse_float(geo, "longitude").unwrap_or(0.0),
            address: self.parse_string(geo, "address"),
            location_type: self.parse_string(geo, "location_type"),
        })
    }

    /// Parse photos array from conversation fields
    /// Decrypts base64 field if data_protection_level is "enhanced"
    fn parse_photos(&self, fields: &Value, uid: &str) -> Vec<crate::models::ConversationPhoto> {
        let array = match fields.get("photos")
            .and_then(|a| a.get("arrayValue"))
            .and_then(|a| a.get("values"))
            .and_then(|a| a.as_array())
        {
            Some(arr) => arr,
            None => return vec![],
        };

        array.iter().filter_map(|item| {
            let map_fields = item.get("mapValue")?.get("fields")?;
            let id = self.parse_string(map_fields, "id");
            let mut base64 = self.parse_string(map_fields, "base64").unwrap_or_default();
            let description = self.parse_string(map_fields, "description");
            let created_at = self.parse_timestamp_optional(map_fields, "created_at").unwrap_or_else(Utc::now);
            let discarded = self.parse_bool(map_fields, "discarded").unwrap_or(false);

            // Check if photo is encrypted (data_protection_level = "enhanced")
            let data_protection_level = self.parse_string(map_fields, "data_protection_level");
            if data_protection_level.as_deref() == Some("enhanced") {
                if let Some(ref secret) = self.encryption_secret {
                    match encryption::decrypt(&base64, uid, secret) {
                        Ok(decrypted) => base64 = decrypted,
                        Err(e) => {
                            tracing::warn!("Failed to decrypt photo {:?}: {} — skipping", id, e);
                            return None;
                        }
                    }
                } else {
                    tracing::warn!("Photo {:?} has enhanced protection but no encryption secret — skipping", id);
                    return None;
                }
            }

            Some(crate::models::ConversationPhoto { id, base64, description, created_at, discarded })
        }).collect()
    }

    /// Parse transcript segments
    /// Handles plain arrays, zlib-compressed bytes (from OMI device), and encrypted segments.
    /// For encrypted segments (data_protection_level = "enhanced"):
    ///   - Decrypts the base64 string → hex string
    ///   - Converts hex to bytes
    ///   - Decompresses with zlib
    ///   - Parses JSON array
    fn parse_transcript_segments(
        &self,
        fields: &Value,
        uid: &str,
    ) -> Result<Vec<TranscriptSegment>, Box<dyn std::error::Error + Send + Sync>> {
        use flate2::read::ZlibDecoder;
        use std::io::Read;

        let transcript_field = fields.get("transcript_segments");

        // Check if transcript is a string (encrypted for enhanced protection)
        if let Some(string_val) = transcript_field.and_then(|t| t.get("stringValue")).and_then(|s| s.as_str()) {
            let data_protection_level = self.parse_string(fields, "data_protection_level");
            if data_protection_level.as_deref() == Some("enhanced") {
                if let Some(ref secret) = self.encryption_secret {
                    // Decrypt the encrypted string
                    let decrypted_payload = match encryption::decrypt(string_val, uid, secret) {
                        Ok(decrypted) => decrypted,
                        Err(e) => {
                            tracing::warn!("Failed to decrypt transcript segments: {}", e);
                            return Ok(vec![]);
                        }
                    };

                    // Check if compression is used (should always be true for enhanced)
                    let is_compressed = self.parse_bool(fields, "transcript_segments_compressed").unwrap_or(false);

                    if is_compressed {
                        // Decrypted payload is a hex string, convert to bytes
                        match hex::decode(&decrypted_payload) {
                            Ok(compressed_bytes) => {
                                // Decompress with zlib
                                let mut decoder = ZlibDecoder::new(&compressed_bytes[..]);
                                let mut decompressed = String::new();
                                if let Err(e) = decoder.read_to_string(&mut decompressed) {
                                    tracing::warn!("Failed to decompress encrypted transcript segments: {}", e);
                                    return Ok(vec![]);
                                }

                                // Parse JSON array of segments
                                match serde_json::from_str::<Vec<serde_json::Value>>(&decompressed) {
                                    Ok(segments) => {
                                        let result: Vec<TranscriptSegment> = segments
                                            .iter()
                                            .filter_map(|seg| {
                                                Some(TranscriptSegment {
                                                    text: seg.get("text")?.as_str()?.to_string(),
                                                    speaker: seg.get("speaker")
                                                        .and_then(|s| s.as_str())
                                                        .unwrap_or("SPEAKER_00")
                                                        .to_string(),
                                                    speaker_id: seg.get("speaker_id")
                                                        .and_then(|s| s.as_i64())
                                                        .unwrap_or(0) as i32,
                                                    is_user: seg.get("is_user")
                                                        .and_then(|s| s.as_bool())
                                                        .unwrap_or(false),
                                                    person_id: seg.get("person_id")
                                                        .and_then(|s| s.as_str())
                                                        .map(|s| s.to_string()),
                                                    start: seg.get("start")
                                                        .and_then(|s| s.as_f64())
                                                        .unwrap_or(0.0),
                                                    end: seg.get("end")
                                                        .and_then(|s| s.as_f64())
                                                        .unwrap_or(0.0),
                                                })
                                            })
                                            .collect();
                                        tracing::debug!("Decrypted and decompressed {} transcript segments for user {}", result.len(), uid);
                                        return Ok(result);
                                    }
                                    Err(e) => {
                                        tracing::warn!("Failed to parse decrypted transcript segments JSON: {}", e);
                                        return Ok(vec![]);
                                    }
                                }
                            }
                            Err(e) => {
                                tracing::warn!("Failed to decode hex from decrypted transcript: {}", e);
                                return Ok(vec![]);
                            }
                        }
                    } else {
                        // Old format: decrypted payload is JSON directly (backward compatibility)
                        match serde_json::from_str::<Vec<serde_json::Value>>(&decrypted_payload) {
                            Ok(segments) => {
                                let result: Vec<TranscriptSegment> = segments
                                    .iter()
                                    .filter_map(|seg| {
                                        Some(TranscriptSegment {
                                            text: seg.get("text")?.as_str()?.to_string(),
                                            speaker: seg.get("speaker")
                                                .and_then(|s| s.as_str())
                                                .unwrap_or("SPEAKER_00")
                                                .to_string(),
                                            speaker_id: seg.get("speaker_id")
                                                .and_then(|s| s.as_i64())
                                                .unwrap_or(0) as i32,
                                            is_user: seg.get("is_user")
                                                .and_then(|s| s.as_bool())
                                                .unwrap_or(false),
                                            person_id: seg.get("person_id")
                                                .and_then(|s| s.as_str())
                                                .map(|s| s.to_string()),
                                            start: seg.get("start")
                                                .and_then(|s| s.as_f64())
                                                .unwrap_or(0.0),
                                            end: seg.get("end")
                                                .and_then(|s| s.as_f64())
                                                .unwrap_or(0.0),
                                        })
                                    })
                                    .collect();
                                tracing::debug!("Decrypted {} transcript segments (uncompressed) for user {}", result.len(), uid);
                                return Ok(result);
                            }
                            Err(e) => {
                                tracing::warn!("Failed to parse decrypted transcript segments JSON: {}", e);
                                return Ok(vec![]);
                            }
                        }
                    }
                } else {
                    tracing::debug!(
                        "Transcript segments have enhanced protection but no encryption secret configured"
                    );
                    return Ok(vec![]);
                }
            } else {
                // String but not enhanced - shouldn't happen, but return empty
                tracing::debug!("Transcript segments are string format but not enhanced protection");
                return Ok(vec![]);
            }
        }

        // Check if transcript is bytes (zlib compressed) - decompress it
        if let Some(bytes_val) = transcript_field.and_then(|t| t.get("bytesValue")) {
            if let Some(b64_str) = bytes_val.as_str() {
                match self.decompress_transcript_segments(b64_str) {
                    Ok(segments) => {
                        tracing::debug!("Decompressed {} transcript segments", segments.len());
                        return Ok(segments);
                    }
                    Err(e) => {
                        tracing::warn!("Failed to decompress transcript segments: {}", e);
                        return Ok(vec![]);
                    }
                }
            }
        }

        // Handle plain array format
        let segments = transcript_field
            .and_then(|s| s.get("arrayValue"))
            .and_then(|a| a.get("values"))
            .and_then(|v| v.as_array());

        if let Some(segs) = segments {
            Ok(segs
                .iter()
                .filter_map(|seg| {
                    let seg_fields = seg.get("mapValue")?.get("fields")?;
                    Some(TranscriptSegment {
                        text: self.parse_string(seg_fields, "text").unwrap_or_default(),
                        speaker: self.parse_string(seg_fields, "speaker").unwrap_or_else(|| "SPEAKER_00".to_string()),
                        speaker_id: self.parse_int(seg_fields, "speaker_id").unwrap_or(0),
                        is_user: self.parse_bool(seg_fields, "is_user").unwrap_or(false),
                        person_id: self.parse_string(seg_fields, "person_id"),
                        start: self.parse_float(seg_fields, "start").unwrap_or(0.0),
                        end: self.parse_float(seg_fields, "end").unwrap_or(0.0),
                    })
                })
                .collect())
        } else {
            Ok(vec![])
        }
    }

    /// Decompress zlib-compressed transcript segments from base64-encoded bytes
    fn decompress_transcript_segments(
        &self,
        b64_str: &str,
    ) -> Result<Vec<TranscriptSegment>, Box<dyn std::error::Error + Send + Sync>> {
        use flate2::read::ZlibDecoder;
        use std::io::Read;

        // Decode base64 to bytes
        let compressed_bytes = base64::Engine::decode(
            &base64::engine::general_purpose::STANDARD,
            b64_str,
        )?;

        // Decompress with zlib
        let mut decoder = ZlibDecoder::new(&compressed_bytes[..]);
        let mut decompressed = String::new();
        decoder.read_to_string(&mut decompressed)?;

        // Parse JSON array of segments
        let segments: Vec<serde_json::Value> = serde_json::from_str(&decompressed)?;

        // Convert to TranscriptSegment
        Ok(segments
            .iter()
            .filter_map(|seg| {
                Some(TranscriptSegment {
                    text: seg.get("text")?.as_str()?.to_string(),
                    speaker: seg
                        .get("speaker")
                        .and_then(|s| s.as_str())
                        .unwrap_or("SPEAKER_00")
                        .to_string(),
                    speaker_id: seg
                        .get("speaker_id")
                        .and_then(|s| s.as_i64())
                        .unwrap_or(0) as i32,
                    is_user: seg
                        .get("is_user")
                        .and_then(|s| s.as_bool())
                        .unwrap_or(false),
                    person_id: seg
                        .get("person_id")
                        .and_then(|s| s.as_str())
                        .map(|s| s.to_string()),
                    start: seg
                        .get("start")
                        .and_then(|s| s.as_f64())
                        .unwrap_or(0.0),
                    end: seg
                        .get("end")
                        .and_then(|s| s.as_f64())
                        .unwrap_or(0.0),
                })
            })
            .collect())
    }

    /// Convert conversation to Firestore document format
    /// Compresses transcript_segments with zlib to match Python backend format.
    /// If encryption_secret is available, also encrypts (enhanced protection).
    fn conversation_to_firestore(&self, conv: &Conversation, uid: &str) -> Value {
        // Build action_items array for structured
        let action_items_values: Vec<Value> = conv.structured.action_items.iter().map(|item| {
            let mut fields = serde_json::Map::new();
            fields.insert("description".to_string(), json!({"stringValue": item.description}));
            fields.insert("completed".to_string(), json!({"booleanValue": item.completed}));
            if let Some(due_at) = &item.due_at {
                fields.insert("due_at".to_string(), json!({"timestampValue": due_at.to_rfc3339()}));
            }
            json!({"mapValue": {"fields": fields}})
        }).collect();

        // Build events array for structured
        let events_values: Vec<Value> = conv.structured.events.iter().map(|event| {
            json!({
                "mapValue": {
                    "fields": {
                        "title": {"stringValue": event.title},
                        "description": {"stringValue": event.description},
                        "start": {"timestampValue": event.start.to_rfc3339()},
                        "duration": {"integerValue": event.duration.to_string()}
                    }
                }
            })
        }).collect();

        // Build apps_results array
        let apps_results_values: Vec<Value> = conv.apps_results.iter().map(|result| {
            let mut fields = serde_json::Map::new();
            if let Some(app_id) = &result.app_id {
                fields.insert("app_id".to_string(), json!({"stringValue": app_id}));
            }
            fields.insert("content".to_string(), json!({"stringValue": result.content}));
            json!({"mapValue": {"fields": fields}})
        }).collect();

        // Build the main document
        let mut fields = serde_json::Map::new();

        // CRITICAL: Include the id field - Python backend requires this
        fields.insert("id".to_string(), json!({"stringValue": conv.id}));
        fields.insert("created_at".to_string(), json!({"timestampValue": conv.created_at.to_rfc3339()}));
        fields.insert("started_at".to_string(), json!({"timestampValue": conv.started_at.to_rfc3339()}));
        fields.insert("finished_at".to_string(), json!({"timestampValue": conv.finished_at.to_rfc3339()}));
        fields.insert("source".to_string(), json!({"stringValue": format!("{:?}", conv.source).to_lowercase()}));
        fields.insert("language".to_string(), json!({"stringValue": conv.language}));
        fields.insert("status".to_string(), json!({"stringValue": format!("{:?}", conv.status).to_lowercase()}));
        fields.insert("discarded".to_string(), json!({"booleanValue": conv.discarded}));
        fields.insert("deleted".to_string(), json!({"booleanValue": conv.deleted}));
        fields.insert("starred".to_string(), json!({"booleanValue": conv.starred}));
        fields.insert("is_locked".to_string(), json!({"booleanValue": conv.is_locked}));

        // Add folder_id if present
        if let Some(folder_id) = &conv.folder_id {
            fields.insert("folder_id".to_string(), json!({"stringValue": folder_id}));
        }

        // Add geolocation if present
        if let Some(geo) = &conv.geolocation {
            let mut geo_fields = serde_json::Map::new();
            if let Some(place_id) = &geo.google_place_id {
                geo_fields.insert("google_place_id".to_string(), json!({"stringValue": place_id}));
            }
            geo_fields.insert("latitude".to_string(), json!({"doubleValue": geo.latitude}));
            geo_fields.insert("longitude".to_string(), json!({"doubleValue": geo.longitude}));
            if let Some(address) = &geo.address {
                geo_fields.insert("address".to_string(), json!({"stringValue": address}));
            }
            if let Some(loc_type) = &geo.location_type {
                geo_fields.insert("location_type".to_string(), json!({"stringValue": loc_type}));
            }
            fields.insert("geolocation".to_string(), json!({"mapValue": {"fields": geo_fields}}));
        }

        // Add photos array
        if !conv.photos.is_empty() {
            let photos_values: Vec<Value> = conv.photos.iter().map(|photo| {
                let mut photo_fields = serde_json::Map::new();
                if let Some(id) = &photo.id {
                    photo_fields.insert("id".to_string(), json!({"stringValue": id}));
                }
                photo_fields.insert("base64".to_string(), json!({"stringValue": &photo.base64}));
                if let Some(desc) = &photo.description {
                    photo_fields.insert("description".to_string(), json!({"stringValue": desc}));
                }
                photo_fields.insert("created_at".to_string(), json!({"timestampValue": photo.created_at.to_rfc3339()}));
                photo_fields.insert("discarded".to_string(), json!({"booleanValue": photo.discarded}));
                json!({"mapValue": {"fields": photo_fields}})
            }).collect();
            fields.insert("photos".to_string(), json!({"arrayValue": {"values": photos_values}}));
        }

        // Build structured with action_items and events
        let mut structured_fields = serde_json::Map::new();
        structured_fields.insert("title".to_string(), json!({"stringValue": conv.structured.title}));
        structured_fields.insert("overview".to_string(), json!({"stringValue": conv.structured.overview}));
        structured_fields.insert("emoji".to_string(), json!({"stringValue": conv.structured.emoji}));
        structured_fields.insert("category".to_string(), json!({"stringValue": format!("{:?}", conv.structured.category).to_lowercase()}));
        structured_fields.insert("action_items".to_string(), json!({"arrayValue": {"values": action_items_values}}));
        structured_fields.insert("events".to_string(), json!({"arrayValue": {"values": events_values}}));

        fields.insert("structured".to_string(), json!({"mapValue": {"fields": structured_fields}}));

        // Add transcript_segments — compressed (and optionally encrypted) to match Python backend
        {
            use flate2::write::ZlibEncoder;
            use flate2::Compression;
            use std::io::Write;

            // Step 1: Serialize segments to JSON array (matching Python's json.dumps format)
            let segments_json: Vec<serde_json::Value> = conv.transcript_segments.iter().map(|seg| {
                json!({
                    "text": seg.text,
                    "speaker": seg.speaker,
                    "speaker_id": seg.speaker_id,
                    "is_user": seg.is_user,
                    "start": seg.start,
                    "end": seg.end
                })
            }).collect();
            let json_str = serde_json::to_string(&segments_json).unwrap_or_else(|_| "[]".to_string());

            // Step 2: Zlib compress
            let mut encoder = ZlibEncoder::new(Vec::new(), Compression::default());
            let _ = encoder.write_all(json_str.as_bytes());
            let compressed_bytes = encoder.finish().unwrap_or_default();

            // Step 3: Store as compressed bytes or encrypt if secret is available
            if let Some(ref secret) = self.encryption_secret {
                // Enhanced: hex encode compressed bytes → encrypt → store as stringValue
                let hex_str = hex::encode(&compressed_bytes);
                match encryption::encrypt(&hex_str, uid, secret) {
                    Ok(encrypted) => {
                        fields.insert("transcript_segments".to_string(), json!({"stringValue": encrypted}));
                        fields.insert("data_protection_level".to_string(), json!({"stringValue": "enhanced"}));
                    }
                    Err(e) => {
                        tracing::warn!("Failed to encrypt transcript segments: {}, falling back to compressed bytes", e);
                        let b64 = base64::engine::general_purpose::STANDARD.encode(&compressed_bytes);
                        fields.insert("transcript_segments".to_string(), json!({"bytesValue": b64}));
                    }
                }
            } else {
                // Standard: store as bytesValue (Firestore REST API expects base64 for bytes)
                let b64 = base64::engine::general_purpose::STANDARD.encode(&compressed_bytes);
                fields.insert("transcript_segments".to_string(), json!({"bytesValue": b64}));
            }
            fields.insert("transcript_segments_compressed".to_string(), json!({"booleanValue": true}));
        }

        // Add apps_results
        fields.insert("apps_results".to_string(), json!({"arrayValue": {"values": apps_results_values}}));

        // Add input_device_name if present
        if let Some(device_name) = &conv.input_device_name {
            fields.insert("input_device_name".to_string(), json!({"stringValue": device_name}));
        }

        json!({"fields": fields})
    }

    // Field parsing helpers
    fn parse_string(&self, fields: &Value, key: &str) -> Option<String> {
        fields.get(key)?.get("stringValue")?.as_str().map(|s| s.to_string())
    }

    fn parse_bool(&self, fields: &Value, key: &str) -> Result<bool, Box<dyn std::error::Error + Send + Sync>> {
        fields
            .get(key)
            .and_then(|v| v.get("booleanValue"))
            .and_then(|v| v.as_bool())
            .ok_or_else(|| format!("Missing or invalid bool field: {}", key).into())
    }

    fn parse_int(&self, fields: &Value, key: &str) -> Option<i32> {
        fields
            .get(key)?
            .get("integerValue")?
            .as_str()
            .and_then(|s| s.parse().ok())
    }

    fn parse_float(&self, fields: &Value, key: &str) -> Option<f64> {
        fields.get(key)?.get("doubleValue")?.as_f64()
    }

    fn parse_timestamp(
        &self,
        fields: &Value,
        key: &str,
    ) -> Result<DateTime<Utc>, Box<dyn std::error::Error + Send + Sync>> {
        let ts = fields
            .get(key)
            .and_then(|v| v.get("timestampValue"))
            .and_then(|v| v.as_str())
            .ok_or_else(|| format!("Missing timestamp field: {}", key))?;

        DateTime::parse_from_rfc3339(ts)
            .map(|dt| dt.with_timezone(&Utc))
            .map_err(|e| format!("Invalid timestamp {}: {}", key, e).into())
    }

    fn parse_timestamp_optional(&self, fields: &Value, key: &str) -> Option<DateTime<Utc>> {
        fields
            .get(key)
            .and_then(|v| v.get("timestampValue"))
            .and_then(|v| v.as_str())
            .and_then(|ts| DateTime::parse_from_rfc3339(ts).ok())
            .map(|dt| dt.with_timezone(&Utc))
    }

    // =========================================================================
    // USER SETTINGS
    // =========================================================================

    /// Get user document fields
    async fn get_user_document(
        &self,
        uid: &str,
    ) -> Result<Value, Box<dyn std::error::Error + Send + Sync>> {
        let url = format!("{}/{}/{}", self.base_url(), USERS_COLLECTION, uid);

        let response = self
            .build_request(reqwest::Method::GET, &url)
            .await?
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Failed to get user document: {}", error_text).into());
        }

        let doc: Value = response.json().await?;
        Ok(doc)
    }

    /// Update user document fields (partial update)
    async fn update_user_fields(
        &self,
        uid: &str,
        fields: Value,
        update_mask: &[&str],
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let mask_params = update_mask
            .iter()
            .map(|f| format!("updateMask.fieldPaths={}", f))
            .collect::<Vec<_>>()
            .join("&");

        let url = format!(
            "{}/{}/{}?{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            mask_params
        );

        let doc = json!({ "fields": fields });

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Failed to update user fields: {}", error_text).into());
        }

        Ok(())
    }

    /// Get daily summary settings for a user
    pub async fn get_daily_summary_settings(
        &self,
        uid: &str,
    ) -> Result<DailySummarySettings, Box<dyn std::error::Error + Send + Sync>> {
        let doc = self.get_user_document(uid).await?;
        let empty = json!({});
        let fields = doc.get("fields").unwrap_or(&empty);

        Ok(DailySummarySettings {
            enabled: self.parse_bool(fields, "daily_summary_enabled").unwrap_or(true),
            hour: self.parse_int(fields, "daily_summary_hour_local").unwrap_or(22),
        })
    }

    /// Update daily summary settings for a user
    pub async fn update_daily_summary_settings(
        &self,
        uid: &str,
        enabled: Option<bool>,
        hour: Option<i32>,
    ) -> Result<DailySummarySettings, Box<dyn std::error::Error + Send + Sync>> {
        // Get current settings
        let current = self.get_daily_summary_settings(uid).await?;

        let new_enabled = enabled.unwrap_or(current.enabled);
        let new_hour = hour.unwrap_or(current.hour);

        let fields = json!({
            "daily_summary_enabled": {"booleanValue": new_enabled},
            "daily_summary_hour_local": {"integerValue": new_hour.to_string()}
        });

        self.update_user_fields(uid, fields, &["daily_summary_enabled", "daily_summary_hour_local"])
            .await?;

        Ok(DailySummarySettings {
            enabled: new_enabled,
            hour: new_hour,
        })
    }

    /// Get transcription preferences for a user
    pub async fn get_transcription_preferences(
        &self,
        uid: &str,
    ) -> Result<TranscriptionPreferences, Box<dyn std::error::Error + Send + Sync>> {
        let doc = self.get_user_document(uid).await?;
        let empty = json!({});
        let fields = doc.get("fields").unwrap_or(&empty);

        // Parse nested transcription_preferences object
        let prefs = fields
            .get("transcription_preferences")
            .and_then(|p| p.get("mapValue"))
            .and_then(|m| m.get("fields"));

        if let Some(pref_fields) = prefs {
            Ok(TranscriptionPreferences {
                single_language_mode: self.parse_bool(pref_fields, "single_language_mode").unwrap_or(false),
                vocabulary: self.parse_string_array(pref_fields, "vocabulary"),
            })
        } else {
            Ok(TranscriptionPreferences::default())
        }
    }

    /// Update transcription preferences for a user
    pub async fn update_transcription_preferences(
        &self,
        uid: &str,
        single_language_mode: Option<bool>,
        vocabulary: Option<Vec<String>>,
    ) -> Result<TranscriptionPreferences, Box<dyn std::error::Error + Send + Sync>> {
        // Get current settings
        let current = self.get_transcription_preferences(uid).await?;

        let new_single_language_mode = single_language_mode.unwrap_or(current.single_language_mode);
        let new_vocabulary = vocabulary.unwrap_or(current.vocabulary);

        let vocab_values: Vec<Value> = new_vocabulary
            .iter()
            .map(|v| json!({"stringValue": v}))
            .collect();

        let fields = json!({
            "transcription_preferences": {
                "mapValue": {
                    "fields": {
                        "single_language_mode": {"booleanValue": new_single_language_mode},
                        "vocabulary": {
                            "arrayValue": {
                                "values": vocab_values
                            }
                        }
                    }
                }
            }
        });

        self.update_user_fields(uid, fields, &["transcription_preferences"])
            .await?;

        Ok(TranscriptionPreferences {
            single_language_mode: new_single_language_mode,
            vocabulary: new_vocabulary,
        })
    }

    // MARK: - Assistant Settings

    /// Helper: parse a sub-map from Firestore fields
    fn parse_sub_map<'a>(&self, fields: &'a Value, key: &str) -> Option<&'a Value> {
        fields.get(key)?.get("mapValue")?.get("fields")
    }

    /// Helper: build a Firestore string array value
    fn build_string_array_value(&self, items: &[String]) -> Value {
        let values: Vec<Value> = items.iter().map(|v| json!({"stringValue": v})).collect();
        json!({"arrayValue": {"values": values}})
    }

    /// Helper: build a sub-map Firestore value from a serde_json::Map of fields
    fn build_sub_map_value(&self, map_fields: serde_json::Map<String, Value>) -> Value {
        json!({"mapValue": {"fields": map_fields}})
    }

    /// Get assistant settings from user document
    pub async fn get_assistant_settings(
        &self,
        uid: &str,
    ) -> Result<AssistantSettingsData, Box<dyn std::error::Error + Send + Sync>> {
        let doc = self.get_user_document(uid).await?;
        let empty = json!({});
        let fields = doc.get("fields").unwrap_or(&empty);

        let settings_fields = self.parse_sub_map(fields, "assistant_settings");

        let Some(sf) = settings_fields else {
            return Ok(AssistantSettingsData::default());
        };

        // Parse shared settings
        let shared = self.parse_sub_map(sf, "shared").map(|f| SharedAssistantSettingsData {
            cooldown_interval: self.parse_int(f, "cooldown_interval"),
            glow_overlay_enabled: self.parse_bool(f, "glow_overlay_enabled").ok(),
            analysis_delay: self.parse_int(f, "analysis_delay"),
            screen_analysis_enabled: self.parse_bool(f, "screen_analysis_enabled").ok(),
        });

        // Parse focus settings
        let focus = self.parse_sub_map(sf, "focus").map(|f| FocusSettingsData {
            enabled: self.parse_bool(f, "enabled").ok(),
            analysis_prompt: self.parse_string(f, "analysis_prompt"),
            cooldown_interval: self.parse_int(f, "cooldown_interval"),
            notifications_enabled: self.parse_bool(f, "notifications_enabled").ok(),
            excluded_apps: Some(self.parse_string_array(f, "excluded_apps")),
        });

        // Parse task settings
        let task = self.parse_sub_map(sf, "task").map(|f| TaskSettingsData {
            enabled: self.parse_bool(f, "enabled").ok(),
            analysis_prompt: self.parse_string(f, "analysis_prompt"),
            extraction_interval: self.parse_float(f, "extraction_interval"),
            min_confidence: self.parse_float(f, "min_confidence"),
            notifications_enabled: self.parse_bool(f, "notifications_enabled").ok(),
            allowed_apps: Some(self.parse_string_array(f, "allowed_apps")),
            browser_keywords: Some(self.parse_string_array(f, "browser_keywords")),
        });

        // Parse advice settings
        let advice = self.parse_sub_map(sf, "advice").map(|f| AdviceSettingsData {
            enabled: self.parse_bool(f, "enabled").ok(),
            analysis_prompt: self.parse_string(f, "analysis_prompt"),
            extraction_interval: self.parse_float(f, "extraction_interval"),
            min_confidence: self.parse_float(f, "min_confidence"),
            notifications_enabled: self.parse_bool(f, "notifications_enabled").ok(),
            excluded_apps: Some(self.parse_string_array(f, "excluded_apps")),
        });

        // Parse memory settings
        let memory = self.parse_sub_map(sf, "memory").map(|f| MemorySettingsData {
            enabled: self.parse_bool(f, "enabled").ok(),
            analysis_prompt: self.parse_string(f, "analysis_prompt"),
            extraction_interval: self.parse_float(f, "extraction_interval"),
            min_confidence: self.parse_float(f, "min_confidence"),
            notifications_enabled: self.parse_bool(f, "notifications_enabled").ok(),
            excluded_apps: Some(self.parse_string_array(f, "excluded_apps")),
        });

        Ok(AssistantSettingsData {
            shared,
            focus,
            task,
            advice,
            memory,
        })
    }

    /// Update assistant settings (merge with existing)
    pub async fn update_assistant_settings(
        &self,
        uid: &str,
        data: &AssistantSettingsData,
    ) -> Result<AssistantSettingsData, Box<dyn std::error::Error + Send + Sync>> {
        let current = self.get_assistant_settings(uid).await?;

        let mut top_fields = serde_json::Map::new();

        // Build shared sub-map
        if data.shared.is_some() || current.shared.is_some() {
            let cur = current.shared.unwrap_or_default();
            let new = data.shared.clone().unwrap_or_default();
            let mut m = serde_json::Map::new();
            let ci = new.cooldown_interval.or(cur.cooldown_interval);
            if let Some(v) = ci { m.insert("cooldown_interval".into(), json!({"integerValue": v.to_string()})); }
            let go = new.glow_overlay_enabled.or(cur.glow_overlay_enabled);
            if let Some(v) = go { m.insert("glow_overlay_enabled".into(), json!({"booleanValue": v})); }
            let ad = new.analysis_delay.or(cur.analysis_delay);
            if let Some(v) = ad { m.insert("analysis_delay".into(), json!({"integerValue": v.to_string()})); }
            let sa = new.screen_analysis_enabled.or(cur.screen_analysis_enabled);
            if let Some(v) = sa { m.insert("screen_analysis_enabled".into(), json!({"booleanValue": v})); }
            if !m.is_empty() {
                top_fields.insert("shared".into(), self.build_sub_map_value(m));
            }
        }

        // Build focus sub-map
        if data.focus.is_some() || current.focus.is_some() {
            let cur = current.focus.unwrap_or_default();
            let new = data.focus.clone().unwrap_or_default();
            let mut m = serde_json::Map::new();
            let en = new.enabled.or(cur.enabled);
            if let Some(v) = en { m.insert("enabled".into(), json!({"booleanValue": v})); }
            let ap = new.analysis_prompt.or(cur.analysis_prompt);
            if let Some(v) = ap { m.insert("analysis_prompt".into(), json!({"stringValue": v})); }
            let ci = new.cooldown_interval.or(cur.cooldown_interval);
            if let Some(v) = ci { m.insert("cooldown_interval".into(), json!({"integerValue": v.to_string()})); }
            let ne = new.notifications_enabled.or(cur.notifications_enabled);
            if let Some(v) = ne { m.insert("notifications_enabled".into(), json!({"booleanValue": v})); }
            let ea = new.excluded_apps.or(cur.excluded_apps);
            if let Some(v) = ea { m.insert("excluded_apps".into(), self.build_string_array_value(&v)); }
            if !m.is_empty() {
                top_fields.insert("focus".into(), self.build_sub_map_value(m));
            }
        }

        // Build task sub-map
        if data.task.is_some() || current.task.is_some() {
            let cur = current.task.unwrap_or_default();
            let new = data.task.clone().unwrap_or_default();
            let mut m = serde_json::Map::new();
            let en = new.enabled.or(cur.enabled);
            if let Some(v) = en { m.insert("enabled".into(), json!({"booleanValue": v})); }
            let ap = new.analysis_prompt.or(cur.analysis_prompt);
            if let Some(v) = ap { m.insert("analysis_prompt".into(), json!({"stringValue": v})); }
            let ei = new.extraction_interval.or(cur.extraction_interval);
            if let Some(v) = ei { m.insert("extraction_interval".into(), json!({"doubleValue": v})); }
            let mc = new.min_confidence.or(cur.min_confidence);
            if let Some(v) = mc { m.insert("min_confidence".into(), json!({"doubleValue": v})); }
            let aa = new.allowed_apps.or(cur.allowed_apps);
            if let Some(v) = aa { m.insert("allowed_apps".into(), self.build_string_array_value(&v)); }
            let ne = new.notifications_enabled.or(cur.notifications_enabled);
            if let Some(v) = ne { m.insert("notifications_enabled".into(), json!({"booleanValue": v})); }
            let bk = new.browser_keywords.or(cur.browser_keywords);
            if let Some(v) = bk { m.insert("browser_keywords".into(), self.build_string_array_value(&v)); }
            if !m.is_empty() {
                top_fields.insert("task".into(), self.build_sub_map_value(m));
            }
        }

        // Build advice sub-map
        if data.advice.is_some() || current.advice.is_some() {
            let cur = current.advice.unwrap_or_default();
            let new = data.advice.clone().unwrap_or_default();
            let mut m = serde_json::Map::new();
            let en = new.enabled.or(cur.enabled);
            if let Some(v) = en { m.insert("enabled".into(), json!({"booleanValue": v})); }
            let ap = new.analysis_prompt.or(cur.analysis_prompt);
            if let Some(v) = ap { m.insert("analysis_prompt".into(), json!({"stringValue": v})); }
            let ei = new.extraction_interval.or(cur.extraction_interval);
            if let Some(v) = ei { m.insert("extraction_interval".into(), json!({"doubleValue": v})); }
            let mc = new.min_confidence.or(cur.min_confidence);
            if let Some(v) = mc { m.insert("min_confidence".into(), json!({"doubleValue": v})); }
            let ne = new.notifications_enabled.or(cur.notifications_enabled);
            if let Some(v) = ne { m.insert("notifications_enabled".into(), json!({"booleanValue": v})); }
            let ea = new.excluded_apps.or(cur.excluded_apps);
            if let Some(v) = ea { m.insert("excluded_apps".into(), self.build_string_array_value(&v)); }
            if !m.is_empty() {
                top_fields.insert("advice".into(), self.build_sub_map_value(m));
            }
        }

        // Build memory sub-map
        if data.memory.is_some() || current.memory.is_some() {
            let cur = current.memory.unwrap_or_default();
            let new = data.memory.clone().unwrap_or_default();
            let mut m = serde_json::Map::new();
            let en = new.enabled.or(cur.enabled);
            if let Some(v) = en { m.insert("enabled".into(), json!({"booleanValue": v})); }
            let ap = new.analysis_prompt.or(cur.analysis_prompt);
            if let Some(v) = ap { m.insert("analysis_prompt".into(), json!({"stringValue": v})); }
            let ei = new.extraction_interval.or(cur.extraction_interval);
            if let Some(v) = ei { m.insert("extraction_interval".into(), json!({"doubleValue": v})); }
            let mc = new.min_confidence.or(cur.min_confidence);
            if let Some(v) = mc { m.insert("min_confidence".into(), json!({"doubleValue": v})); }
            let ne = new.notifications_enabled.or(cur.notifications_enabled);
            if let Some(v) = ne { m.insert("notifications_enabled".into(), json!({"booleanValue": v})); }
            let ea = new.excluded_apps.or(cur.excluded_apps);
            if let Some(v) = ea { m.insert("excluded_apps".into(), self.build_string_array_value(&v)); }
            if !m.is_empty() {
                top_fields.insert("memory".into(), self.build_sub_map_value(m));
            }
        }

        if !top_fields.is_empty() {
            let fields = json!({
                "assistant_settings": {
                    "mapValue": {
                        "fields": Value::Object(top_fields)
                    }
                }
            });

            self.update_user_fields(uid, fields, &["assistant_settings"]).await?;
        }

        // Return merged state
        self.get_assistant_settings(uid).await
    }

    /// Get user email from Firestore profile
    pub async fn get_user_email(
        &self,
        uid: &str,
    ) -> Result<Option<String>, Box<dyn std::error::Error + Send + Sync>> {
        let doc = self.get_user_document(uid).await?;
        let empty = json!({});
        let fields = doc.get("fields").unwrap_or(&empty);
        Ok(self.parse_string(fields, "email"))
    }

    /// Get user language preference
    pub async fn get_user_language(
        &self,
        uid: &str,
    ) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
        let doc = self.get_user_document(uid).await?;
        let empty = json!({});
        let fields = doc.get("fields").unwrap_or(&empty);

        Ok(self.parse_string(fields, "language").unwrap_or_else(|| "en".to_string()))
    }

    /// Update user language preference
    pub async fn update_user_language(
        &self,
        uid: &str,
        language: &str,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let fields = json!({
            "language": {"stringValue": language}
        });

        self.update_user_fields(uid, fields, &["language"]).await
    }

    /// Get recording permission for a user
    pub async fn get_recording_permission(
        &self,
        uid: &str,
    ) -> Result<bool, Box<dyn std::error::Error + Send + Sync>> {
        let doc = self.get_user_document(uid).await?;
        let empty = json!({});
        let fields = doc.get("fields").unwrap_or(&empty);

        Ok(self.parse_bool(fields, "store_recording_permission").unwrap_or(false))
    }

    /// Set recording permission for a user
    pub async fn set_recording_permission(
        &self,
        uid: &str,
        enabled: bool,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let fields = json!({
            "store_recording_permission": {"booleanValue": enabled}
        });

        self.update_user_fields(uid, fields, &["store_recording_permission"]).await
    }

    /// Get private cloud sync setting for a user
    pub async fn get_private_cloud_sync(
        &self,
        uid: &str,
    ) -> Result<bool, Box<dyn std::error::Error + Send + Sync>> {
        let doc = self.get_user_document(uid).await?;
        let empty = json!({});
        let fields = doc.get("fields").unwrap_or(&empty);

        // Default to true if not set
        Ok(self.parse_bool(fields, "private_cloud_sync_enabled").unwrap_or(true))
    }

    /// Set private cloud sync setting for a user
    pub async fn set_private_cloud_sync(
        &self,
        uid: &str,
        enabled: bool,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let fields = json!({
            "private_cloud_sync_enabled": {"booleanValue": enabled}
        });

        self.update_user_fields(uid, fields, &["private_cloud_sync_enabled"]).await
    }

    /// Get notification settings for a user
    pub async fn get_notification_settings(
        &self,
        uid: &str,
    ) -> Result<NotificationSettings, Box<dyn std::error::Error + Send + Sync>> {
        let doc = self.get_user_document(uid).await?;
        let empty = json!({});
        let fields = doc.get("fields").unwrap_or(&empty);

        Ok(NotificationSettings {
            enabled: self.parse_bool(fields, "notifications_enabled").unwrap_or(true),
            frequency: self.parse_int(fields, "notification_frequency").unwrap_or(3),
        })
    }

    /// Update notification settings for a user
    pub async fn update_notification_settings(
        &self,
        uid: &str,
        enabled: Option<bool>,
        frequency: Option<i32>,
    ) -> Result<NotificationSettings, Box<dyn std::error::Error + Send + Sync>> {
        // Get current settings
        let current = self.get_notification_settings(uid).await?;

        let new_enabled = enabled.unwrap_or(current.enabled);
        let new_frequency = frequency.unwrap_or(current.frequency);

        let fields = json!({
            "notifications_enabled": {"booleanValue": new_enabled},
            "notification_frequency": {"integerValue": new_frequency.to_string()}
        });

        self.update_user_fields(uid, fields, &["notifications_enabled", "notification_frequency"])
            .await?;

        Ok(NotificationSettings {
            enabled: new_enabled,
            frequency: new_frequency,
        })
    }

    /// Get user profile
    pub async fn get_user_profile(
        &self,
        uid: &str,
    ) -> Result<UserProfile, Box<dyn std::error::Error + Send + Sync>> {
        let doc = self.get_user_document(uid).await?;
        let empty = json!({});
        let fields = doc.get("fields").unwrap_or(&empty);

        Ok(UserProfile {
            uid: uid.to_string(),
            email: self.parse_string(fields, "email"),
            name: self.parse_string(fields, "name"),
            time_zone: self.parse_string(fields, "time_zone"),
            created_at: self.parse_timestamp_optional(fields, "created_at")
                .map(|dt| dt.to_rfc3339()),
            motivation: self.parse_string(fields, "motivation"),
            use_case: self.parse_string(fields, "use_case"),
            job: self.parse_string(fields, "job"),
            company: self.parse_string(fields, "company"),
        })
    }

    /// Update user profile fields (onboarding data)
    pub async fn update_user_profile(
        &self,
        uid: &str,
        name: Option<String>,
        motivation: Option<String>,
        use_case: Option<String>,
        job: Option<String>,
        company: Option<String>,
    ) -> Result<UserProfile, Box<dyn std::error::Error + Send + Sync>> {
        let mut fields = json!({});
        let mut mask: Vec<&str> = Vec::new();

        if let Some(ref v) = name {
            fields["name"] = json!({"stringValue": v});
            mask.push("name");
        }
        if let Some(ref v) = motivation {
            fields["motivation"] = json!({"stringValue": v});
            mask.push("motivation");
        }
        if let Some(ref v) = use_case {
            fields["use_case"] = json!({"stringValue": v});
            mask.push("use_case");
        }
        if let Some(ref v) = job {
            fields["job"] = json!({"stringValue": v});
            mask.push("job");
        }
        if let Some(ref v) = company {
            fields["company"] = json!({"stringValue": v});
            mask.push("company");
        }

        if !mask.is_empty() {
            self.update_user_fields(uid, fields, &mask).await?;
        }

        self.get_user_profile(uid).await
    }

    // =========================================================================
    // USER PERSONA
    // =========================================================================

    /// Get AI-generated user profile from user document
    pub async fn get_ai_user_profile(
        &self,
        uid: &str,
    ) -> Result<Option<AIUserProfile>, Box<dyn std::error::Error + Send + Sync>> {
        let doc = self.get_user_document(uid).await?;
        let empty = json!({});
        let fields = doc.get("fields").unwrap_or(&empty);

        let profile_fields = fields
            .get("ai_user_profile")
            .and_then(|p| p.get("mapValue"))
            .and_then(|m| m.get("fields"));

        if let Some(pf) = profile_fields {
            let profile_text = self.parse_string(pf, "profile_text").unwrap_or_default();
            let generated_at = self.parse_timestamp(pf, "generated_at")?;
            let data_sources_used = self.parse_int(pf, "data_sources_used").unwrap_or(0);

            Ok(Some(AIUserProfile {
                profile_text,
                generated_at,
                data_sources_used,
            }))
        } else {
            Ok(None)
        }
    }

    /// Update AI-generated user profile in user document
    pub async fn update_ai_user_profile(
        &self,
        uid: &str,
        profile_text: &str,
        generated_at: &str,
        data_sources_used: i32,
    ) -> Result<AIUserProfile, Box<dyn std::error::Error + Send + Sync>> {
        let generated_at_dt = DateTime::parse_from_rfc3339(generated_at)
            .map(|dt| dt.with_timezone(&Utc))
            .map_err(|e| format!("Invalid generated_at timestamp: {}", e))?;

        let fields = json!({
            "ai_user_profile": {
                "mapValue": {
                    "fields": {
                        "profile_text": {"stringValue": profile_text},
                        "generated_at": {"timestampValue": generated_at},
                        "data_sources_used": {"integerValue": data_sources_used.to_string()}
                    }
                }
            }
        });

        self.update_user_fields(uid, fields, &["ai_user_profile"]).await?;

        Ok(AIUserProfile {
            profile_text: profile_text.to_string(),
            generated_at: generated_at_dt,
            data_sources_used,
        })
    }

    // =========================================================================
    // FOCUS SESSIONS
    // =========================================================================

    /// Create a focus session
    /// Path: users/{uid}/focus_sessions/{session_id}
    pub async fn create_focus_session(
        &self,
        uid: &str,
        status: &FocusStatus,
        app_or_site: &str,
        description: &str,
        message: Option<&str>,
    ) -> Result<FocusSessionDB, Box<dyn std::error::Error + Send + Sync>> {
        let session_id = uuid::Uuid::new_v4().to_string();
        let now = Utc::now();

        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            FOCUS_SESSIONS_SUBCOLLECTION,
            session_id
        );

        let status_str = match status {
            FocusStatus::Focused => "focused",
            FocusStatus::Distracted => "distracted",
        };

        let mut fields = json!({
            "status": {"stringValue": status_str},
            "app_or_site": {"stringValue": app_or_site},
            "description": {"stringValue": description},
            "created_at": {"timestampValue": now.to_rfc3339()}
        });

        if let Some(msg) = message {
            fields["message"] = json!({"stringValue": msg});
        }

        let doc = json!({"fields": fields});

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore create error: {}", error_text).into());
        }

        tracing::info!(
            "Created focus session {} for user {} with status={}",
            session_id,
            uid,
            status_str
        );

        Ok(FocusSessionDB {
            id: session_id,
            status: status.clone(),
            app_or_site: app_or_site.to_string(),
            description: description.to_string(),
            message: message.map(|s| s.to_string()),
            created_at: now,
            duration_seconds: None,
        })
    }

    /// Get focus sessions for a user
    /// Path: users/{uid}/focus_sessions
    pub async fn get_focus_sessions(
        &self,
        uid: &str,
        limit: usize,
        offset: usize,
        date_filter: Option<&str>,
    ) -> Result<Vec<FocusSessionDB>, Box<dyn std::error::Error + Send + Sync>> {
        let parent = format!("{}/{}/{}", self.base_url(), USERS_COLLECTION, uid);

        // Build filters
        let mut filters: Vec<Value> = Vec::new();

        // If date filter provided, filter by date range
        if let Some(date) = date_filter {
            // Parse date and create start/end timestamps
            if let Ok(parsed_date) = chrono::NaiveDate::parse_from_str(date, "%Y-%m-%d") {
                let start = parsed_date
                    .and_hms_opt(0, 0, 0)
                    .unwrap()
                    .and_utc();
                let end = parsed_date
                    .and_hms_opt(23, 59, 59)
                    .unwrap()
                    .and_utc();

                filters.push(json!({
                    "fieldFilter": {
                        "field": {"fieldPath": "created_at"},
                        "op": "GREATER_THAN_OR_EQUAL",
                        "value": {"timestampValue": start.to_rfc3339()}
                    }
                }));
                filters.push(json!({
                    "fieldFilter": {
                        "field": {"fieldPath": "created_at"},
                        "op": "LESS_THAN_OR_EQUAL",
                        "value": {"timestampValue": end.to_rfc3339()}
                    }
                }));
            }
        }

        // Build the where clause
        let where_clause = if filters.is_empty() {
            None
        } else if filters.len() == 1 {
            Some(filters.into_iter().next().unwrap())
        } else {
            Some(json!({
                "compositeFilter": {
                    "op": "AND",
                    "filters": filters
                }
            }))
        };

        // Build structured query
        let mut structured_query = json!({
            "from": [{"collectionId": FOCUS_SESSIONS_SUBCOLLECTION}],
            "orderBy": [{"field": {"fieldPath": "created_at"}, "direction": "DESCENDING"}],
            "limit": limit,
            "offset": offset
        });

        if let Some(where_filter) = where_clause {
            structured_query["where"] = where_filter;
        }

        let query = json!({
            "structuredQuery": structured_query
        });

        let response = self
            .build_request(reqwest::Method::POST, &format!("{}:runQuery", parent))
            .await?
            .json(&query)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            tracing::error!("Firestore query error: {}", error_text);
            return Ok(vec![]);
        }

        let results: Vec<Value> = response.json().await?;
        let sessions = results
            .into_iter()
            .filter_map(|doc| {
                doc.get("document")
                    .and_then(|d| self.parse_focus_session(d).ok())
            })
            .collect();

        Ok(sessions)
    }

    /// Delete a focus session
    pub async fn delete_focus_session(
        &self,
        uid: &str,
        session_id: &str,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            FOCUS_SESSIONS_SUBCOLLECTION,
            session_id
        );

        let response = self
            .build_request(reqwest::Method::DELETE, &url)
            .await?
            .send()
            .await?;

        if !response.status().is_success() && response.status() != reqwest::StatusCode::NOT_FOUND {
            let error_text = response.text().await?;
            return Err(format!("Firestore delete error: {}", error_text).into());
        }

        tracing::info!("Deleted focus session {} for user {}", session_id, uid);
        Ok(())
    }

    /// Get focus statistics for a date
    pub async fn get_focus_stats(
        &self,
        uid: &str,
        date: &str,
    ) -> Result<FocusStats, Box<dyn std::error::Error + Send + Sync>> {
        // Get all sessions for the date
        let sessions = self.get_focus_sessions(uid, 1000, 0, Some(date)).await?;

        let mut focused_count: i64 = 0;
        let mut distracted_count: i64 = 0;
        let mut distraction_map: std::collections::HashMap<String, (i64, i64)> =
            std::collections::HashMap::new();

        for session in &sessions {
            match session.status {
                FocusStatus::Focused => focused_count += 1,
                FocusStatus::Distracted => {
                    distracted_count += 1;
                    let entry = distraction_map
                        .entry(session.app_or_site.clone())
                        .or_insert((0, 0));
                    entry.0 += session.duration_seconds.unwrap_or(60); // Default 60s per session
                    entry.1 += 1;
                }
            }
        }

        // Build top distractions
        let mut top_distractions: Vec<DistractionEntry> = distraction_map
            .into_iter()
            .map(|(app, (secs, count))| DistractionEntry {
                app_or_site: app,
                total_seconds: secs,
                count,
            })
            .collect();

        // Sort by total time descending
        top_distractions.sort_by(|a, b| b.total_seconds.cmp(&a.total_seconds));

        // Take top 5
        top_distractions.truncate(5);

        // Estimate minutes (each session ~1 minute if no duration)
        let focused_minutes = focused_count;
        let distracted_minutes = distracted_count;

        Ok(FocusStats {
            date: date.to_string(),
            focused_minutes,
            distracted_minutes,
            session_count: sessions.len() as i64,
            focused_count,
            distracted_count,
            top_distractions,
        })
    }

    /// Parse a focus session from Firestore document
    fn parse_focus_session(
        &self,
        doc: &Value,
    ) -> Result<FocusSessionDB, Box<dyn std::error::Error + Send + Sync>> {
        let name = doc
            .get("name")
            .and_then(|n| n.as_str())
            .ok_or("Missing document name")?;

        let id = name.split('/').last().unwrap_or("unknown").to_string();

        let fields = doc.get("fields").ok_or("Missing fields")?;

        let status_str = self.parse_string(fields, "status").unwrap_or_default();
        let status = match status_str.as_str() {
            "focused" => FocusStatus::Focused,
            _ => FocusStatus::Distracted,
        };

        Ok(FocusSessionDB {
            id,
            status,
            app_or_site: self.parse_string(fields, "app_or_site").unwrap_or_default(),
            description: self.parse_string(fields, "description").unwrap_or_default(),
            message: self.parse_string(fields, "message"),
            created_at: self
                .parse_timestamp_optional(fields, "created_at")
                .unwrap_or_else(Utc::now),
            duration_seconds: self.parse_int(fields, "duration_seconds").map(|v| v as i64),
        })
    }

    // =========================================================================
    // CHAT SESSIONS
    // =========================================================================

    /// Create a chat session
    /// Path: users/{uid}/chat_sessions/{session_id}
    pub async fn create_chat_session(
        &self,
        uid: &str,
        title: Option<&str>,
        app_id: Option<&str>,
    ) -> Result<ChatSessionDB, Box<dyn std::error::Error + Send + Sync>> {
        let session_id = uuid::Uuid::new_v4().to_string();
        let now = Utc::now();

        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            CHAT_SESSIONS_SUBCOLLECTION,
            session_id
        );

        let mut fields = json!({
            // CRITICAL: id field required - Python ChatSession model requires it
            // and chat.py accesses chat_session['id'] directly
            "id": {"stringValue": &session_id},
            "title": {"stringValue": title.unwrap_or("New Chat")},
            "created_at": {"timestampValue": now.to_rfc3339()},
            "updated_at": {"timestampValue": now.to_rfc3339()},
            "message_count": {"integerValue": "0"},
            "starred": {"booleanValue": false}
        });

        // CRITICAL: Always set app_id and plugin_id fields for backward compatibility
        // Python backend queries chat_sessions.where(plugin_id == null) for main chat
        if let Some(app) = app_id {
            fields["app_id"] = json!({"stringValue": app});
            fields["plugin_id"] = json!({"stringValue": app});
        } else {
            // For main chat (no app), explicitly set null values
            fields["app_id"] = json!({"nullValue": null});
            fields["plugin_id"] = json!({"nullValue": null});
        }

        let doc = json!({"fields": fields});

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore create error: {}", error_text).into());
        }

        tracing::info!(
            "Created chat session {} for user {} with title={}",
            session_id,
            uid,
            title.unwrap_or("New Chat")
        );

        Ok(ChatSessionDB {
            id: session_id,
            title: title.unwrap_or("New Chat").to_string(),
            preview: None,
            created_at: now,
            updated_at: now,
            app_id: app_id.map(|s| s.to_string()),
            message_count: 0,
            starred: false,
        })
    }

    /// Get chat sessions for a user
    /// Path: users/{uid}/chat_sessions
    pub async fn get_chat_sessions(
        &self,
        uid: &str,
        app_id: Option<&str>,
        limit: usize,
        offset: usize,
        starred: Option<bool>,
    ) -> Result<Vec<ChatSessionDB>, Box<dyn std::error::Error + Send + Sync>> {
        let parent = format!("{}/{}/{}", self.base_url(), USERS_COLLECTION, uid);

        // Build filters
        let mut filters: Vec<Value> = Vec::new();

        // Filter by app_id (null = main Omi chat)
        if let Some(app) = app_id {
            filters.push(json!({
                "fieldFilter": {
                    "field": {"fieldPath": "app_id"},
                    "op": "EQUAL",
                    "value": {"stringValue": app}
                }
            }));
        }

        // Filter by starred if specified
        if let Some(is_starred) = starred {
            filters.push(json!({
                "fieldFilter": {
                    "field": {"fieldPath": "starred"},
                    "op": "EQUAL",
                    "value": {"booleanValue": is_starred}
                }
            }));
        }

        // Build the where clause
        let where_clause = if filters.is_empty() {
            None
        } else if filters.len() == 1 {
            Some(filters.into_iter().next().unwrap())
        } else {
            Some(json!({
                "compositeFilter": {
                    "op": "AND",
                    "filters": filters
                }
            }))
        };

        // Build structured query
        // NOTE: Use created_at for ordering (not updated_at) for backward compatibility
        // Old sessions from Flutter app don't have updated_at field
        let mut structured_query = json!({
            "from": [{"collectionId": CHAT_SESSIONS_SUBCOLLECTION}],
            "orderBy": [{"field": {"fieldPath": "created_at"}, "direction": "DESCENDING"}],
            "limit": limit,
            "offset": offset
        });

        if let Some(where_filter) = where_clause {
            structured_query["where"] = where_filter;
        }

        let query = json!({
            "structuredQuery": structured_query
        });

        let response = self
            .build_request(reqwest::Method::POST, &format!("{}:runQuery", parent))
            .await?
            .json(&query)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            tracing::error!("Firestore query error: {}", error_text);
            return Ok(vec![]);
        }

        let results: Vec<Value> = response.json().await?;
        let sessions = results
            .into_iter()
            .filter_map(|doc| {
                doc.get("document")
                    .and_then(|d| self.parse_chat_session(d).ok())
            })
            .collect();

        Ok(sessions)
    }

    /// Get a single chat session
    /// Path: users/{uid}/chat_sessions/{session_id}
    pub async fn get_chat_session(
        &self,
        uid: &str,
        session_id: &str,
    ) -> Result<Option<ChatSessionDB>, Box<dyn std::error::Error + Send + Sync>> {
        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            CHAT_SESSIONS_SUBCOLLECTION,
            session_id
        );

        let response = self
            .build_request(reqwest::Method::GET, &url)
            .await?
            .send()
            .await?;

        if response.status() == reqwest::StatusCode::NOT_FOUND {
            return Ok(None);
        }

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore get error: {}", error_text).into());
        }

        let doc: Value = response.json().await?;
        Ok(Some(self.parse_chat_session(&doc)?))
    }

    /// Update a chat session (title, starred, preview, message_count)
    /// Path: users/{uid}/chat_sessions/{session_id}
    pub async fn update_chat_session(
        &self,
        uid: &str,
        session_id: &str,
        title: Option<&str>,
        starred: Option<bool>,
    ) -> Result<ChatSessionDB, Box<dyn std::error::Error + Send + Sync>> {
        // First get the existing session
        let existing = self.get_chat_session(uid, session_id).await?
            .ok_or_else(|| format!("Chat session {} not found", session_id))?;

        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            CHAT_SESSIONS_SUBCOLLECTION,
            session_id
        );

        let now = Utc::now();
        let mut fields = json!({
            "title": {"stringValue": title.unwrap_or(&existing.title)},
            "starred": {"booleanValue": starred.unwrap_or(existing.starred)},
            "updated_at": {"timestampValue": now.to_rfc3339()},
            "created_at": {"timestampValue": existing.created_at.to_rfc3339()},
            "message_count": {"integerValue": existing.message_count.to_string()}
        });

        if let Some(preview) = &existing.preview {
            fields["preview"] = json!({"stringValue": preview});
        }
        if let Some(app) = &existing.app_id {
            fields["app_id"] = json!({"stringValue": app});
        }

        let doc = json!({"fields": fields});

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore update error: {}", error_text).into());
        }

        tracing::info!(
            "Updated chat session {} for user {}",
            session_id,
            uid
        );

        Ok(ChatSessionDB {
            id: session_id.to_string(),
            title: title.unwrap_or(&existing.title).to_string(),
            preview: existing.preview,
            created_at: existing.created_at,
            updated_at: now,
            app_id: existing.app_id,
            message_count: existing.message_count,
            starred: starred.unwrap_or(existing.starred),
        })
    }

    /// Update chat session preview and message count (called when new message is added)
    pub async fn update_chat_session_with_message(
        &self,
        uid: &str,
        session_id: &str,
        preview: &str,
        title: Option<&str>,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        // First get the existing session
        let existing = match self.get_chat_session(uid, session_id).await? {
            Some(s) => s,
            None => return Ok(()), // Session doesn't exist, skip update
        };

        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            CHAT_SESSIONS_SUBCOLLECTION,
            session_id
        );

        let now = Utc::now();
        let new_count = existing.message_count + 1;

        // Use provided title or keep existing (title is auto-generated from first message)
        let final_title = title.unwrap_or(&existing.title);

        let mut fields = json!({
            "title": {"stringValue": final_title},
            "preview": {"stringValue": preview.chars().take(100).collect::<String>()},
            "updated_at": {"timestampValue": now.to_rfc3339()},
            "created_at": {"timestampValue": existing.created_at.to_rfc3339()},
            "message_count": {"integerValue": new_count.to_string()},
            "starred": {"booleanValue": existing.starred}
        });

        if let Some(app) = &existing.app_id {
            fields["app_id"] = json!({"stringValue": app});
        }

        let doc = json!({"fields": fields});

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            tracing::warn!("Failed to update chat session with message: {}", error_text);
        }

        Ok(())
    }

    /// Delete a chat session and its associated messages
    /// Path: users/{uid}/chat_sessions/{session_id}
    pub async fn delete_chat_session(
        &self,
        uid: &str,
        session_id: &str,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        // First, delete all messages with this session_id
        if let Err(e) = self.delete_messages_by_session(uid, session_id).await {
            tracing::warn!("Failed to delete messages for session {}: {}", session_id, e);
            // Continue with session deletion
        }

        // Delete the session document
        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            CHAT_SESSIONS_SUBCOLLECTION,
            session_id
        );

        let response = self
            .build_request(reqwest::Method::DELETE, &url)
            .await?
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore delete error: {}", error_text).into());
        }

        tracing::info!("Deleted chat session {} for user {}", session_id, uid);
        Ok(())
    }

    /// Delete all messages with a specific session_id
    async fn delete_messages_by_session(
        &self,
        uid: &str,
        session_id: &str,
    ) -> Result<usize, Box<dyn std::error::Error + Send + Sync>> {
        let parent = format!("{}/{}/{}", self.base_url(), USERS_COLLECTION, uid);

        // Query messages with this session_id
        let structured_query = json!({
            "from": [{"collectionId": MESSAGES_SUBCOLLECTION}],
            "where": {
                "fieldFilter": {
                    "field": {"fieldPath": "session_id"},
                    "op": "EQUAL",
                    "value": {"stringValue": session_id}
                }
            },
            "limit": 500  // Batch delete limit
        });

        let query = json!({
            "structuredQuery": structured_query
        });

        let response = self
            .build_request(reqwest::Method::POST, &format!("{}:runQuery", parent))
            .await?
            .json(&query)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Failed to query messages: {}", error_text).into());
        }

        let results: Vec<Value> = response.json().await?;
        let mut deleted_count = 0;

        // Delete each message
        for result in results {
            if let Some(doc) = result.get("document") {
                if let Some(name) = doc.get("name").and_then(|n| n.as_str()) {
                    // Extract the full document path for deletion
                    let delete_url = format!(
                        "https://firestore.googleapis.com/v1/{}",
                        name
                    );

                    let delete_response = self
                        .build_request(reqwest::Method::DELETE, &delete_url)
                        .await?
                        .send()
                        .await?;

                    if delete_response.status().is_success() {
                        deleted_count += 1;
                    }
                }
            }
        }

        tracing::info!(
            "Deleted {} messages for session {} (user {})",
            deleted_count,
            session_id,
            uid
        );

        Ok(deleted_count)
    }

    /// Parse a chat session from Firestore document
    /// Supports both old (Flutter) and new (Desktop) session formats for backward compatibility
    fn parse_chat_session(
        &self,
        doc: &Value,
    ) -> Result<ChatSessionDB, Box<dyn std::error::Error + Send + Sync>> {
        let name = doc
            .get("name")
            .and_then(|n| n.as_str())
            .ok_or("Missing document name")?;

        let id = name.split('/').last().unwrap_or("unknown").to_string();

        let fields = doc.get("fields").ok_or("Missing fields")?;

        let created_at = self
            .parse_timestamp_optional(fields, "created_at")
            .unwrap_or_else(Utc::now);

        // For message_count: prefer explicit field, fallback to message_ids array length (old format)
        let message_count = self.parse_int(fields, "message_count").unwrap_or_else(|| {
            // Old Flutter sessions store message IDs in an array
            fields
                .get("message_ids")
                .and_then(|v| v.get("arrayValue"))
                .and_then(|a| a.get("values"))
                .and_then(|v| v.as_array())
                .map(|arr| arr.len() as i32)
                .unwrap_or(0)
        });

        // For app_id: fallback to plugin_id (old Flutter format)
        let app_id = self
            .parse_string(fields, "app_id")
            .or_else(|| self.parse_string(fields, "plugin_id"));

        // For title: use explicit title, or "Omi" for main chat (app_id=null), or "New Chat"
        // This helps users recognize their main Omi chat from old Flutter sessions
        let title = self.parse_string(fields, "title").unwrap_or_else(|| {
            if app_id.is_none() {
                "Omi".to_string()
            } else {
                "New Chat".to_string()
            }
        });

        Ok(ChatSessionDB {
            id,
            title,
            preview: self.parse_string(fields, "preview"),
            created_at,
            // For updated_at: fallback to created_at (old sessions don't have updated_at)
            updated_at: self
                .parse_timestamp_optional(fields, "updated_at")
                .unwrap_or(created_at),
            app_id,
            message_count,
            starred: self.parse_bool(fields, "starred").unwrap_or(false),
        })
    }

    // =========================================================================
    // ADVICE
    // =========================================================================

    /// Create a new advice entry
    /// Path: users/{uid}/advice/{advice_id}
    pub async fn create_advice(
        &self,
        uid: &str,
        content: &str,
        category: Option<AdviceCategory>,
        reasoning: Option<&str>,
        source_app: Option<&str>,
        confidence: Option<f64>,
        context_summary: Option<&str>,
        current_activity: Option<&str>,
    ) -> Result<AdviceDB, Box<dyn std::error::Error + Send + Sync>> {
        let advice_id = uuid::Uuid::new_v4().to_string();
        let now = Utc::now();

        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            ADVICE_SUBCOLLECTION,
            advice_id
        );

        let category_str = match category.unwrap_or(AdviceCategory::Other) {
            AdviceCategory::Productivity => "productivity",
            AdviceCategory::Health => "health",
            AdviceCategory::Communication => "communication",
            AdviceCategory::Learning => "learning",
            AdviceCategory::Other => "other",
        };

        let mut fields = json!({
            "content": {"stringValue": content},
            "category": {"stringValue": category_str},
            "confidence": {"doubleValue": confidence.unwrap_or(0.5)},
            "is_read": {"booleanValue": false},
            "is_dismissed": {"booleanValue": false},
            "created_at": {"timestampValue": now.to_rfc3339()}
        });

        if let Some(r) = reasoning {
            fields["reasoning"] = json!({"stringValue": r});
        }
        if let Some(app) = source_app {
            fields["source_app"] = json!({"stringValue": app});
        }
        if let Some(summary) = context_summary {
            fields["context_summary"] = json!({"stringValue": summary});
        }
        if let Some(activity) = current_activity {
            fields["current_activity"] = json!({"stringValue": activity});
        }

        let doc = json!({"fields": fields});

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore create error: {}", error_text).into());
        }

        let created_doc: Value = response.json().await?;
        let advice = self.parse_advice(&created_doc)?;

        tracing::info!("Created advice {} for user {}", advice_id, uid);
        Ok(advice)
    }

    /// Get advice for a user
    /// Path: users/{uid}/advice
    pub async fn get_advice(
        &self,
        uid: &str,
        limit: usize,
        offset: usize,
        category: Option<&str>,
        include_dismissed: bool,
    ) -> Result<Vec<AdviceDB>, Box<dyn std::error::Error + Send + Sync>> {
        let parent = format!("{}/{}/{}", self.base_url(), USERS_COLLECTION, uid);

        // Build filters
        let mut filters: Vec<Value> = Vec::new();

        // Filter out dismissed unless requested
        if !include_dismissed {
            filters.push(json!({
                "fieldFilter": {
                    "field": {"fieldPath": "is_dismissed"},
                    "op": "EQUAL",
                    "value": {"booleanValue": false}
                }
            }));
        }

        // Filter by category if specified
        if let Some(cat) = category {
            filters.push(json!({
                "fieldFilter": {
                    "field": {"fieldPath": "category"},
                    "op": "EQUAL",
                    "value": {"stringValue": cat}
                }
            }));
        }

        // Build the where clause
        let where_clause = if filters.is_empty() {
            None
        } else if filters.len() == 1 {
            Some(filters.into_iter().next().unwrap())
        } else {
            Some(json!({
                "compositeFilter": {
                    "op": "AND",
                    "filters": filters
                }
            }))
        };

        // Build structured query
        let mut structured_query = json!({
            "from": [{"collectionId": ADVICE_SUBCOLLECTION}],
            "orderBy": [{"field": {"fieldPath": "created_at"}, "direction": "DESCENDING"}],
            "limit": limit,
            "offset": offset
        });

        if let Some(where_filter) = where_clause {
            structured_query["where"] = where_filter;
        }

        let query = json!({
            "structuredQuery": structured_query
        });

        let response = self
            .build_request(reqwest::Method::POST, &format!("{}:runQuery", parent))
            .await?
            .json(&query)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            tracing::error!("Firestore query error: {}", error_text);
            return Ok(vec![]);
        }

        let results: Vec<Value> = response.json().await?;
        let advice_list = results
            .into_iter()
            .filter_map(|doc| {
                doc.get("document")
                    .and_then(|d| self.parse_advice(d).ok())
            })
            .collect();

        Ok(advice_list)
    }

    /// Update advice (mark as read/dismissed)
    pub async fn update_advice(
        &self,
        uid: &str,
        advice_id: &str,
        is_read: Option<bool>,
        is_dismissed: Option<bool>,
    ) -> Result<AdviceDB, Box<dyn std::error::Error + Send + Sync>> {
        let mut field_paths: Vec<&str> = vec!["updated_at"];
        let mut fields = json!({
            "updated_at": {"timestampValue": Utc::now().to_rfc3339()}
        });

        if let Some(read) = is_read {
            field_paths.push("is_read");
            fields["is_read"] = json!({"booleanValue": read});
        }

        if let Some(dismissed) = is_dismissed {
            field_paths.push("is_dismissed");
            fields["is_dismissed"] = json!({"booleanValue": dismissed});
        }

        let update_mask = field_paths
            .iter()
            .map(|f| format!("updateMask.fieldPaths={}", f))
            .collect::<Vec<_>>()
            .join("&");

        let url = format!(
            "{}/{}/{}/{}/{}?{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            ADVICE_SUBCOLLECTION,
            advice_id,
            update_mask
        );

        let doc = json!({"fields": fields});

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore update error: {}", error_text).into());
        }

        let updated_doc: Value = response.json().await?;
        let advice = self.parse_advice(&updated_doc)?;

        tracing::info!("Updated advice {} for user {}", advice_id, uid);
        Ok(advice)
    }

    /// Delete advice permanently
    pub async fn delete_advice(
        &self,
        uid: &str,
        advice_id: &str,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            ADVICE_SUBCOLLECTION,
            advice_id
        );

        let response = self
            .build_request(reqwest::Method::DELETE, &url)
            .await?
            .send()
            .await?;

        if !response.status().is_success() && response.status() != reqwest::StatusCode::NOT_FOUND {
            let error_text = response.text().await?;
            return Err(format!("Firestore delete error: {}", error_text).into());
        }

        tracing::info!("Deleted advice {} for user {}", advice_id, uid);
        Ok(())
    }

    /// Mark all advice as read for a user
    pub async fn mark_all_advice_read(
        &self,
        uid: &str,
    ) -> Result<usize, Box<dyn std::error::Error + Send + Sync>> {
        // Get all unread advice
        let advice_list = self.get_advice(uid, 1000, 0, None, false).await?;
        let unread: Vec<_> = advice_list.iter().filter(|a| !a.is_read).collect();
        let count = unread.len();

        // Update each one
        for advice in unread {
            let _ = self.update_advice(uid, &advice.id, Some(true), None).await;
        }

        Ok(count)
    }

    /// Parse Firestore document to AdviceDB
    fn parse_advice(
        &self,
        doc: &Value,
    ) -> Result<AdviceDB, Box<dyn std::error::Error + Send + Sync>> {
        let fields = doc.get("fields").ok_or("Missing fields")?;
        let name = doc.get("name").and_then(|n| n.as_str()).unwrap_or("");
        let id = name.split('/').last().unwrap_or("").to_string();

        let category_str = self.parse_string(fields, "category").unwrap_or_else(|| "other".to_string());
        let category = match category_str.as_str() {
            "productivity" => AdviceCategory::Productivity,
            "health" => AdviceCategory::Health,
            "communication" => AdviceCategory::Communication,
            "learning" => AdviceCategory::Learning,
            _ => AdviceCategory::Other,
        };

        Ok(AdviceDB {
            id,
            content: self.parse_string(fields, "content").unwrap_or_default(),
            category,
            reasoning: self.parse_string(fields, "reasoning"),
            source_app: self.parse_string(fields, "source_app"),
            confidence: self.parse_float(fields, "confidence").unwrap_or(0.5),
            context_summary: self.parse_string(fields, "context_summary"),
            current_activity: self.parse_string(fields, "current_activity"),
            created_at: self.parse_timestamp_optional(fields, "created_at").unwrap_or_else(Utc::now),
            updated_at: self.parse_timestamp_optional(fields, "updated_at"),
            is_read: self.parse_bool(fields, "is_read").unwrap_or(false),
            is_dismissed: self.parse_bool(fields, "is_dismissed").unwrap_or(false),
        })
    }

    // =========================================================================
    // Desktop Releases (for Sparkle auto-update)
    // =========================================================================

    /// Get desktop releases for auto-update appcast
    /// Fetches from desktop_releases collection
    pub async fn get_desktop_releases(
        &self,
    ) -> Result<Vec<crate::routes::updates::ReleaseInfo>, Box<dyn std::error::Error + Send + Sync>> {
        let url = format!(
            "{}/desktop_releases",
            self.base_url()
        );

        let response = self
            .build_request(reqwest::Method::GET, &url)
            .await?
            .send()
            .await?;

        if !response.status().is_success() {
            // If collection doesn't exist, return empty list
            if response.status() == reqwest::StatusCode::NOT_FOUND {
                return Ok(vec![]);
            }
            let error_text = response.text().await?;
            return Err(format!("Firestore error: {}", error_text).into());
        }

        let data: Value = response.json().await?;
        let mut releases = Vec::new();

        if let Some(documents) = data.get("documents").and_then(|d| d.as_array()) {
            for doc in documents {
                if let Ok(release) = self.parse_release(doc) {
                    releases.push(release);
                }
            }
        }

        // Sort by build number descending (newest first)
        releases.sort_by(|a, b| b.build_number.cmp(&a.build_number));

        Ok(releases)
    }

    /// Parse Firestore document to ReleaseInfo
    fn parse_release(
        &self,
        doc: &Value,
    ) -> Result<crate::routes::updates::ReleaseInfo, Box<dyn std::error::Error + Send + Sync>> {
        let fields = doc.get("fields").ok_or("Missing fields")?;

        let changelog = if let Some(arr) = fields.get("changelog").and_then(|c| c.get("arrayValue")).and_then(|a| a.get("values")).and_then(|v| v.as_array()) {
            arr.iter()
                .filter_map(|v| v.get("stringValue").and_then(|s| s.as_str()))
                .map(|s| s.to_string())
                .collect()
        } else {
            vec![]
        };

        // channel: None means stable (missing field or null in Firestore)
        let channel = self.parse_string(fields, "channel");

        Ok(crate::routes::updates::ReleaseInfo {
            version: self.parse_string(fields, "version").unwrap_or_default(),
            build_number: self.parse_int(fields, "build_number").unwrap_or(0) as u32,
            download_url: self.parse_string(fields, "download_url").unwrap_or_default(),
            ed_signature: self.parse_string(fields, "ed_signature").unwrap_or_default(),
            published_at: self.parse_string(fields, "published_at").unwrap_or_default(),
            changelog,
            is_live: self.parse_bool(fields, "is_live").unwrap_or(false),
            is_critical: self.parse_bool(fields, "is_critical").unwrap_or(false),
            channel,
        })
    }

    /// Create a new desktop release in Firestore
    pub async fn create_desktop_release(
        &self,
        release: &crate::routes::updates::ReleaseInfo,
    ) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
        let doc_id = format!("v{}+{}", release.version, release.build_number);

        let url = format!(
            "{}/desktop_releases/{}",
            self.base_url(),
            doc_id
        );

        // Build changelog array
        let changelog_values: Vec<Value> = release.changelog
            .iter()
            .map(|s| json!({"stringValue": s}))
            .collect();

        // Channel field: stringValue for non-stable, nullValue for stable
        let channel_value = match &release.channel {
            Some(ch) if !ch.is_empty() => json!({"stringValue": ch}),
            _ => json!({"nullValue": null}),
        };

        let doc = json!({
            "fields": {
                "version": {"stringValue": release.version},
                "build_number": {"integerValue": release.build_number.to_string()},
                "download_url": {"stringValue": release.download_url},
                "ed_signature": {"stringValue": release.ed_signature},
                "published_at": {"stringValue": release.published_at},
                "changelog": {"arrayValue": {"values": changelog_values}},
                "is_live": {"booleanValue": release.is_live},
                "is_critical": {"booleanValue": release.is_critical},
                "channel": channel_value
            }
        });

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore create error: {}", error_text).into());
        }

        tracing::info!("Created desktop release: {}", doc_id);
        Ok(doc_id)
    }

    /// Promote a desktop release to the next channel: staging → beta → stable
    /// Returns (old_channel, new_channel) where empty string = stable
    pub async fn promote_desktop_release(
        &self,
        doc_id: &str,
    ) -> Result<(String, String), Box<dyn std::error::Error + Send + Sync>> {
        // Fetch the current document
        let url = format!(
            "{}/desktop_releases/{}",
            self.base_url(),
            doc_id
        );

        let response = self
            .build_request(reqwest::Method::GET, &url)
            .await?
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Release not found: {}", error_text).into());
        }

        let doc: Value = response.json().await?;
        let fields = doc.get("fields").ok_or("Missing fields in document")?;
        let current_channel = self.parse_string(fields, "channel").unwrap_or_default();

        // Determine next channel
        let (old_channel, new_channel_value) = match current_channel.as_str() {
            "staging" => ("staging".to_string(), json!({"stringValue": "beta"})),
            "beta" => ("beta".to_string(), json!({"nullValue": null})),
            "" => return Err("Release is already on stable channel, cannot promote further".into()),
            other => return Err(format!("Unknown channel '{}', cannot promote", other).into()),
        };

        let new_channel = match new_channel_value.get("stringValue").and_then(|v| v.as_str()) {
            Some(ch) => ch.to_string(),
            None => String::new(), // stable
        };

        // PATCH only the channel field
        let patch_url = format!(
            "{}/desktop_releases/{}?updateMask.fieldPaths=channel",
            self.base_url(),
            doc_id
        );

        let patch_doc = json!({
            "fields": {
                "channel": new_channel_value
            }
        });

        let response = self
            .build_request(reqwest::Method::PATCH, &patch_url)
            .await?
            .json(&patch_doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Failed to update channel: {}", error_text).into());
        }

        tracing::info!("Promoted release {}: {} → {}", doc_id,
            if old_channel.is_empty() { "stable" } else { &old_channel },
            if new_channel.is_empty() { "stable" } else { &new_channel },
        );

        Ok((old_channel, new_channel))
    }

    // =========================================================================
    // MESSAGES (Chat Persistence)
    // =========================================================================

    /// Get the mobile app's main chat session ID for a user.
    /// The mobile (Python) backend creates a chat_session with plugin_id=null for the main chat,
    /// and filters all messages by chat_session_id. Desktop messages must include this ID
    /// to be visible on mobile.
    pub async fn get_main_chat_session_id(
        &self,
        uid: &str,
    ) -> Result<Option<String>, Box<dyn std::error::Error + Send + Sync>> {
        // Fetch ALL chat sessions and filter client-side.
        // Firestore REST API's `WHERE plugin_id == null` does NOT match documents
        // where plugin_id is absent or was set to null by the Python SDK (gRPC).
        // So we fetch all sessions and find the main one ourselves.
        let url = format!(
            "{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            CHAT_SESSIONS_SUBCOLLECTION
        );

        let response = self
            .build_request(reqwest::Method::GET, &url)
            .await?
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            tracing::warn!("Failed to list chat sessions: {}", error_text);
            return Ok(None);
        }

        let body: Value = response.json().await?;
        let documents = match body.get("documents").and_then(|d| d.as_array()) {
            Some(docs) => docs,
            None => {
                tracing::info!("No chat sessions found for user {}", uid);
                return Ok(None);
            }
        };

        // Find main chat session: plugin_id is either null, absent, or empty string
        let mut best_session: Option<(String, usize)> = None; // (doc_id, message_count)
        for doc in documents {
            let fields = match doc.get("fields") {
                Some(f) => f,
                None => continue,
            };

            // Check plugin_id — main chat has null/absent/empty plugin_id
            let is_main = match fields.get("plugin_id") {
                None => true, // field absent = main chat
                Some(val) => {
                    // nullValue means explicitly null
                    if val.get("nullValue").is_some() {
                        true
                    } else if let Some(s) = val.get("stringValue").and_then(|v| v.as_str()) {
                        s.is_empty()
                    } else {
                        false
                    }
                }
            };

            if !is_main {
                continue;
            }

            // Extract doc ID from name
            let doc_id = match doc.get("name").and_then(|n| n.as_str()) {
                Some(name) => match name.split('/').last() {
                    Some(id) => id.to_string(),
                    None => continue,
                },
                None => continue,
            };

            // Count messages to find the most-used session
            let msg_count = fields
                .get("messages")
                .and_then(|m| m.get("arrayValue"))
                .and_then(|a| a.get("values"))
                .and_then(|v| v.as_array())
                .map(|arr| arr.len())
                .unwrap_or(0);

            if best_session.as_ref().map_or(true, |(_, count)| msg_count > *count) {
                best_session = Some((doc_id, msg_count));
            }
        }

        let session_id = best_session.map(|(id, _)| id);

        if let Some(ref id) = session_id {
            tracing::info!("Found main chat session {} for user {}", id, uid);
        } else {
            tracing::info!("No main chat session found for user {}", uid);
        }

        Ok(session_id)
    }

    /// Save a chat message to Firestore
    /// Used for chat history persistence
    pub async fn save_message(
        &self,
        uid: &str,
        text: &str,
        sender: &str,
        app_id: Option<&str>,
        session_id: Option<&str>,
        metadata: Option<&str>,
    ) -> Result<MessageDB, Box<dyn std::error::Error + Send + Sync>> {
        let message_id = uuid::Uuid::new_v4().to_string();
        let now = Utc::now();

        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            MESSAGES_SUBCOLLECTION,
            message_id
        );

        let mut fields = json!({
            // CRITICAL: id field required - Python queries .where('id', '==', message_id)
            "id": {"stringValue": &message_id},
            "text": {"stringValue": text},
            "sender": {"stringValue": sender},
            "created_at": {"timestampValue": now.to_rfc3339()},
            "reported": {"booleanValue": false},
            // CRITICAL: type field required - Python Message model requires it (no default)
            "type": {"stringValue": "text"},
            // Default empty arrays for memories_id
            "memories_id": {"arrayValue": {"values": []}},
            "from_external_integration": {"booleanValue": false}
        });

        // CRITICAL: Always set app_id and plugin_id fields (even as null) for backward compatibility
        // Python backend queries .where(plugin_id == null) for main chat
        // Firestore won't match documents that don't have the field at all
        if let Some(app) = app_id {
            fields["app_id"] = json!({"stringValue": app});
            fields["plugin_id"] = json!({"stringValue": app});
        } else {
            // For main chat (no app), explicitly set null values
            fields["app_id"] = json!({"nullValue": null});
            fields["plugin_id"] = json!({"nullValue": null});
        }

        // Determine chat_session_id for cross-platform compatibility
        // The mobile (Python) backend filters messages by chat_session_id,
        // so desktop messages must include the mobile's session ID to be visible there.
        let effective_session_id: Option<String> = if let Some(session) = session_id {
            Some(session.to_string())
        } else if app_id.is_none() {
            // Default main chat — look up the mobile's chat session
            match self.get_main_chat_session_id(uid).await {
                Ok(Some(main_session_id)) => {
                    tracing::info!(
                        "Using mobile main chat session {} for desktop message",
                        main_session_id
                    );
                    Some(main_session_id)
                }
                Ok(None) => {
                    tracing::info!("No mobile main chat session found for user {}", uid);
                    None
                }
                Err(e) => {
                    tracing::warn!("Failed to look up main chat session: {}", e);
                    None
                }
            }
        } else {
            None
        };

        if let Some(ref session) = effective_session_id {
            fields["session_id"] = json!({"stringValue": session});
            // Also set chat_session_id for Python compatibility
            fields["chat_session_id"] = json!({"stringValue": session});
        }

        if let Some(meta) = metadata {
            fields["metadata"] = json!({"stringValue": meta});
        }

        let doc = json!({"fields": fields});

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore create error: {}", error_text).into());
        }

        let message = MessageDB {
            id: message_id.clone(),
            text: text.to_string(),
            created_at: now,
            sender: sender.to_string(),
            app_id: app_id.map(|s| s.to_string()),
            session_id: effective_session_id,
            rating: None,
            reported: false,
            metadata: metadata.map(|s| s.to_string()),
        };

        tracing::info!(
            "Saved {} message {} for user {} (app_id={:?})",
            sender,
            message_id,
            uid,
            app_id
        );
        Ok(message)
    }

    /// Get chat messages for a user with optional app_id and session_id filter
    pub async fn get_messages(
        &self,
        uid: &str,
        app_id: Option<&str>,
        session_id: Option<&str>,
        limit: usize,
        offset: usize,
    ) -> Result<Vec<MessageDB>, Box<dyn std::error::Error + Send + Sync>> {
        let parent = format!("{}/{}/{}", self.base_url(), USERS_COLLECTION, uid);

        // Build filters
        let mut filters: Vec<Value> = Vec::new();

        if let Some(app) = app_id {
            filters.push(json!({
                "fieldFilter": {
                    "field": {"fieldPath": "app_id"},
                    "op": "EQUAL",
                    "value": {"stringValue": app}
                }
            }));
        }

        if let Some(session) = session_id {
            // NOTE: Use chat_session_id for backward compatibility
            // Old messages from Flutter app only have chat_session_id field
            // New messages have both session_id and chat_session_id
            filters.push(json!({
                "fieldFilter": {
                    "field": {"fieldPath": "chat_session_id"},
                    "op": "EQUAL",
                    "value": {"stringValue": session}
                }
            }));
        }

        // Build the where clause
        let where_clause = if filters.is_empty() {
            None
        } else if filters.len() == 1 {
            Some(filters.into_iter().next().unwrap())
        } else {
            Some(json!({
                "compositeFilter": {
                    "op": "AND",
                    "filters": filters
                }
            }))
        };

        // Build structured query - order by created_at descending to get most recent messages first
        // The UI will reverse to display in chronological order
        let mut structured_query = json!({
            "from": [{"collectionId": MESSAGES_SUBCOLLECTION}],
            "orderBy": [{"field": {"fieldPath": "created_at"}, "direction": "DESCENDING"}],
            "limit": limit,
            "offset": offset
        });

        if let Some(where_filter) = where_clause {
            structured_query["where"] = where_filter;
        }

        let query = json!({
            "structuredQuery": structured_query
        });

        let response = self
            .build_request(reqwest::Method::POST, &format!("{}:runQuery", parent))
            .await?
            .json(&query)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            tracing::error!("Firestore query error: {}", error_text);
            return Ok(vec![]);
        }

        let results: Vec<Value> = response.json().await?;
        let messages = results
            .into_iter()
            .filter_map(|doc| {
                doc.get("document")
                    .and_then(|d| self.parse_message(d, uid).ok())
            })
            .collect();

        Ok(messages)
    }

    /// Delete chat messages for a user with optional app_id filter
    /// Returns the count of deleted messages
    pub async fn delete_messages(
        &self,
        uid: &str,
        app_id: Option<&str>,
    ) -> Result<usize, Box<dyn std::error::Error + Send + Sync>> {
        // First, get all message IDs to delete
        let messages = self.get_messages(uid, app_id, None, 1000, 0).await?;
        let count = messages.len();

        if count == 0 {
            return Ok(0);
        }

        // Delete each message
        for message in messages {
            let url = format!(
                "{}/{}/{}/{}/{}",
                self.base_url(),
                USERS_COLLECTION,
                uid,
                MESSAGES_SUBCOLLECTION,
                message.id
            );

            let response = self
                .build_request(reqwest::Method::DELETE, &url)
                .await?
                .send()
                .await?;

            if !response.status().is_success() && response.status() != reqwest::StatusCode::NOT_FOUND {
                let error_text = response.text().await?;
                tracing::error!("Failed to delete message {}: {}", message.id, error_text);
            }
        }

        tracing::info!(
            "Deleted {} messages for user {} (app_id={:?})",
            count,
            uid,
            app_id
        );
        Ok(count)
    }

    /// Update a message's rating (thumbs up/down)
    /// rating: 1 = thumbs up, -1 = thumbs down, None = clear rating
    pub async fn update_message_rating(
        &self,
        uid: &str,
        message_id: &str,
        rating: Option<i32>,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            MESSAGES_SUBCOLLECTION,
            message_id
        );

        // First, get the existing message to preserve other fields
        let get_response = self
            .build_request(reqwest::Method::GET, &url)
            .await?
            .send()
            .await?;

        if get_response.status() == reqwest::StatusCode::NOT_FOUND {
            return Err("Message not found".into());
        }

        if !get_response.status().is_success() {
            let error_text = get_response.text().await?;
            return Err(format!("Failed to get message: {}", error_text).into());
        }

        let doc: Value = get_response.json().await?;
        let existing_fields = doc.get("fields").ok_or("Missing fields")?;

        // Build updated fields, preserving existing values
        let mut fields = json!({
            "text": existing_fields.get("text").cloned().unwrap_or(json!({"stringValue": ""})),
            "sender": existing_fields.get("sender").cloned().unwrap_or(json!({"stringValue": "human"})),
            "created_at": existing_fields.get("created_at").cloned().unwrap_or(json!({"timestampValue": Utc::now().to_rfc3339()})),
            "reported": existing_fields.get("reported").cloned().unwrap_or(json!({"booleanValue": false}))
        });

        // Preserve optional fields if they exist
        if let Some(app_id) = existing_fields.get("app_id") {
            fields["app_id"] = app_id.clone();
        }
        if let Some(session_id) = existing_fields.get("session_id") {
            fields["session_id"] = session_id.clone();
        }

        // Set the rating (or null to clear)
        match rating {
            Some(r) => {
                fields["rating"] = json!({"integerValue": r.to_string()});
            }
            None => {
                fields["rating"] = json!({"nullValue": null});
            }
        }

        let update_doc = json!({"fields": fields});

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&update_doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Failed to update message rating: {}", error_text).into());
        }

        tracing::info!(
            "Updated rating for message {} (user {}): {:?}",
            message_id,
            uid,
            rating
        );

        Ok(())
    }

    /// Parse a Firestore document into a MessageDB
    /// Decrypts text if data_protection_level is "enhanced" and encryption secret is available.
    fn parse_message(&self, doc: &Value, uid: &str) -> Result<MessageDB, Box<dyn std::error::Error + Send + Sync>> {
        let fields = doc.get("fields").ok_or("Missing fields")?;
        let name = doc.get("name").and_then(|n| n.as_str()).unwrap_or("");
        let id = name.split('/').last().unwrap_or("").to_string();

        // Get raw text
        let mut text = fields
            .get("text")
            .and_then(|v| v.get("stringValue"))
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();

        // Check if text is encrypted (data_protection_level = "enhanced")
        let data_protection_level = self.parse_string(fields, "data_protection_level");
        if data_protection_level.as_deref() == Some("enhanced") {
            if let Some(ref secret) = self.encryption_secret {
                match encryption::decrypt(&text, uid, secret) {
                    Ok(decrypted) => text = decrypted,
                    Err(e) => {
                        tracing::warn!("Failed to decrypt message {}: {}", id, e);
                        text = "[Encrypted message — decryption failed]".to_string();
                    }
                }
            } else {
                tracing::warn!(
                    "Message {} has enhanced protection but no encryption secret configured",
                    id
                );
                text = "[Encrypted message — decryption failed]".to_string();
            }
        }

        let sender = fields
            .get("sender")
            .and_then(|v| v.get("stringValue"))
            .and_then(|v| v.as_str())
            .unwrap_or("human")
            .to_string();

        let created_at = fields
            .get("created_at")
            .and_then(|v| v.get("timestampValue"))
            .and_then(|v| v.as_str())
            .and_then(|s| DateTime::parse_from_rfc3339(s).ok())
            .map(|dt| dt.with_timezone(&Utc))
            .unwrap_or_else(Utc::now);

        let app_id = fields
            .get("app_id")
            .and_then(|v| v.get("stringValue"))
            .and_then(|v| v.as_str())
            .map(|s| s.to_string());

        let session_id = fields
            .get("session_id")
            .and_then(|v| v.get("stringValue"))
            .and_then(|v| v.as_str())
            .map(|s| s.to_string());

        let rating = fields
            .get("rating")
            .and_then(|v| v.get("integerValue"))
            .and_then(|v| v.as_str())
            .and_then(|s| s.parse::<i32>().ok());

        let reported = fields
            .get("reported")
            .and_then(|v| v.get("booleanValue"))
            .and_then(|v| v.as_bool())
            .unwrap_or(false);

        let metadata = fields
            .get("metadata")
            .and_then(|v| v.get("stringValue"))
            .and_then(|v| v.as_str())
            .map(|s| s.to_string());

        Ok(MessageDB {
            id,
            text,
            created_at,
            sender,
            app_id,
            session_id,
            rating,
            reported,
            metadata,
        })
    }

    // =========================================================================
    // FOLDERS
    // =========================================================================

    /// Get all folders for a user
    pub async fn get_folders(
        &self,
        uid: &str,
    ) -> Result<Vec<Folder>, Box<dyn std::error::Error + Send + Sync>> {
        let parent = format!("{}/{}/{}", self.base_url(), USERS_COLLECTION, uid);

        let structured_query = json!({
            "from": [{"collectionId": FOLDERS_SUBCOLLECTION}],
            "orderBy": [{"field": {"fieldPath": "order"}, "direction": "ASCENDING"}]
        });

        let query = json!({
            "structuredQuery": structured_query
        });

        let response = self
            .build_request(reqwest::Method::POST, &format!("{}:runQuery", parent))
            .await?
            .json(&query)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            tracing::error!("Firestore query error: {}", error_text);
            return Ok(vec![]);
        }

        let results: Vec<Value> = response.json().await?;
        let folders = results
            .into_iter()
            .filter_map(|doc| doc.get("document").and_then(|d| self.parse_folder(d).ok()))
            .collect();

        Ok(folders)
    }

    /// Create a new folder
    pub async fn create_folder(
        &self,
        uid: &str,
        name: &str,
        description: Option<&str>,
        color: Option<&str>,
    ) -> Result<Folder, Box<dyn std::error::Error + Send + Sync>> {
        let folder_id = uuid::Uuid::new_v4().to_string();
        let now = Utc::now();

        let existing = self.get_folders(uid).await?;
        let order = existing.len() as i32;

        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            FOLDERS_SUBCOLLECTION,
            folder_id
        );

        let mut fields = json!({
            "name": {"stringValue": name},
            "color": {"stringValue": color.unwrap_or("#6B7280")},
            "order": {"integerValue": order.to_string()},
            "is_default": {"booleanValue": false},
            "is_system": {"booleanValue": false},
            "conversation_count": {"integerValue": "0"},
            "created_at": {"timestampValue": now.to_rfc3339()},
            "updated_at": {"timestampValue": now.to_rfc3339()}
        });

        if let Some(desc) = description {
            fields["description"] = json!({"stringValue": desc});
        }

        let doc = json!({"fields": fields});

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore create error: {}", error_text).into());
        }

        tracing::info!("Created folder {} for user {}", folder_id, uid);

        Ok(Folder {
            id: folder_id,
            name: name.to_string(),
            description: description.map(|s| s.to_string()),
            color: color.unwrap_or("#6B7280").to_string(),
            created_at: now,
            updated_at: now,
            order,
            is_default: false,
            is_system: false,
            category_mapping: None,
            conversation_count: 0,
        })
    }

    /// Update a folder
    pub async fn update_folder(
        &self,
        uid: &str,
        folder_id: &str,
        name: Option<&str>,
        description: Option<&str>,
        color: Option<&str>,
        order: Option<i32>,
    ) -> Result<Folder, Box<dyn std::error::Error + Send + Sync>> {
        let now = Utc::now();
        let mut field_paths: Vec<&str> = vec!["updated_at"];
        let mut fields = json!({
            "updated_at": {"timestampValue": now.to_rfc3339()}
        });

        if let Some(n) = name {
            field_paths.push("name");
            fields["name"] = json!({"stringValue": n});
        }

        if let Some(d) = description {
            field_paths.push("description");
            fields["description"] = json!({"stringValue": d});
        }

        if let Some(c) = color {
            field_paths.push("color");
            fields["color"] = json!({"stringValue": c});
        }

        if let Some(o) = order {
            field_paths.push("order");
            fields["order"] = json!({"integerValue": o.to_string()});
        }

        let update_mask = field_paths.iter().map(|f| format!("updateMask.fieldPaths={}", f)).collect::<Vec<_>>().join("&");

        let url = format!(
            "{}/{}/{}/{}/{}?{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            FOLDERS_SUBCOLLECTION,
            folder_id,
            update_mask
        );

        let doc = json!({"fields": fields});

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore update error: {}", error_text).into());
        }

        let updated_doc: Value = response.json().await?;
        let folder = self.parse_folder(&updated_doc)?;

        tracing::info!("Updated folder {} for user {}", folder_id, uid);
        Ok(folder)
    }

    /// Delete a folder
    pub async fn delete_folder(
        &self,
        uid: &str,
        folder_id: &str,
        move_to_folder_id: Option<&str>,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        if let Some(target_id) = move_to_folder_id {
            let conversations = self.get_conversations(uid, 100, 0, true, &[], None, Some(folder_id), None, None).await?;
            for conv in conversations {
                let _ = self.set_conversation_folder(uid, &conv.id, Some(target_id)).await;
            }
        } else {
            let conversations = self.get_conversations(uid, 100, 0, true, &[], None, Some(folder_id), None, None).await?;
            for conv in conversations {
                let _ = self.set_conversation_folder(uid, &conv.id, None).await;
            }
        }

        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            FOLDERS_SUBCOLLECTION,
            folder_id
        );

        let response = self.build_request(reqwest::Method::DELETE, &url).await?.send().await?;

        if !response.status().is_success() && response.status() != reqwest::StatusCode::NOT_FOUND {
            let error_text = response.text().await?;
            return Err(format!("Firestore delete error: {}", error_text).into());
        }

        tracing::info!("Deleted folder {} for user {}", folder_id, uid);
        Ok(())
    }

    /// Set conversation folder
    pub async fn set_conversation_folder(
        &self,
        uid: &str,
        conversation_id: &str,
        folder_id: Option<&str>,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let url = format!(
            "{}/{}/{}/{}/{}?updateMask.fieldPaths=folder_id",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            CONVERSATIONS_SUBCOLLECTION,
            conversation_id
        );

        let doc = if let Some(fid) = folder_id {
            json!({"fields": {"folder_id": {"stringValue": fid}}})
        } else {
            json!({"fields": {"folder_id": {"nullValue": null}}})
        };

        let response = self.build_request(reqwest::Method::PATCH, &url).await?.json(&doc).send().await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore update error: {}", error_text).into());
        }

        tracing::info!("Set conversation {} folder to {:?} for user {}", conversation_id, folder_id, uid);
        Ok(())
    }

    /// Bulk move conversations to a folder
    pub async fn bulk_move_to_folder(
        &self,
        uid: &str,
        folder_id: &str,
        conversation_ids: &[String],
    ) -> Result<i32, Box<dyn std::error::Error + Send + Sync>> {
        let mut moved_count = 0;
        for conv_id in conversation_ids {
            if self.set_conversation_folder(uid, conv_id, Some(folder_id)).await.is_ok() {
                moved_count += 1;
            }
        }
        tracing::info!("Bulk moved {} conversations to folder {} for user {}", moved_count, folder_id, uid);
        Ok(moved_count)
    }

    /// Reorder folders
    pub async fn reorder_folders(
        &self,
        uid: &str,
        folder_ids: &[String],
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        for (index, folder_id) in folder_ids.iter().enumerate() {
            let url = format!(
                "{}/{}/{}/{}/{}?updateMask.fieldPaths=order",
                self.base_url(),
                USERS_COLLECTION,
                uid,
                FOLDERS_SUBCOLLECTION,
                folder_id
            );

            let doc = json!({"fields": {"order": {"integerValue": index.to_string()}}});
            let _ = self.build_request(reqwest::Method::PATCH, &url).await?.json(&doc).send().await;
        }
        tracing::info!("Reordered {} folders for user {}", folder_ids.len(), uid);
        Ok(())
    }

    // ========================================
    // GOALS METHODS
    // ========================================

    /// Get all active goals for a user (max 3)
    pub async fn get_user_goals(
        &self,
        uid: &str,
        limit: usize,
    ) -> Result<Vec<GoalDB>, Box<dyn std::error::Error + Send + Sync>> {
        // Query the user's goals subcollection directly
        let url = format!(
            "{}/{}/{}:runQuery",
            self.base_url(),
            USERS_COLLECTION,
            uid
        );

        // Note: Don't use orderBy with where filter on different fields - requires composite index
        // Instead, we sort in Rust after fetching (like Python backend does)
        let query = json!({
            "structuredQuery": {
                "from": [{"collectionId": GOALS_SUBCOLLECTION}],
                "where": {
                    "fieldFilter": {
                        "field": {"fieldPath": "is_active"},
                        "op": "EQUAL",
                        "value": {"booleanValue": true}
                    }
                }
            }
        });

        let response = self
            .build_request(reqwest::Method::POST, &url)
            .await?
            .json(&query)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore query error: {}", error_text).into());
        }

        let results: Vec<Value> = response.json().await?;
        let mut goals = Vec::new();

        for result in results {
            if let Some(doc) = result.get("document") {
                if let Ok(goal) = self.parse_goal(doc) {
                    goals.push(goal);
                }
            }
        }

        // Sort by created_at descending (newest first) and apply limit
        goals.sort_by(|a, b| b.created_at.cmp(&a.created_at));
        goals.truncate(limit);

        tracing::info!("Found {} active goals for user {}", goals.len(), uid);
        Ok(goals)
    }

    /// Create a new goal for a user
    /// If user already has 3 active goals, deactivates the oldest one
    pub async fn create_goal(
        &self,
        uid: &str,
        title: &str,
        description: Option<&str>,
        goal_type: GoalType,
        target_value: f64,
        current_value: f64,
        min_value: f64,
        max_value: f64,
        unit: Option<&str>,
        source: Option<&str>,
    ) -> Result<GoalDB, Box<dyn std::error::Error + Send + Sync>> {
        // Check existing active goals
        let existing_goals = self.get_user_goals(uid, 10).await?;

        // If we have 3 or more active goals, deactivate the oldest one
        if existing_goals.len() >= 3 {
            if let Some(oldest) = existing_goals.last() {
                tracing::info!("Deactivating oldest goal {} to make room for new goal", oldest.id);
                self.update_goal(uid, &oldest.id, None, None, None, None, None, None, None, Some(false), None).await?;
            }
        }

        // Generate a unique ID
        let now = Utc::now();
        let goal_id = document_id_from_seed(&format!("{}-{}-{}", uid, title, now.timestamp_millis()));

        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            GOALS_SUBCOLLECTION,
            goal_id
        );

        let mut fields = json!({
            "title": {"stringValue": title},
            "goal_type": {"stringValue": match goal_type {
                GoalType::Boolean => "boolean",
                GoalType::Scale => "scale",
                GoalType::Numeric => "numeric",
            }},
            "target_value": {"doubleValue": target_value},
            "current_value": {"doubleValue": current_value},
            "min_value": {"doubleValue": min_value},
            "max_value": {"doubleValue": max_value},
            "is_active": {"booleanValue": true},
            "created_at": {"timestampValue": now.to_rfc3339()},
            "updated_at": {"timestampValue": now.to_rfc3339()}
        });

        if let Some(d) = description {
            fields.as_object_mut().unwrap().insert(
                "description".to_string(),
                json!({"stringValue": d}),
            );
        }

        if let Some(u) = unit {
            fields.as_object_mut().unwrap().insert(
                "unit".to_string(),
                json!({"stringValue": u}),
            );
        }

        if let Some(s) = source {
            fields.as_object_mut().unwrap().insert(
                "source".to_string(),
                json!({"stringValue": s}),
            );
        }

        let doc = json!({"fields": fields});

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore create goal error: {}", error_text).into());
        }

        let goal = GoalDB {
            id: goal_id,
            title: title.to_string(),
            description: description.map(|s| s.to_string()),
            goal_type,
            target_value,
            current_value,
            min_value,
            max_value,
            unit: unit.map(|s| s.to_string()),
            is_active: true,
            created_at: now,
            updated_at: now,
            completed_at: None,
            source: source.map(|s| s.to_string()),
        };

        tracing::info!("Created goal {} for user {}", goal.id, uid);
        Ok(goal)
    }

    /// Update an existing goal
    pub async fn update_goal(
        &self,
        uid: &str,
        goal_id: &str,
        title: Option<&str>,
        description: Option<&str>,
        target_value: Option<f64>,
        current_value: Option<f64>,
        min_value: Option<f64>,
        max_value: Option<f64>,
        unit: Option<&str>,
        is_active: Option<bool>,
        completed_at: Option<DateTime<Utc>>,
    ) -> Result<GoalDB, Box<dyn std::error::Error + Send + Sync>> {
        // Build update mask and fields
        let mut update_fields: Vec<&str> = vec![];
        let mut fields = serde_json::Map::new();
        let now = Utc::now();

        if let Some(t) = title {
            update_fields.push("title");
            fields.insert("title".to_string(), json!({"stringValue": t}));
        }
        if let Some(d) = description {
            update_fields.push("description");
            fields.insert("description".to_string(), json!({"stringValue": d}));
        }
        if let Some(v) = target_value {
            update_fields.push("target_value");
            fields.insert("target_value".to_string(), json!({"doubleValue": v}));
        }
        if let Some(v) = current_value {
            update_fields.push("current_value");
            fields.insert("current_value".to_string(), json!({"doubleValue": v}));
        }
        if let Some(v) = min_value {
            update_fields.push("min_value");
            fields.insert("min_value".to_string(), json!({"doubleValue": v}));
        }
        if let Some(v) = max_value {
            update_fields.push("max_value");
            fields.insert("max_value".to_string(), json!({"doubleValue": v}));
        }
        if let Some(u) = unit {
            update_fields.push("unit");
            fields.insert("unit".to_string(), json!({"stringValue": u}));
        }
        if let Some(active) = is_active {
            update_fields.push("is_active");
            fields.insert("is_active".to_string(), json!({"booleanValue": active}));
        }
        if let Some(cat) = completed_at {
            update_fields.push("completed_at");
            fields.insert("completed_at".to_string(), json!({"timestampValue": cat.to_rfc3339()}));
        }

        // Always update updated_at
        update_fields.push("updated_at");
        fields.insert("updated_at".to_string(), json!({"timestampValue": now.to_rfc3339()}));

        let update_mask = update_fields.iter()
            .map(|f| format!("updateMask.fieldPaths={}", f))
            .collect::<Vec<_>>()
            .join("&");

        let url = format!(
            "{}/{}/{}/{}/{}?{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            GOALS_SUBCOLLECTION,
            goal_id,
            update_mask
        );

        let doc = json!({"fields": fields});

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore update goal error: {}", error_text).into());
        }

        // Fetch the updated goal
        let goal = self.get_goal(uid, goal_id).await?
            .ok_or("Goal not found after update")?;

        tracing::info!("Updated goal {} for user {}", goal_id, uid);
        Ok(goal)
    }

    /// Update goal progress (current_value) and record history
    pub async fn update_goal_progress(
        &self,
        uid: &str,
        goal_id: &str,
        current_value: f64,
    ) -> Result<GoalDB, Box<dyn std::error::Error + Send + Sync>> {
        let goal = self.update_goal(uid, goal_id, None, None, None, Some(current_value), None, None, None, None, None).await?;

        // Also save history entry (inline, fast write)
        if let Err(e) = self.save_goal_progress_history(uid, goal_id, current_value).await {
            tracing::warn!("Failed to save goal progress history: {}", e);
        }

        // Auto-complete if current_value >= target_value
        if current_value >= goal.target_value && goal.completed_at.is_none() {
            tracing::info!("Goal {} completed! current_value={} >= target_value={}", goal_id, current_value, goal.target_value);
            let completed_goal = self.update_goal(uid, goal_id, None, None, None, None, None, None, None, Some(false), Some(Utc::now())).await?;
            return Ok(completed_goal);
        }

        Ok(goal)
    }

    /// Get inactive goals for a user (is_active == false — both completed and abandoned)
    pub async fn get_completed_goals(
        &self,
        uid: &str,
        limit: usize,
    ) -> Result<Vec<GoalDB>, Box<dyn std::error::Error + Send + Sync>> {
        let url = format!(
            "{}/{}/{}:runQuery",
            self.base_url(),
            USERS_COLLECTION,
            uid
        );

        let query = json!({
            "structuredQuery": {
                "from": [{"collectionId": GOALS_SUBCOLLECTION}],
                "where": {
                    "fieldFilter": {
                        "field": {"fieldPath": "is_active"},
                        "op": "EQUAL",
                        "value": {"booleanValue": false}
                    }
                }
            }
        });

        let response = self
            .build_request(reqwest::Method::POST, &url)
            .await?
            .json(&query)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore query completed goals error: {}", error_text).into());
        }

        let results: Vec<Value> = response.json().await?;
        let mut goals = Vec::new();

        for result in results {
            if let Some(doc) = result.get("document") {
                if let Ok(goal) = self.parse_goal(doc) {
                    goals.push(goal);
                }
            }
        }

        // Sort: completed goals first (by completed_at desc), then abandoned (by updated_at desc)
        goals.sort_by(|a, b| {
            let a_time = a.completed_at.unwrap_or(a.updated_at);
            let b_time = b.completed_at.unwrap_or(b.updated_at);
            b_time.cmp(&a_time)
        });
        goals.truncate(limit);

        tracing::info!("Found {} completed goals for user {}", goals.len(), uid);
        Ok(goals)
    }

    /// Save a progress history entry for a goal
    /// Writes to goals/{goal_id}/goal_history/{YYYY-MM-DD}
    pub async fn save_goal_progress_history(
        &self,
        uid: &str,
        goal_id: &str,
        value: f64,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let now = Utc::now();
        let date_key = now.format("%Y-%m-%d").to_string();

        let url = format!(
            "{}/{}/{}/{}/{}/goal_history/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            GOALS_SUBCOLLECTION,
            goal_id,
            date_key
        );

        let doc = json!({
            "fields": {
                "date": {"stringValue": &date_key},
                "value": {"doubleValue": value},
                "recorded_at": {"timestampValue": now.to_rfc3339()}
            }
        });

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore save goal history error: {}", error_text).into());
        }

        tracing::debug!("Saved goal history for {}/{}: {} on {}", uid, goal_id, value, date_key);
        Ok(())
    }

    /// Get progress history for a goal
    pub async fn get_goal_history(
        &self,
        uid: &str,
        goal_id: &str,
        days: u32,
    ) -> Result<Vec<GoalHistoryEntry>, Box<dyn std::error::Error + Send + Sync>> {
        use crate::models::GoalHistoryEntry;

        // Query the goal_history subcollection
        let parent = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            GOALS_SUBCOLLECTION,
            goal_id
        );

        let cutoff = Utc::now() - chrono::TimeDelta::days(days as i64);

        let query = json!({
            "structuredQuery": {
                "from": [{"collectionId": "goal_history"}],
                "where": {
                    "fieldFilter": {
                        "field": {"fieldPath": "recorded_at"},
                        "op": "GREATER_THAN_OR_EQUAL",
                        "value": {"timestampValue": cutoff.to_rfc3339()}
                    }
                },
                "orderBy": [{"field": {"fieldPath": "recorded_at"}, "direction": "DESCENDING"}],
                "limit": days as i64
            }
        });

        let response = self
            .build_request(reqwest::Method::POST, &format!("{}:runQuery", parent))
            .await?
            .json(&query)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore query goal history error: {}", error_text).into());
        }

        let results: Vec<Value> = response.json().await?;
        let mut history = Vec::new();

        for result in results {
            if let Some(doc) = result.get("document") {
                if let Some(fields) = doc.get("fields") {
                    let date = self.parse_string(fields, "date").unwrap_or_default();
                    let value = self.parse_double(fields, "value").unwrap_or(0.0);
                    let recorded_at = self.parse_timestamp_optional(fields, "recorded_at").unwrap_or_else(Utc::now);
                    history.push(GoalHistoryEntry { date, value, recorded_at });
                }
            }
        }

        tracing::info!("Found {} history entries for goal {}", history.len(), goal_id);
        Ok(history)
    }

    /// Delete a goal
    pub async fn delete_goal(
        &self,
        uid: &str,
        goal_id: &str,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            GOALS_SUBCOLLECTION,
            goal_id
        );

        let response = self
            .build_request(reqwest::Method::DELETE, &url)
            .await?
            .send()
            .await?;

        if !response.status().is_success() && response.status() != reqwest::StatusCode::NOT_FOUND {
            let error_text = response.text().await?;
            return Err(format!("Firestore delete goal error: {}", error_text).into());
        }

        tracing::info!("Deleted goal {} for user {}", goal_id, uid);
        Ok(())
    }

    /// Get a single goal by ID
    pub async fn get_goal(
        &self,
        uid: &str,
        goal_id: &str,
    ) -> Result<Option<GoalDB>, Box<dyn std::error::Error + Send + Sync>> {
        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            GOALS_SUBCOLLECTION,
            goal_id
        );

        let response = self
            .build_request(reqwest::Method::GET, &url)
            .await?
            .send()
            .await?;

        if response.status() == reqwest::StatusCode::NOT_FOUND {
            return Ok(None);
        }

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore get goal error: {}", error_text).into());
        }

        let doc: Value = response.json().await?;
        let goal = self.parse_goal(&doc)?;
        Ok(Some(goal))
    }

    /// Get action items for daily score calculation
    /// Returns (completed_count, total_count) for items due on the given date
    pub async fn get_action_items_for_daily_score(
        &self,
        uid: &str,
        due_start: &str,
        due_end: &str,
    ) -> Result<(i32, i32), Box<dyn std::error::Error + Send + Sync>> {
        // Use same URL pattern as working get_action_items method
        let parent = format!("{}/{}/{}", self.base_url(), USERS_COLLECTION, uid);
        let url = format!("{}:runQuery", parent);

        // We need to get all items due today, regardless of completion status
        let query = json!({
            "structuredQuery": {
                "from": [{"collectionId": ACTION_ITEMS_SUBCOLLECTION}],
                "where": {
                    "compositeFilter": {
                        "op": "AND",
                        "filters": [
                            {
                                "fieldFilter": {
                                    "field": {"fieldPath": "due_at"},
                                    "op": "GREATER_THAN_OR_EQUAL",
                                    "value": {"timestampValue": due_start}
                                }
                            },
                            {
                                "fieldFilter": {
                                    "field": {"fieldPath": "due_at"},
                                    "op": "LESS_THAN",
                                    "value": {"timestampValue": due_end}
                                }
                            }
                        ]
                    }
                },
                "limit": 100
            }
        });

        let response = self
            .build_request(reqwest::Method::POST, &url)
            .await?
            .json(&query)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore query error: {}", error_text).into());
        }

        let results: Vec<Value> = response.json().await?;
        let mut completed = 0;
        let mut total = 0;

        for result in results {
            if let Some(doc) = result.get("document") {
                if let Some(fields) = doc.get("fields") {
                    total += 1;
                    if self.parse_bool(fields, "completed").unwrap_or(false) {
                        completed += 1;
                    }
                }
            }
        }

        tracing::info!("Daily score for user {}: {}/{} tasks completed", uid, completed, total);
        Ok((completed, total))
    }

    /// Get action items for weekly score calculation (created in date range)
    pub async fn get_action_items_for_weekly_score(
        &self,
        uid: &str,
        start_date: &str,
        end_date: &str,
    ) -> Result<(i32, i32), Box<dyn std::error::Error + Send + Sync>> {
        // Use same URL pattern as working get_action_items method
        let parent = format!("{}/{}/{}", self.base_url(), USERS_COLLECTION, uid);
        let url = format!("{}:runQuery", parent);

        let query = json!({
            "structuredQuery": {
                "from": [{"collectionId": ACTION_ITEMS_SUBCOLLECTION}],
                "where": {
                    "compositeFilter": {
                        "op": "AND",
                        "filters": [
                            {
                                "fieldFilter": {
                                    "field": {"fieldPath": "created_at"},
                                    "op": "GREATER_THAN_OR_EQUAL",
                                    "value": {"timestampValue": start_date}
                                }
                            },
                            {
                                "fieldFilter": {
                                    "field": {"fieldPath": "created_at"},
                                    "op": "LESS_THAN",
                                    "value": {"timestampValue": end_date}
                                }
                            }
                        ]
                    }
                },
                "limit": 1000
            }
        });

        let response = self
            .build_request(reqwest::Method::POST, &url)
            .await?
            .json(&query)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore query error: {}", error_text).into());
        }

        let results: Vec<Value> = response.json().await?;
        let mut completed = 0;
        let mut total = 0;

        for result in results {
            if let Some(doc) = result.get("document") {
                if let Some(fields) = doc.get("fields") {
                    total += 1;
                    if self.parse_bool(fields, "completed").unwrap_or(false) {
                        completed += 1;
                    }
                }
            }
        }

        tracing::info!("Weekly score for user {}: {}/{} tasks completed", uid, completed, total);
        Ok((completed, total))
    }

    /// Get all action items for overall score calculation
    pub async fn get_action_items_for_overall_score(
        &self,
        uid: &str,
    ) -> Result<(i32, i32), Box<dyn std::error::Error + Send + Sync>> {
        let parent = format!("{}/{}/{}", self.base_url(), USERS_COLLECTION, uid);
        let agg_url = format!("{}:runAggregationQuery", parent);

        let structured_query = json!({
            "from": [{"collectionId": ACTION_ITEMS_SUBCOLLECTION}]
        });

        // Count total and completed in parallel using aggregation queries
        let total_query = json!({
            "structuredAggregationQuery": {
                "structuredQuery": structured_query,
                "aggregations": [{"alias": "count", "count": {}}]
            }
        });

        let completed_query = json!({
            "structuredAggregationQuery": {
                "structuredQuery": {
                    "from": [{"collectionId": ACTION_ITEMS_SUBCOLLECTION}],
                    "where": {
                        "fieldFilter": {
                            "field": {"fieldPath": "completed"},
                            "op": "EQUAL",
                            "value": {"booleanValue": true}
                        }
                    }
                },
                "aggregations": [{"alias": "count", "count": {}}]
            }
        });

        let (total_resp, completed_resp) = tokio::join!(
            async {
                self.build_request(reqwest::Method::POST, &agg_url)
                    .await?
                    .json(&total_query)
                    .send()
                    .await
                    .map_err(|e| -> Box<dyn std::error::Error + Send + Sync> { Box::new(e) })
            },
            async {
                self.build_request(reqwest::Method::POST, &agg_url)
                    .await?
                    .json(&completed_query)
                    .send()
                    .await
                    .map_err(|e| -> Box<dyn std::error::Error + Send + Sync> { Box::new(e) })
            }
        );

        let parse_count = |response: reqwest::Response| async move {
            if !response.status().is_success() {
                let error_text = response.text().await?;
                return Err(format!("Firestore aggregation query error: {}", error_text).into());
            }
            let results: Vec<Value> = response.json().await?;
            let count = results
                .first()
                .and_then(|r| r.get("result"))
                .and_then(|r| r.get("aggregateFields"))
                .and_then(|f| f.get("count"))
                .and_then(|c| c.get("integerValue"))
                .and_then(|v| v.as_str())
                .and_then(|s| s.parse::<i32>().ok())
                .unwrap_or(0);
            Ok::<i32, Box<dyn std::error::Error + Send + Sync>>(count)
        };

        let total = parse_count(total_resp?).await?;
        let completed = parse_count(completed_resp?).await?;

        tracing::info!("Overall score for user {}: {}/{} tasks completed", uid, completed, total);
        Ok((completed, total))
    }

    /// Parse a goal from Firestore document
    fn parse_goal(&self, doc: &Value) -> Result<GoalDB, Box<dyn std::error::Error + Send + Sync>> {
        let fields = doc.get("fields").ok_or("Missing fields")?;
        let name_path = doc.get("name").and_then(|n| n.as_str()).unwrap_or("");
        let id = name_path.split('/').last().unwrap_or("").to_string();

        let goal_type_str = self.parse_string(fields, "goal_type").unwrap_or_else(|| "boolean".to_string());
        let goal_type = match goal_type_str.as_str() {
            "scale" => GoalType::Scale,
            "numeric" => GoalType::Numeric,
            _ => GoalType::Boolean,
        };

        Ok(GoalDB {
            id,
            title: self.parse_string(fields, "title").unwrap_or_default(),
            description: self.parse_string(fields, "description"),
            goal_type,
            target_value: self.parse_double(fields, "target_value").unwrap_or(1.0),
            current_value: self.parse_double(fields, "current_value").unwrap_or(0.0),
            min_value: self.parse_double(fields, "min_value").unwrap_or(0.0),
            max_value: self.parse_double(fields, "max_value").unwrap_or(100.0),
            unit: self.parse_string(fields, "unit"),
            is_active: self.parse_bool(fields, "is_active").unwrap_or(true),
            created_at: self.parse_timestamp_optional(fields, "created_at").unwrap_or_else(Utc::now),
            updated_at: self.parse_timestamp_optional(fields, "updated_at").unwrap_or_else(Utc::now),
            completed_at: {
                if fields.get("completed_at").is_some() {
                    Some(self.parse_timestamp_optional(fields, "completed_at").unwrap_or_else(Utc::now))
                } else {
                    None
                }
            },
            source: self.parse_string(fields, "source"),
        })
    }

    /// Parse double value from Firestore fields
    fn parse_double(&self, fields: &Value, key: &str) -> Option<f64> {
        fields.get(key)
            .and_then(|v| {
                // Try doubleValue first
                if let Some(d) = v.get("doubleValue").and_then(|d| d.as_f64()) {
                    return Some(d);
                }
                // Try integerValue (Firestore sometimes stores numbers as integers)
                if let Some(i) = v.get("integerValue") {
                    if let Some(s) = i.as_str() {
                        return s.parse::<f64>().ok();
                    }
                    if let Some(n) = i.as_i64() {
                        return Some(n as f64);
                    }
                }
                None
            })
    }

    // =========================================================================
    // PERSONAS
    // =========================================================================

    /// Get user's persona (there can be only one per user)
    pub async fn get_user_persona(
        &self,
        uid: &str,
    ) -> Result<Option<PersonaDB>, Box<dyn std::error::Error + Send + Sync>> {
        let parent = self.base_url();

        // Query for persona with matching uid and persona capability
        let query = json!({
            "structuredQuery": {
                "from": [{"collectionId": APPS_COLLECTION}],
                "where": {
                    "compositeFilter": {
                        "op": "AND",
                        "filters": [
                            {
                                "fieldFilter": {
                                    "field": {"fieldPath": "uid"},
                                    "op": "EQUAL",
                                    "value": {"stringValue": uid}
                                }
                            },
                            {
                                "fieldFilter": {
                                    "field": {"fieldPath": "capabilities"},
                                    "op": "ARRAY_CONTAINS",
                                    "value": {"stringValue": "persona"}
                                }
                            }
                        ]
                    }
                },
                "limit": 1
            }
        });

        let response = self
            .build_request(reqwest::Method::POST, &format!("{}:runQuery", parent))
            .await?
            .json(&query)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            tracing::error!("Firestore query error: {}", error_text);
            return Ok(None);
        }

        let results: Vec<Value> = response.json().await?;

        // Return first matching persona
        for result in results {
            if let Some(doc) = result.get("document") {
                return Ok(Some(self.parse_persona(doc)?));
            }
        }

        Ok(None)
    }

    /// Create a new persona for user
    pub async fn create_persona(
        &self,
        uid: &str,
        name: &str,
        username: Option<&str>,
        description: &str,
        persona_prompt: Option<&str>,
        author: &str,
        email: Option<&str>,
    ) -> Result<PersonaDB, Box<dyn std::error::Error + Send + Sync>> {
        // Generate ULID-style ID
        let persona_id = ulid::Ulid::new().to_string();
        let now = Utc::now();

        let url = format!(
            "{}/{}/{}",
            self.base_url(),
            APPS_COLLECTION,
            persona_id
        );

        let mut fields = json!({
            "id": {"stringValue": &persona_id},
            "uid": {"stringValue": uid},
            "name": {"stringValue": name},
            "description": {"stringValue": description},
            "image": {"stringValue": ""},
            "category": {"stringValue": "personality-emulation"},
            "capabilities": {"arrayValue": {"values": [{"stringValue": "persona"}]}},
            "approved": {"booleanValue": false},
            "status": {"stringValue": "under-review"},
            "private": {"booleanValue": false},
            "author": {"stringValue": author},
            "created_at": {"timestampValue": now.to_rfc3339()},
            "updated_at": {"timestampValue": now.to_rfc3339()}
        });

        if let Some(uname) = username {
            fields["username"] = json!({"stringValue": uname});
        }
        if let Some(prompt) = persona_prompt {
            fields["persona_prompt"] = json!({"stringValue": prompt});
        }
        if let Some(e) = email {
            fields["email"] = json!({"stringValue": e});
        }

        let doc = json!({ "fields": fields });

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore create error: {}", error_text).into());
        }

        tracing::info!("Created persona {} for user {}", persona_id, uid);

        Ok(PersonaDB {
            id: persona_id,
            uid: uid.to_string(),
            name: name.to_string(),
            username: username.map(|s| s.to_string()),
            description: description.to_string(),
            image: String::new(),
            category: "personality-emulation".to_string(),
            capabilities: vec!["persona".to_string()],
            persona_prompt: persona_prompt.map(|s| s.to_string()),
            approved: false,
            status: "under-review".to_string(),
            is_private: false,
            author: author.to_string(),
            email: email.map(|s| s.to_string()),
            created_at: now,
            updated_at: now,
        })
    }

    /// Update an existing persona
    pub async fn update_persona(
        &self,
        persona_id: &str,
        name: Option<&str>,
        description: Option<&str>,
        persona_prompt: Option<&str>,
        image: Option<&str>,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let now = Utc::now();
        let mut update_fields = vec!["updated_at"];
        let mut fields = json!({
            "updated_at": {"timestampValue": now.to_rfc3339()}
        });

        if let Some(n) = name {
            fields["name"] = json!({"stringValue": n});
            update_fields.push("name");
        }
        if let Some(d) = description {
            fields["description"] = json!({"stringValue": d});
            update_fields.push("description");
        }
        if let Some(p) = persona_prompt {
            fields["persona_prompt"] = json!({"stringValue": p});
            update_fields.push("persona_prompt");
        }
        if let Some(i) = image {
            fields["image"] = json!({"stringValue": i});
            update_fields.push("image");
        }

        let update_mask = update_fields
            .iter()
            .map(|f| format!("updateMask.fieldPaths={}", f))
            .collect::<Vec<_>>()
            .join("&");

        let url = format!(
            "{}/{}/{}?{}",
            self.base_url(),
            APPS_COLLECTION,
            persona_id,
            update_mask
        );

        let doc = json!({ "fields": fields });

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore update error: {}", error_text).into());
        }

        tracing::info!("Updated persona {}", persona_id);
        Ok(())
    }

    /// Delete a persona
    pub async fn delete_persona(
        &self,
        persona_id: &str,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let url = format!(
            "{}/{}/{}",
            self.base_url(),
            APPS_COLLECTION,
            persona_id
        );

        let response = self
            .build_request(reqwest::Method::DELETE, &url)
            .await?
            .send()
            .await?;

        if !response.status().is_success() && response.status() != reqwest::StatusCode::NOT_FOUND {
            let error_text = response.text().await?;
            return Err(format!("Firestore delete error: {}", error_text).into());
        }

        tracing::info!("Deleted persona {}", persona_id);
        Ok(())
    }

    /// Check if a username is available
    pub async fn is_username_available(
        &self,
        username: &str,
    ) -> Result<bool, Box<dyn std::error::Error + Send + Sync>> {
        let parent = self.base_url();

        let query = json!({
            "structuredQuery": {
                "from": [{"collectionId": APPS_COLLECTION}],
                "where": {
                    "fieldFilter": {
                        "field": {"fieldPath": "username"},
                        "op": "EQUAL",
                        "value": {"stringValue": username}
                    }
                },
                "limit": 1
            }
        });

        let response = self
            .build_request(reqwest::Method::POST, &format!("{}:runQuery", parent))
            .await?
            .json(&query)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            tracing::error!("Firestore query error: {}", error_text);
            return Ok(false);
        }

        let results: Vec<Value> = response.json().await?;

        // Username is available if no documents found
        let has_document = results.iter().any(|r| r.get("document").is_some());
        Ok(!has_document)
    }

    /// Get public memories for a user (for persona generation)
    pub async fn get_public_memories(
        &self,
        uid: &str,
        limit: usize,
    ) -> Result<Vec<MemoryDB>, Box<dyn std::error::Error + Send + Sync>> {
        let parent = format!(
            "{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid
        );

        let query = json!({
            "structuredQuery": {
                "from": [{"collectionId": MEMORIES_SUBCOLLECTION}],
                "where": {
                    "fieldFilter": {
                        "field": {"fieldPath": "visibility"},
                        "op": "EQUAL",
                        "value": {"stringValue": "public"}
                    }
                },
                "orderBy": [{"field": {"fieldPath": "created_at"}, "direction": "DESCENDING"}],
                "limit": limit
            }
        });

        let response = self
            .build_request(reqwest::Method::POST, &format!("{}:runQuery", parent))
            .await?
            .json(&query)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            tracing::error!("Firestore query error: {}", error_text);
            return Ok(vec![]);
        }

        let results: Vec<Value> = response.json().await?;
        let memories: Vec<MemoryDB> = results
            .into_iter()
            .filter_map(|doc| {
                doc.get("document")
                    .and_then(|d| self.parse_memory(d, uid).ok())
            })
            .collect();

        tracing::info!("Found {} public memories for user {}", memories.len(), uid);
        Ok(memories)
    }

    /// Count public memories for a user
    pub async fn count_public_memories(
        &self,
        uid: &str,
    ) -> Result<i32, Box<dyn std::error::Error + Send + Sync>> {
        let memories = self.get_public_memories(uid, 1000).await?;
        Ok(memories.len() as i32)
    }

    /// Parse a persona from Firestore document
    fn parse_persona(&self, doc: &Value) -> Result<PersonaDB, Box<dyn std::error::Error + Send + Sync>> {
        let fields = doc.get("fields").ok_or("Missing fields")?;
        let name_path = doc.get("name").and_then(|n| n.as_str()).unwrap_or("");
        let id = name_path.split('/').last().unwrap_or("").to_string();

        let capabilities = {
            let caps = self.parse_string_array(fields, "capabilities");
            if caps.is_empty() {
                vec!["persona".to_string()]
            } else {
                caps
            }
        };

        Ok(PersonaDB {
            id,
            uid: self.parse_string(fields, "uid").unwrap_or_default(),
            name: self.parse_string(fields, "name").unwrap_or_default(),
            username: self.parse_string(fields, "username"),
            description: self.parse_string(fields, "description").unwrap_or_default(),
            image: self.parse_string(fields, "image").unwrap_or_default(),
            category: self.parse_string(fields, "category").unwrap_or_else(|| "personality-emulation".to_string()),
            capabilities,
            persona_prompt: self.parse_string(fields, "persona_prompt"),
            approved: self.parse_bool(fields, "approved").unwrap_or(false),
            status: self.parse_string(fields, "status").unwrap_or_else(|| "under-review".to_string()),
            is_private: self.parse_bool(fields, "private").unwrap_or(false),
            author: self.parse_string(fields, "author").unwrap_or_default(),
            email: self.parse_string(fields, "email"),
            created_at: self.parse_timestamp_optional(fields, "created_at").unwrap_or_else(Utc::now),
            updated_at: self.parse_timestamp_optional(fields, "updated_at").unwrap_or_else(Utc::now),
        })
    }

    /// Parse a folder from Firestore document
    fn parse_folder(&self, doc: &Value) -> Result<Folder, Box<dyn std::error::Error + Send + Sync>> {
        let fields = doc.get("fields").ok_or("Missing fields")?;
        let name_path = doc.get("name").and_then(|n| n.as_str()).unwrap_or("");
        let id = name_path.split('/').last().unwrap_or("").to_string();

        Ok(Folder {
            id,
            name: self.parse_string(fields, "name").unwrap_or_default(),
            description: self.parse_string(fields, "description"),
            color: self.parse_string(fields, "color").unwrap_or_else(|| "#6B7280".to_string()),
            created_at: self.parse_timestamp_optional(fields, "created_at").unwrap_or_else(Utc::now),
            updated_at: self.parse_timestamp_optional(fields, "updated_at").unwrap_or_else(Utc::now),
            order: self.parse_int(fields, "order").unwrap_or(0),
            is_default: self.parse_bool(fields, "is_default").unwrap_or(false),
            is_system: self.parse_bool(fields, "is_system").unwrap_or(false),
            category_mapping: self.parse_string(fields, "category_mapping"),
            conversation_count: self.parse_int(fields, "conversation_count").unwrap_or(0),
        })
    }

    // =========================================================================
    // PEOPLE - Speaker voice profiles for transcript naming
    // =========================================================================

    /// Get all people for a user
    pub async fn get_people(
        &self,
        uid: &str,
    ) -> Result<Vec<crate::models::Person>, Box<dyn std::error::Error + Send + Sync>> {
        let parent = format!("{}/{}/{}", self.base_url(), USERS_COLLECTION, uid);

        let structured_query = json!({
            "from": [{"collectionId": PEOPLE_SUBCOLLECTION}],
            "orderBy": [{"field": {"fieldPath": "name"}, "direction": "ASCENDING"}]
        });

        let query = json!({
            "structuredQuery": structured_query
        });

        let response = self
            .build_request(reqwest::Method::POST, &format!("{}:runQuery", parent))
            .await?
            .json(&query)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            tracing::error!("Firestore query error for people: {}", error_text);
            return Ok(vec![]);
        }

        let results: Vec<Value> = response.json().await?;
        let people = results
            .into_iter()
            .filter_map(|doc| doc.get("document").and_then(|d| self.parse_person(d).ok()))
            .collect();

        Ok(people)
    }

    /// Create a new person
    pub async fn create_person(
        &self,
        uid: &str,
        name: &str,
    ) -> Result<crate::models::Person, Box<dyn std::error::Error + Send + Sync>> {
        let person_id = uuid::Uuid::new_v4().to_string();
        let now = Utc::now();

        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            PEOPLE_SUBCOLLECTION,
            person_id
        );

        let fields = json!({
            "name": {"stringValue": name},
            "created_at": {"timestampValue": now.to_rfc3339()},
            "updated_at": {"timestampValue": now.to_rfc3339()}
        });

        let doc = json!({"fields": fields});

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore create person error: {}", error_text).into());
        }

        tracing::info!("Created person '{}' ({}) for user {}", name, person_id, uid);

        Ok(crate::models::Person {
            id: person_id,
            name: name.to_string(),
            created_at: now,
            updated_at: now,
        })
    }

    /// Update a person's name
    pub async fn update_person_name(
        &self,
        uid: &str,
        person_id: &str,
        new_name: &str,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let now = Utc::now();
        let url = format!(
            "{}/{}/{}/{}/{}?updateMask.fieldPaths=name&updateMask.fieldPaths=updated_at",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            PEOPLE_SUBCOLLECTION,
            person_id
        );

        let fields = json!({
            "name": {"stringValue": new_name},
            "updated_at": {"timestampValue": now.to_rfc3339()}
        });

        let doc = json!({"fields": fields});

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore update person error: {}", error_text).into());
        }

        Ok(())
    }

    /// Delete a person
    pub async fn delete_person(
        &self,
        uid: &str,
        person_id: &str,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            PEOPLE_SUBCOLLECTION,
            person_id
        );

        let response = self
            .build_request(reqwest::Method::DELETE, &url)
            .await?
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore delete person error: {}", error_text).into());
        }

        tracing::info!("Deleted person {} for user {}", person_id, uid);
        Ok(())
    }

    /// Bulk assign segments in a conversation to a person or user
    pub async fn assign_segments_bulk(
        &self,
        uid: &str,
        conversation_id: &str,
        segment_ids: &[String],
        assign_type: &str,
        value: Option<&str>,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        // Get the current conversation to read segments
        let conv = self.get_conversation(uid, conversation_id).await?
            .ok_or("Conversation not found")?;
        let mut segments = conv.transcript_segments;

        // Build a set of target segment IDs for fast lookup
        let target_ids: std::collections::HashSet<&str> =
            segment_ids.iter().map(|s| s.as_str()).collect();

        // Update matching segments
        for (idx, seg) in segments.iter_mut().enumerate() {
            // Segments may not have explicit IDs in Firestore — match by index as string
            let seg_id = idx.to_string();
            if target_ids.contains(seg_id.as_str()) {
                match assign_type {
                    "is_user" => {
                        seg.is_user = value.map(|v| v == "true").unwrap_or(false);
                        if seg.is_user {
                            seg.person_id = None;
                        }
                    }
                    "person_id" => {
                        seg.person_id = value.map(|s| s.to_string());
                        seg.is_user = false;
                    }
                    _ => {}
                }
            }
        }

        // Write updated segments back as array
        let segment_values: Vec<Value> = segments
            .iter()
            .map(|seg| {
                let mut fields = json!({
                    "text": {"stringValue": seg.text},
                    "speaker": {"stringValue": seg.speaker},
                    "speaker_id": {"integerValue": seg.speaker_id.to_string()},
                    "is_user": {"booleanValue": seg.is_user},
                    "start": {"doubleValue": seg.start},
                    "end": {"doubleValue": seg.end}
                });
                if let Some(ref pid) = seg.person_id {
                    fields["person_id"] = json!({"stringValue": pid});
                }
                json!({"mapValue": {"fields": fields}})
            })
            .collect();

        let url = format!(
            "{}/{}/{}/{}/{}?updateMask.fieldPaths=transcript_segments",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            CONVERSATIONS_SUBCOLLECTION,
            conversation_id
        );

        let doc = json!({
            "fields": {
                "transcript_segments": {
                    "arrayValue": {
                        "values": segment_values
                    }
                }
            }
        });

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore assign segments error: {}", error_text).into());
        }

        tracing::info!(
            "Assigned {} segments in conversation {} for user {}",
            segment_ids.len(),
            conversation_id,
            uid
        );
        Ok(())
    }

    /// Parse a person document from Firestore
    fn parse_person(
        &self,
        doc: &Value,
    ) -> Result<crate::models::Person, Box<dyn std::error::Error + Send + Sync>> {
        let fields = doc.get("fields").ok_or("Missing fields")?;
        let name_path = doc.get("name").and_then(|n| n.as_str()).unwrap_or("");
        let id = name_path.split('/').last().unwrap_or("").to_string();

        Ok(crate::models::Person {
            id,
            name: self.parse_string(fields, "name").unwrap_or_default(),
            created_at: self
                .parse_timestamp_optional(fields, "created_at")
                .unwrap_or_else(Utc::now),
            updated_at: self
                .parse_timestamp_optional(fields, "updated_at")
                .unwrap_or_else(Utc::now),
        })
    }

    // =========================================================================
    // KNOWLEDGE GRAPH - Nodes and Edges for 3D Memory Visualization
    // =========================================================================

    /// Create or update a knowledge graph node
    pub async fn upsert_kg_node(
        &self,
        uid: &str,
        node: &crate::models::KnowledgeGraphNode,
    ) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            KG_NODES_SUBCOLLECTION,
            node.id
        );

        // Build aliases arrays
        let aliases_values: Vec<Value> = node.aliases
            .iter()
            .map(|a| json!({"stringValue": a}))
            .collect();

        let aliases_lower_values: Vec<Value> = node.aliases_lower
            .iter()
            .map(|a| json!({"stringValue": a}))
            .collect();

        let memory_ids_values: Vec<Value> = node.memory_ids
            .iter()
            .map(|m| json!({"stringValue": m}))
            .collect();

        let doc = json!({
            "fields": {
                "id": {"stringValue": &node.id},
                "label": {"stringValue": &node.label},
                "node_type": {"stringValue": node.node_type.to_string()},
                "aliases": {"arrayValue": {"values": aliases_values}},
                "aliases_lower": {"arrayValue": {"values": aliases_lower_values}},
                "memory_ids": {"arrayValue": {"values": memory_ids_values}},
                "label_lower": {"stringValue": &node.label_lower},
                "created_at": {"timestampValue": node.created_at.to_rfc3339()},
                "updated_at": {"timestampValue": node.updated_at.to_rfc3339()}
            }
        });

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Failed to upsert KG node: {}", error_text).into());
        }

        Ok(node.id.clone())
    }

    /// Create or update a knowledge graph edge
    pub async fn upsert_kg_edge(
        &self,
        uid: &str,
        edge: &crate::models::KnowledgeGraphEdge,
    ) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            KG_EDGES_SUBCOLLECTION,
            edge.id
        );

        let memory_ids_values: Vec<Value> = edge.memory_ids
            .iter()
            .map(|m| json!({"stringValue": m}))
            .collect();

        let doc = json!({
            "fields": {
                "id": {"stringValue": &edge.id},
                "source_id": {"stringValue": &edge.source_id},
                "target_id": {"stringValue": &edge.target_id},
                "label": {"stringValue": &edge.label},
                "memory_ids": {"arrayValue": {"values": memory_ids_values}},
                "created_at": {"timestampValue": edge.created_at.to_rfc3339()}
            }
        });

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Failed to upsert KG edge: {}", error_text).into());
        }

        Ok(edge.id.clone())
    }

    /// Get all knowledge graph nodes for a user
    pub async fn get_kg_nodes(
        &self,
        uid: &str,
    ) -> Result<Vec<crate::models::KnowledgeGraphNode>, Box<dyn std::error::Error + Send + Sync>> {
        let url = format!(
            "{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            KG_NODES_SUBCOLLECTION
        );

        let response = self
            .build_request(reqwest::Method::GET, &url)
            .await?
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Failed to get KG nodes: {}", error_text).into());
        }

        let result: Value = response.json().await?;
        let documents = result.get("documents").and_then(|d| d.as_array());

        let nodes: Vec<crate::models::KnowledgeGraphNode> = documents
            .map(|docs| {
                docs.iter()
                    .filter_map(|doc| self.parse_kg_node(doc).ok())
                    .collect()
            })
            .unwrap_or_default();

        tracing::info!("Found {} KG nodes for user {}", nodes.len(), uid);
        Ok(nodes)
    }

    /// Get all knowledge graph edges for a user
    pub async fn get_kg_edges(
        &self,
        uid: &str,
    ) -> Result<Vec<crate::models::KnowledgeGraphEdge>, Box<dyn std::error::Error + Send + Sync>> {
        let url = format!(
            "{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            KG_EDGES_SUBCOLLECTION
        );

        let response = self
            .build_request(reqwest::Method::GET, &url)
            .await?
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Failed to get KG edges: {}", error_text).into());
        }

        let result: Value = response.json().await?;
        let documents = result.get("documents").and_then(|d| d.as_array());

        let edges: Vec<crate::models::KnowledgeGraphEdge> = documents
            .map(|docs| {
                docs.iter()
                    .filter_map(|doc| self.parse_kg_edge(doc).ok())
                    .collect()
            })
            .unwrap_or_default();

        tracing::info!("Found {} KG edges for user {}", edges.len(), uid);
        Ok(edges)
    }

    /// Delete all knowledge graph data for a user
    pub async fn delete_kg_data(
        &self,
        uid: &str,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        // Delete all nodes
        let nodes = self.get_kg_nodes(uid).await?;
        for node in &nodes {
            let url = format!(
                "{}/{}/{}/{}/{}",
                self.base_url(),
                USERS_COLLECTION,
                uid,
                KG_NODES_SUBCOLLECTION,
                node.id
            );
            let _ = self
                .build_request(reqwest::Method::DELETE, &url)
                .await?
                .send()
                .await;
        }

        // Delete all edges
        let edges = self.get_kg_edges(uid).await?;
        for edge in &edges {
            let url = format!(
                "{}/{}/{}/{}/{}",
                self.base_url(),
                USERS_COLLECTION,
                uid,
                KG_EDGES_SUBCOLLECTION,
                edge.id
            );
            let _ = self
                .build_request(reqwest::Method::DELETE, &url)
                .await?
                .send()
                .await;
        }

        tracing::info!("Deleted {} nodes and {} edges for user {}", nodes.len(), edges.len(), uid);
        Ok(())
    }

    /// Parse a knowledge graph node from Firestore document
    fn parse_kg_node(&self, doc: &Value) -> Result<crate::models::KnowledgeGraphNode, Box<dyn std::error::Error + Send + Sync>> {
        let fields = doc.get("fields").ok_or("Missing fields")?;

        let node_type_str = self.parse_string(fields, "node_type").unwrap_or_else(|| "concept".to_string());
        let node_type = match node_type_str.as_str() {
            "person" => crate::models::NodeType::Person,
            "place" => crate::models::NodeType::Place,
            "organization" => crate::models::NodeType::Organization,
            "thing" => crate::models::NodeType::Thing,
            _ => crate::models::NodeType::Concept,
        };

        Ok(crate::models::KnowledgeGraphNode {
            id: self.parse_string(fields, "id").unwrap_or_default(),
            label: self.parse_string(fields, "label").unwrap_or_default(),
            node_type,
            aliases: self.parse_string_array(fields, "aliases"),
            memory_ids: self.parse_string_array(fields, "memory_ids"),
            label_lower: self.parse_string(fields, "label_lower").unwrap_or_default(),
            aliases_lower: self.parse_string_array(fields, "aliases_lower"),
            created_at: self.parse_timestamp_optional(fields, "created_at").unwrap_or_else(Utc::now),
            updated_at: self.parse_timestamp_optional(fields, "updated_at").unwrap_or_else(Utc::now),
        })
    }

    /// Parse a knowledge graph edge from Firestore document
    fn parse_kg_edge(&self, doc: &Value) -> Result<crate::models::KnowledgeGraphEdge, Box<dyn std::error::Error + Send + Sync>> {
        let fields = doc.get("fields").ok_or("Missing fields")?;

        Ok(crate::models::KnowledgeGraphEdge {
            id: self.parse_string(fields, "id").unwrap_or_default(),
            source_id: self.parse_string(fields, "source_id").unwrap_or_default(),
            target_id: self.parse_string(fields, "target_id").unwrap_or_default(),
            label: self.parse_string(fields, "label").unwrap_or_default(),
            memory_ids: self.parse_string_array(fields, "memory_ids"),
            created_at: self.parse_timestamp_optional(fields, "created_at").unwrap_or_else(Utc::now),
        })
    }

    // =========================================================================
    // AGENT VM
    // =========================================================================

    /// Get agent VM info for a user from the agentVm field on their user document
    pub async fn get_agent_vm(
        &self,
        uid: &str,
    ) -> Result<Option<crate::models::agent::AgentVm>, Box<dyn std::error::Error + Send + Sync>> {
        let doc = self.get_user_document(uid).await?;
        let empty = json!({});
        let fields = doc.get("fields").unwrap_or(&empty);

        let agent_vm = fields.get("agentVm");
        if agent_vm.is_none() {
            return Ok(None);
        }

        let map_value = agent_vm
            .and_then(|v| v.get("mapValue"))
            .and_then(|v| v.get("fields"));

        if map_value.is_none() {
            return Ok(None);
        }

        let f = map_value.unwrap();

        let vm_name = f
            .get("vmName")
            .and_then(|v| v.get("stringValue"))
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();

        if vm_name.is_empty() {
            return Ok(None);
        }

        let zone = f
            .get("zone")
            .and_then(|v| v.get("stringValue"))
            .and_then(|v| v.as_str())
            .unwrap_or("us-central1-a")
            .to_string();

        let ip = f
            .get("ip")
            .and_then(|v| v.get("stringValue"))
            .and_then(|v| v.as_str())
            .map(|s| s.to_string());

        let status_str = f
            .get("status")
            .and_then(|v| v.get("stringValue"))
            .and_then(|v| v.as_str())
            .unwrap_or("provisioning");

        let status = match status_str {
            "ready" => crate::models::agent::AgentVmStatus::Ready,
            "stopped" => crate::models::agent::AgentVmStatus::Stopped,
            "error" => crate::models::agent::AgentVmStatus::Error,
            _ => crate::models::agent::AgentVmStatus::Provisioning,
        };

        let auth_token = f
            .get("authToken")
            .and_then(|v| v.get("stringValue"))
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();

        let created_at = f
            .get("createdAt")
            .and_then(|v| v.get("stringValue"))
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();

        let last_query_at = f
            .get("lastQueryAt")
            .and_then(|v| v.get("stringValue"))
            .and_then(|v| v.as_str())
            .map(|s| s.to_string());

        Ok(Some(crate::models::agent::AgentVm {
            vm_name,
            zone,
            ip,
            status,
            auth_token,
            created_at,
            last_query_at,
        }))
    }

    /// Set agent VM info on a user's document
    pub async fn set_agent_vm(
        &self,
        uid: &str,
        vm_name: &str,
        zone: &str,
        ip: Option<&str>,
        status: crate::models::agent::AgentVmStatus,
        auth_token: &str,
        created_at: &str,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let mut vm_fields = json!({
            "vmName": {"stringValue": vm_name},
            "zone": {"stringValue": zone},
            "status": {"stringValue": status.to_string()},
            "authToken": {"stringValue": auth_token},
            "createdAt": {"stringValue": created_at}
        });

        if let Some(ip_val) = ip {
            vm_fields.as_object_mut().unwrap().insert(
                "ip".to_string(),
                json!({"stringValue": ip_val}),
            );
        }

        let fields = json!({
            "agentVm": {
                "mapValue": {
                    "fields": vm_fields
                }
            }
        });

        self.update_user_fields(uid, fields, &["agentVm"]).await
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
}
