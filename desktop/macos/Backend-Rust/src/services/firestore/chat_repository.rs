use chrono::{DateTime, Utc};
use serde_json::{json, Value};

use super::{
    FirestoreService, CHAT_SESSIONS_SUBCOLLECTION, MESSAGES_SUBCOLLECTION, USERS_COLLECTION,
};
use crate::models::{ChatSessionDB, MessageDB};

fn build_create_chat_session_fields(
    session_id: &str,
    title: Option<&str>,
    app_id: Option<&str>,
    now: DateTime<Utc>,
) -> Value {
    let mut fields = json!({
        // CRITICAL: id field required - Python ChatSession model requires it
        // and chat.py accesses chat_session['id'] directly
        "id": {"stringValue": session_id},
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

    fields
}

fn build_acquire_chat_session_fields(
    session_id: &str,
    app_id: Option<&str>,
    now: DateTime<Utc>,
) -> Value {
    let mut session_fields = json!({
        "id": {"stringValue": session_id},
        "created_at": {"timestampValue": now.to_rfc3339()},
        "message_ids": {"arrayValue": {"values": []}},
        "file_ids": {"arrayValue": {"values": []}}
    });

    if let Some(app) = app_id {
        session_fields["plugin_id"] = json!({"stringValue": app});
        session_fields["app_id"] = json!({"stringValue": app});
    } else {
        session_fields["plugin_id"] = json!({"nullValue": null});
        session_fields["app_id"] = json!({"nullValue": null});
    }

    session_fields
}

fn build_save_message_fields(
    message_id: &str,
    text: &str,
    sender: &str,
    app_id: Option<&str>,
    session_id: Option<&str>,
    metadata: Option<&str>,
    now: DateTime<Utc>,
) -> Value {
    let mut fields = json!({
        // CRITICAL: id field required - Python queries .where('id', '==', message_id)
        "id": {"stringValue": message_id},
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

    if let Some(session) = session_id {
        fields["session_id"] = json!({"stringValue": session});
        fields["chat_session_id"] = json!({"stringValue": session});
    }

    if let Some(meta) = metadata {
        fields["metadata"] = json!({"stringValue": meta});
    }

    fields
}

fn null_or_empty_firestore_field(fields: &Value, key: &str) -> bool {
    match fields.get(key) {
        None => true,
        Some(val) => {
            val.get("nullValue").is_some()
                || val
                    .get("stringValue")
                    .and_then(|v| v.as_str())
                    .is_some_and(|s| s.is_empty())
        }
    }
}

fn chat_session_matches_app(fields: &Value, app_id: Option<&str>) -> bool {
    match app_id {
        Some(target_app) => {
            // Looking for a session with this specific plugin_id
            fields
                .get("plugin_id")
                .and_then(|v| v.get("stringValue"))
                .and_then(|v| v.as_str())
                == Some(target_app)
        }
        None => {
            // Looking for main chat: both plugin_id AND app_id must be
            // null, absent, or empty. Without the app_id check, task-chat
            // sessions (plugin_id=null, app_id="task-chat") match falsely.
            null_or_empty_firestore_field(fields, "plugin_id")
                && null_or_empty_firestore_field(fields, "app_id")
        }
    }
}

fn update_mask_query(field_paths: &[&str]) -> String {
    field_paths
        .iter()
        .map(|field| format!("updateMask.fieldPaths={}", urlencoding::encode(field)))
        .collect::<Vec<_>>()
        .join("&")
}

impl FirestoreService {
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

        let fields = build_create_chat_session_fields(&session_id, title, app_id, now);
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
            filters.into_iter().next()
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
        let existing = self
            .get_chat_session(uid, session_id)
            .await?
            .ok_or_else(|| format!("Chat session {} not found", session_id))?;

        let update_mask = update_mask_query(&["title", "starred", "updated_at"]);
        let url = format!(
            "{}/{}/{}/{}/{}?{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            CHAT_SESSIONS_SUBCOLLECTION,
            session_id,
            update_mask
        );

        let now = Utc::now();
        let fields = json!({
            "title": {"stringValue": title.unwrap_or(&existing.title)},
            "starred": {"booleanValue": starred.unwrap_or(existing.starred)},
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
            return Err(format!("Firestore update error: {}", error_text).into());
        }

        tracing::info!("Updated chat session {} for user {}", session_id, uid);

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

        let update_mask = update_mask_query(&["title", "preview", "updated_at", "message_count"]);
        let url = format!(
            "{}/{}/{}/{}/{}?{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            CHAT_SESSIONS_SUBCOLLECTION,
            session_id,
            update_mask
        );

        let now = Utc::now();
        let new_count = existing.message_count + 1;

        // Use provided title or keep existing (title is auto-generated from first message)
        let final_title = title.unwrap_or(&existing.title);

        let fields = json!({
            "title": {"stringValue": final_title},
            "preview": {"stringValue": preview.chars().take(100).collect::<String>()},
            "updated_at": {"timestampValue": now.to_rfc3339()},
            "message_count": {"integerValue": new_count.to_string()}
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
            tracing::warn!(
                "Failed to delete messages for session {}: {}",
                session_id,
                e
            );
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
        let mut deleted_count = 0;

        loop {
            // Query messages with this session_id. Re-query after each batch because
            // runQuery does not return a continuation token; once a batch is deleted,
            // the next matching documents move into the first page.
            let structured_query = json!({
                "from": [{"collectionId": MESSAGES_SUBCOLLECTION}],
                "where": {
                    "fieldFilter": {
                        "field": {"fieldPath": "session_id"},
                        "op": "EQUAL",
                        "value": {"stringValue": session_id}
                    }
                },
                "limit": 500
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
            let mut found_count = 0;
            let mut batch_count = 0;

            // Delete each message in the current batch.
            for result in results {
                if let Some(doc) = result.get("document") {
                    found_count += 1;
                    if let Some(name) = doc.get("name").and_then(|n| n.as_str()) {
                        // Extract the full document path for deletion
                        let delete_url = format!("https://firestore.googleapis.com/v1/{}", name);

                        let delete_response = self
                            .build_request(reqwest::Method::DELETE, &delete_url)
                            .await?
                            .send()
                            .await?;

                        if delete_response.status().is_success() {
                            deleted_count += 1;
                            batch_count += 1;
                        }
                    }
                }
            }

            if found_count < 500 || batch_count == 0 {
                break;
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

        let id = name.split('/').next_back().unwrap_or("unknown").to_string();

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

    /// Get or create a chat session for the given app_id (None = main default chat).
    /// Mirrors Python's `acquire_chat_session()`:
    ///   1. List all chat_sessions, find one matching plugin_id
    ///   2. If none exists, create one with {id, created_at, plugin_id}
    /// Returns the session ID.
    pub async fn acquire_chat_session(
        &self,
        uid: &str,
        app_id: Option<&str>,
    ) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
        // Step 1: Fetch all chat sessions and find a matching one client-side.
        // We can't use `WHERE plugin_id == null` via REST API - it doesn't match
        // documents where the field is absent or was set to null by the Python SDK.
        let list_url = format!(
            "{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            CHAT_SESSIONS_SUBCOLLECTION
        );

        let mut page_token: Option<String> = None;
        loop {
            let paged_url = if let Some(token) = &page_token {
                format!(
                    "{}?pageSize=100&pageToken={}",
                    list_url,
                    urlencoding::encode(token)
                )
            } else {
                format!("{}?pageSize=100", list_url)
            };

            let response = self
                .build_request(reqwest::Method::GET, &paged_url)
                .await?
                .send()
                .await?;

            if !response.status().is_success() {
                let error_text = response.text().await?;
                return Err(format!("Failed to list chat sessions: {}", error_text).into());
            }

            let body: Value = response.json().await?;
            if let Some(documents) = body.get("documents").and_then(|d| d.as_array()) {
                for doc in documents {
                    let fields = match doc.get("fields") {
                        Some(f) => f,
                        None => continue,
                    };

                    if chat_session_matches_app(fields, app_id) {
                        if let Some(doc_id) = doc
                            .get("name")
                            .and_then(|n| n.as_str())
                            .and_then(|name| name.split('/').next_back())
                        {
                            tracing::info!(
                                "Found existing chat session {} for user {} (app_id={:?})",
                                doc_id,
                                uid,
                                app_id
                            );
                            return Ok(doc_id.to_string());
                        }
                    }
                }
            }

            page_token = body
                .get("nextPageToken")
                .and_then(|token| token.as_str())
                .filter(|token| !token.is_empty())
                .map(ToOwned::to_owned);

            if page_token.is_none() {
                break;
            }
        }

        // Step 2: No matching session found - create one (mirrors Python's ChatSession model)
        let session_id = uuid::Uuid::new_v4().to_string();
        let now = Utc::now();

        let create_url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            CHAT_SESSIONS_SUBCOLLECTION,
            session_id
        );

        let session_fields = build_acquire_chat_session_fields(&session_id, app_id, now);
        let doc = json!({"fields": session_fields});

        let response = self
            .build_request(reqwest::Method::PATCH, &create_url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Failed to create chat session: {}", error_text).into());
        }

        tracing::info!(
            "Created new chat session {} for user {} (app_id={:?})",
            session_id,
            uid,
            app_id
        );
        Ok(session_id)
    }

    /// Append a message ID to a chat session's message_ids array.
    /// Mirrors Python's `add_message_to_chat_session()`.
    async fn add_message_to_chat_session(
        &self,
        uid: &str,
        chat_session_id: &str,
        message_id: &str,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        // Firestore REST API: use fieldTransforms with appendMissingElements
        // to atomically append to the array (equivalent to Python's ArrayUnion)
        let update = json!({
            "writes": [{
                "transform": {
                    "document": format!(
                        "projects/{}/databases/(default)/documents/{}/{}/{}/{}",
                        self.project_id, USERS_COLLECTION, uid,
                        CHAT_SESSIONS_SUBCOLLECTION, chat_session_id
                    ),
                    "fieldTransforms": [{
                        "fieldPath": "message_ids",
                        "appendMissingElements": {
                            "values": [{"stringValue": message_id}]
                        }
                    }]
                }
            }]
        });

        let commit_url = format!(
            "https://firestore.googleapis.com/v1/projects/{}/databases/(default)/documents:commit",
            self.project_id
        );

        let response = self
            .build_request(reqwest::Method::POST, &commit_url)
            .await?
            .json(&update)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            tracing::warn!(
                "Failed to add message {} to chat session {}: {}",
                message_id,
                chat_session_id,
                error_text
            );
        }

        Ok(())
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

        // Acquire (get or create) a chat session - mirrors Python's acquire_chat_session().
        // This ensures desktop messages have a chat_session_id so they're visible on mobile.
        let effective_session_id: Option<String> = if let Some(session) = session_id {
            Some(session.to_string())
        } else {
            match self.acquire_chat_session(uid, app_id).await {
                Ok(session) => Some(session),
                Err(e) => {
                    tracing::warn!("Failed to acquire chat session: {}", e);
                    None
                }
            }
        };

        let fields = build_save_message_fields(
            &message_id,
            text,
            sender,
            app_id,
            effective_session_id.as_deref(),
            metadata,
            now,
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
            return Err(format!("Firestore create error: {}", error_text).into());
        }

        // Track message in the chat session's message_ids array
        // (mirrors Python's add_message_to_chat_session)
        if let Some(ref session) = effective_session_id {
            if let Err(e) = self
                .add_message_to_chat_session(uid, session, &message_id)
                .await
            {
                tracing::warn!("Failed to track message in chat session: {}", e);
                // Non-fatal - message is already saved
            }
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
}

#[cfg(test)]
mod tests {
    use super::*;
    use reqwest::Client;
    use std::sync::Arc;
    use tokio::sync::RwLock;

    fn service() -> FirestoreService {
        FirestoreService {
            client: Client::new(),
            project_id: "test-project".to_string(),
            credentials: None,
            cached_token: Arc::new(RwLock::new(None)),
            encryption_secret: None,
        }
    }

    fn timestamp() -> DateTime<Utc> {
        match DateTime::parse_from_rfc3339("2026-06-26T12:34:56Z") {
            Ok(value) => value.with_timezone(&Utc),
            Err(error) => panic!("test timestamp should parse: {}", error),
        }
    }

    #[test]
    fn update_mask_query_encodes_requested_field_paths() {
        assert_eq!(
            update_mask_query(&["title", "structured.title"]),
            "updateMask.fieldPaths=title&updateMask.fieldPaths=structured.title"
        );
    }

    #[test]
    fn parse_chat_session_new_doc() {
        let doc = json!({
            "name": "projects/p/databases/(default)/documents/users/u/chat_sessions/session-1",
            "fields": {
                "title": {"stringValue": "A chat"},
                "preview": {"stringValue": "hello"},
                "created_at": {"timestampValue": "2026-06-26T12:00:00Z"},
                "updated_at": {"timestampValue": "2026-06-26T12:30:00Z"},
                "app_id": {"stringValue": "plugin-a"},
                "message_count": {"integerValue": "7"},
                "starred": {"booleanValue": true}
            }
        });

        let session = match service().parse_chat_session(&doc) {
            Ok(session) => session,
            Err(error) => panic!("chat session should parse: {}", error),
        };

        assert_eq!(session.id, "session-1");
        assert_eq!(session.title, "A chat");
        assert_eq!(session.preview.as_deref(), Some("hello"));
        assert_eq!(session.app_id.as_deref(), Some("plugin-a"));
        assert_eq!(session.message_count, 7);
        assert!(session.starred);
        assert_ne!(session.created_at, session.updated_at);
    }

    #[test]
    fn parse_chat_session_legacy_main_defaults() {
        let doc = json!({
            "name": "projects/p/databases/(default)/documents/users/u/chat_sessions/main",
            "fields": {
                "created_at": {"timestampValue": "2026-06-26T12:00:00Z"},
                "message_ids": {
                    "arrayValue": {
                        "values": [
                            {"stringValue": "message-1"},
                            {"stringValue": "message-2"}
                        ]
                    }
                },
                "plugin_id": {"nullValue": null},
                "app_id": {"nullValue": null}
            }
        });

        let session = match service().parse_chat_session(&doc) {
            Ok(session) => session,
            Err(error) => panic!("chat session should parse: {}", error),
        };

        assert_eq!(session.id, "main");
        assert_eq!(session.title, "Omi");
        assert_eq!(session.app_id, None);
        assert_eq!(session.message_count, 2);
        assert_eq!(session.created_at, session.updated_at);
        assert!(!session.starred);
    }

    #[test]
    fn parse_chat_session_legacy_plugin_fallback() {
        let doc = json!({
            "name": "projects/p/databases/(default)/documents/users/u/chat_sessions/plugin",
            "fields": {
                "created_at": {"timestampValue": "2026-06-26T12:00:00Z"},
                "plugin_id": {"stringValue": "plugin-legacy"},
                "message_ids": {"arrayValue": {"values": []}}
            }
        });

        let session = match service().parse_chat_session(&doc) {
            Ok(session) => session,
            Err(error) => panic!("chat session should parse: {}", error),
        };

        assert_eq!(session.title, "New Chat");
        assert_eq!(session.app_id.as_deref(), Some("plugin-legacy"));
        assert_eq!(session.message_count, 0);
    }

    #[test]
    fn app_matching_rejects_task_chat_false_positive() {
        let task_chat_fields = json!({
            "plugin_id": {"nullValue": null},
            "app_id": {"stringValue": "task-chat"}
        });
        let main_chat_fields = json!({
            "plugin_id": {"nullValue": null},
            "app_id": {"nullValue": null}
        });

        assert!(!chat_session_matches_app(&task_chat_fields, None));
        assert!(chat_session_matches_app(&main_chat_fields, None));
    }

    #[test]
    fn app_matching_accepts_legacy_main_shapes_and_requires_exact_plugin() {
        let absent_fields = json!({});
        let empty_fields = json!({
            "plugin_id": {"stringValue": ""},
            "app_id": {"stringValue": ""}
        });
        let plugin_fields = json!({
            "plugin_id": {"stringValue": "plugin-a"},
            "app_id": {"stringValue": "plugin-a"}
        });

        assert!(chat_session_matches_app(&absent_fields, None));
        assert!(chat_session_matches_app(&empty_fields, None));
        assert!(chat_session_matches_app(&plugin_fields, Some("plugin-a")));
        assert!(!chat_session_matches_app(&plugin_fields, Some("plugin-b")));
        assert!(!chat_session_matches_app(&plugin_fields, None));
    }

    #[test]
    fn create_chat_session_fields_preserve_main_nulls_and_plugin_fields() {
        let main_fields = build_create_chat_session_fields("session", None, None, timestamp());
        assert_eq!(main_fields["app_id"], json!({"nullValue": null}));
        assert_eq!(main_fields["plugin_id"], json!({"nullValue": null}));
        assert_eq!(main_fields["title"], json!({"stringValue": "New Chat"}));
        assert_eq!(main_fields["message_count"], json!({"integerValue": "0"}));

        let plugin_fields =
            build_create_chat_session_fields("session", Some("Title"), Some("app"), timestamp());
        assert_eq!(plugin_fields["app_id"], json!({"stringValue": "app"}));
        assert_eq!(plugin_fields["plugin_id"], json!({"stringValue": "app"}));
        assert_eq!(plugin_fields["title"], json!({"stringValue": "Title"}));
    }

    #[test]
    fn acquire_chat_session_fields_preserve_legacy_arrays_and_compat_fields() {
        let main_fields = build_acquire_chat_session_fields("session", None, timestamp());
        assert_eq!(main_fields["plugin_id"], json!({"nullValue": null}));
        assert_eq!(main_fields["app_id"], json!({"nullValue": null}));
        assert_eq!(
            main_fields["message_ids"],
            json!({"arrayValue": {"values": []}})
        );
        assert_eq!(
            main_fields["file_ids"],
            json!({"arrayValue": {"values": []}})
        );

        let plugin_fields =
            build_acquire_chat_session_fields("session", Some("plugin"), timestamp());
        assert_eq!(plugin_fields["plugin_id"], json!({"stringValue": "plugin"}));
        assert_eq!(plugin_fields["app_id"], json!({"stringValue": "plugin"}));
    }

    #[test]
    fn save_message_fields_preserve_session_and_app_compatibility_fields() {
        let main_fields = build_save_message_fields(
            "message",
            "hello",
            "user",
            None,
            Some("session"),
            Some("{}"),
            timestamp(),
        );
        assert_eq!(main_fields["app_id"], json!({"nullValue": null}));
        assert_eq!(main_fields["plugin_id"], json!({"nullValue": null}));
        assert_eq!(main_fields["session_id"], json!({"stringValue": "session"}));
        assert_eq!(
            main_fields["chat_session_id"],
            json!({"stringValue": "session"})
        );
        assert_eq!(main_fields["metadata"], json!({"stringValue": "{}"}));
        assert_eq!(main_fields["type"], json!({"stringValue": "text"}));

        let plugin_fields = build_save_message_fields(
            "message",
            "hello",
            "assistant",
            Some("plugin"),
            None,
            None,
            timestamp(),
        );
        assert_eq!(plugin_fields["app_id"], json!({"stringValue": "plugin"}));
        assert_eq!(plugin_fields["plugin_id"], json!({"stringValue": "plugin"}));
        assert!(plugin_fields.get("session_id").is_none());
        assert!(plugin_fields.get("chat_session_id").is_none());
    }
}
