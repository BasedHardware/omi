use super::*;

impl FirestoreService {
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
            filters.into_iter().next()
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

            if !response.status().is_success()
                && response.status() != reqwest::StatusCode::NOT_FOUND
            {
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

    /// Delete all documents in a user subcollection and return deleted count.
    pub async fn delete_all_documents_in_subcollection(
        &self,
        uid: &str,
        subcollection: &str,
    ) -> Result<usize, Box<dyn std::error::Error + Send + Sync>> {
        let parent = format!("{}/{}/{}", self.base_url(), USERS_COLLECTION, uid);
        let query = json!({
            "structuredQuery": {
                "from": [{"collectionId": subcollection}],
                "limit": 5000
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
            return Err(format!(
                "Firestore query error for {}: {}",
                subcollection, error_text
            )
            .into());
        }

        let results: Vec<Value> = response.json().await?;
        let mut deleted = 0usize;

        for result in results {
            let Some(name) = result
                .get("document")
                .and_then(|d| d.get("name"))
                .and_then(|n| n.as_str())
            else {
                continue;
            };

            let Some(doc_id) = name.rsplit('/').next() else {
                continue;
            };

            let url = format!(
                "{}/{}/{}/{}/{}",
                self.base_url(),
                USERS_COLLECTION,
                uid,
                subcollection,
                doc_id
            );

            let delete_response = self
                .build_request(reqwest::Method::DELETE, &url)
                .await?
                .send()
                .await?;

            if delete_response.status().is_success()
                || delete_response.status() == reqwest::StatusCode::NOT_FOUND
            {
                deleted += 1;
            } else {
                let error_text = delete_response.text().await?;
                return Err(format!(
                    "Firestore delete error for {}/{}: {}",
                    subcollection, doc_id, error_text
                )
                .into());
            }
        }

        tracing::info!("Deleted {} docs from {}/{}", deleted, uid, subcollection);
        Ok(deleted)
    }

    /// Delete the user root document (`users/{uid}`).
    pub async fn delete_user_root_document(
        &self,
        uid: &str,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let url = format!("{}/{}/{}", self.base_url(), USERS_COLLECTION, uid);

        let response = self
            .build_request(reqwest::Method::DELETE, &url)
            .await?
            .send()
            .await?;

        if !response.status().is_success() && response.status() != reqwest::StatusCode::NOT_FOUND {
            let error_text = response.text().await?;
            return Err(format!("Firestore delete user root error: {}", error_text).into());
        }

        tracing::info!("Deleted user root doc for {}", uid);
        Ok(())
    }

    /// Delete Firebase Auth user by UID using service-account OAuth (admin path).
    pub async fn delete_firebase_auth_user(
        &self,
        project_id: &str,
        uid: &str,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let access_token = self.get_access_token().await?;
        let url = format!(
            "https://identitytoolkit.googleapis.com/v1/projects/{}/accounts:delete",
            project_id
        );

        let response = self
            .client
            .post(&url)
            .bearer_auth(access_token)
            .json(&json!({ "localId": uid }))
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            // Idempotent delete: if auth user is already gone, treat as success.
            if error_text.contains("USER_NOT_FOUND") {
                tracing::info!("Firebase Auth user {} already deleted", uid);
                return Ok(());
            }
            return Err(format!("Firebase admin accounts:delete failed: {}", error_text).into());
        }

        tracing::info!("Deleted Firebase Auth user {}", uid);
        Ok(())
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
            "{}/{}/{}/{}/{}?updateMask.fieldPaths=rating&currentDocument.exists=true",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            MESSAGES_SUBCOLLECTION,
            message_id
        );

        // Set the rating (or null to clear)
        let mut fields = json!({});
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
    fn parse_message(
        &self,
        doc: &Value,
        uid: &str,
    ) -> Result<MessageDB, Box<dyn std::error::Error + Send + Sync>> {
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
                        text = "[Protected message — cannot decrypt with current key]".to_string();
                    }
                }
            } else {
                tracing::warn!(
                    "Message {} has enhanced protection but no encryption secret configured",
                    id
                );
                text = "[Protected message — ENCRYPTION_SECRET not configured]".to_string();
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
}
