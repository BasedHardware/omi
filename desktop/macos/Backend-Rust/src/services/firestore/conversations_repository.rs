use super::*;

impl FirestoreService {
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
            filters.into_iter().next()
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

        let parent = format!("{}/{}/{}", self.base_url(), USERS_COLLECTION, uid);

        tracing::debug!(
            "Firestore query: {}",
            serde_json::to_string_pretty(&query).unwrap_or_default()
        );

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

        tracing::info!(
            "Retrieved {} conversations for user {}",
            conversations.len(),
            uid
        );
        Ok(conversations)
    }

    /// Get count of conversations for a user using Firestore aggregation query
    pub async fn get_conversations_count(
        &self,
        uid: &str,
        include_discarded: bool,
        statuses: &[String],
    ) -> Result<i64, Box<dyn std::error::Error + Send + Sync>> {
        let parent = format!("{}/{}/{}", self.base_url(), USERS_COLLECTION, uid);

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
            filters.into_iter().next()
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
            .build_request(
                reqwest::Method::POST,
                &format!("{}:runAggregationQuery", parent),
            )
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
        let mut apps_results = current.map(|c| c.apps_results).unwrap_or_default();

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

        tracing::info!(
            "Added app result for app {} to conversation {}",
            app_id,
            conversation_id
        );
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
}
