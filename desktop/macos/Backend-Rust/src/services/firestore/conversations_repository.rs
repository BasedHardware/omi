use super::*;

pub(super) fn build_conversations_query(
    limit: usize,
    offset: usize,
    include_discarded: bool,
    statuses: &[String],
    categories: Option<&[String]>,
    starred: Option<bool>,
    folder_id: Option<&str>,
    start_date: Option<&str>,
    end_date: Option<&str>,
    date_field: &str,
) -> Value {
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

    if let Some(category_values) = categories {
        if !category_values.is_empty() {
            filters.push(json!({
                "fieldFilter": {
                    "field": {"fieldPath": "structured.category"},
                    "op": "IN",
                    "value": {
                        "arrayValue": {
                            "values": category_values.iter().map(|s| json!({"stringValue": s})).collect::<Vec<_>>()
                        }
                    }
                }
            }));
        }
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

    if let Some(starred_val) = starred {
        filters.push(json!({
            "fieldFilter": {
                "field": {"fieldPath": "starred"},
                "op": "EQUAL",
                "value": {"booleanValue": starred_val}
            }
        }));
    }

    if let Some(fid) = folder_id {
        filters.push(json!({
            "fieldFilter": {
                "field": {"fieldPath": "folder_id"},
                "op": "EQUAL",
                "value": {"stringValue": fid}
            }
        }));
    }

    if let Some(start) = start_date {
        filters.push(json!({
            "fieldFilter": {
                "field": {"fieldPath": date_field},
                "op": "GREATER_THAN_OR_EQUAL",
                "value": {"timestampValue": start}
            }
        }));
    }

    if let Some(end) = end_date {
        filters.push(json!({
            "fieldFilter": {
                "field": {"fieldPath": date_field},
                "op": "LESS_THAN_OR_EQUAL",
                "value": {"timestampValue": end}
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

    let sort_field = if start_date.is_some() || end_date.is_some() {
        date_field
    } else {
        "created_at"
    };

    let mut structured_query = json!({
        "from": [{"collectionId": CONVERSATIONS_SUBCOLLECTION}],
        "orderBy": [{"field": {"fieldPath": sort_field}, "direction": "DESCENDING"}],
        "limit": limit,
        "offset": offset
    });

    if let Some(where_filter) = where_clause {
        structured_query["where"] = where_filter;
    }

    json!({ "structuredQuery": structured_query })
}

pub(super) fn update_mask_query(field_paths: impl IntoIterator<Item = String>) -> String {
    field_paths
        .into_iter()
        .map(|field| format!("updateMask.fieldPaths={}", urlencoding::encode(&field)))
        .collect::<Vec<_>>()
        .join("&")
}

pub(super) fn conversation_update_mask_query(doc: &Value) -> String {
    let mut field_paths = doc
        .get("fields")
        .and_then(Value::as_object)
        .map(|fields| {
            fields
                .keys()
                .filter(|field| field.as_str() != "structured")
                .cloned()
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    field_paths.extend(conversation_structured_leaf_paths(doc));
    update_mask_query(field_paths)
}

pub(super) fn conversation_structured_leaf_paths(doc: &Value) -> Vec<String> {
    doc.get("fields")
        .and_then(|fields| fields.get("structured"))
        .and_then(|structured| structured.get("mapValue"))
        .and_then(|map| map.get("fields"))
        .and_then(Value::as_object)
        .map(|fields| {
            fields
                .keys()
                .map(|field| format!("structured.{}", field))
                .collect::<Vec<_>>()
        })
        .unwrap_or_default()
}

pub(super) fn conversation_patch_url(
    base_url: &str,
    uid: &str,
    conversation_id: &str,
    doc: &Value,
) -> String {
    format!(
        "{}/{}/{}/{}/{}?{}",
        base_url,
        USERS_COLLECTION,
        uid,
        CONVERSATIONS_SUBCOLLECTION,
        conversation_id,
        conversation_update_mask_query(doc)
    )
}

impl FirestoreService {
    pub async fn get_conversations(
        &self,
        uid: &str,
        limit: usize,
        offset: usize,
        include_discarded: bool,
        statuses: &[String],
        categories: Option<&[String]>,
        starred: Option<bool>,
        folder_id: Option<&str>,
        start_date: Option<&str>,
        end_date: Option<&str>,
        date_field: &str,
    ) -> Result<Vec<Conversation>, Box<dyn std::error::Error + Send + Sync>> {
        let query = build_conversations_query(
            limit,
            offset,
            include_discarded,
            statuses,
            categories,
            starred,
            folder_id,
            start_date,
            end_date,
            date_field,
        );

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
        let doc = self.conversation_to_firestore(conversation, uid);
        let url = conversation_patch_url(&self.base_url(), uid, &conversation.id, &doc);

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
            .ok_or_else(|| "Conversation not found".to_string())?
            .apps_results;

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

#[cfg(test)]
#[allow(clippy::unwrap_used)]
mod contract_tests {
    use super::*;
    use chrono::TimeZone;

    fn fixture() -> Value {
        let path = format!(
            "{}/../../../contract_tests/fixtures/conversations.json",
            env!("CARGO_MANIFEST_DIR")
        );
        serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap()
    }

    fn field_filter<'a>(filters: &'a [Value], field: &str) -> &'a Value {
        filters
            .iter()
            .find(|filter| filter["fieldFilter"]["field"]["fieldPath"].as_str() == Some(field))
            .unwrap()
    }

    #[test]
    fn contract_conversation_query_matches_python_semantics() {
        let data = fixture();
        let query_fixture = &data["query"];
        let categories = vec!["work".to_string(), "technology".to_string()];
        let query = build_conversations_query(
            query_fixture["limit"].as_u64().unwrap() as usize,
            query_fixture["offset"].as_u64().unwrap() as usize,
            false,
            &["completed".to_string(), "in_progress".to_string()],
            Some(&categories),
            Some(true),
            Some("folder-1"),
            query_fixture["start_date"].as_str(),
            query_fixture["end_date"].as_str(),
            query_fixture["date_field"].as_str().unwrap(),
        );
        let structured = &query["structuredQuery"];
        let filters = structured["where"]["compositeFilter"]["filters"]
            .as_array()
            .unwrap();

        assert_eq!(
            field_filter(filters, "discarded")["fieldFilter"]["op"],
            "EQUAL"
        );
        assert_eq!(
            field_filter(filters, "structured.category")["fieldFilter"]["op"],
            "IN"
        );
        assert_eq!(field_filter(filters, "status")["fieldFilter"]["op"], "IN");
        assert_eq!(
            field_filter(filters, "starred")["fieldFilter"]["op"],
            "EQUAL"
        );
        assert_eq!(
            field_filter(filters, "folder_id")["fieldFilter"]["op"],
            "EQUAL"
        );
        assert_eq!(
            field_filter(filters, "finished_at")["fieldFilter"]["op"],
            "GREATER_THAN_OR_EQUAL"
        );
        assert!(filters.iter().any(|filter| {
            filter["fieldFilter"]["field"]["fieldPath"].as_str() == Some("finished_at")
                && filter["fieldFilter"]["op"] == "LESS_THAN_OR_EQUAL"
        }));
        assert_eq!(
            structured["orderBy"][0]["field"]["fieldPath"],
            query_fixture["date_field"]
        );
        assert_eq!(structured["limit"], query_fixture["limit"]);
        assert_eq!(structured["offset"], query_fixture["offset"]);

        let default_query =
            build_conversations_query(2, 1, false, &[], None, None, None, None, None, "created_at");
        assert_eq!(
            default_query["structuredQuery"]["orderBy"][0]["field"]["fieldPath"],
            "created_at"
        );

        let custom_date_without_range = build_conversations_query(
            2,
            1,
            false,
            &[],
            None,
            None,
            None,
            None,
            None,
            "finished_at",
        );
        assert_eq!(
            custom_date_without_range["structuredQuery"]["orderBy"][0]["field"]["fieldPath"],
            "created_at"
        );
    }

    #[test]
    fn contract_conversation_save_path_uses_update_mask_to_preserve_python_fields() {
        let service = FirestoreService::new_for_contract(None);
        let now = Utc.timestamp_opt(1_767_323_045, 0).unwrap();
        let conversation = Conversation {
            id: "conversation-1".to_string(),
            created_at: now,
            started_at: now,
            finished_at: now,
            source: crate::models::conversation::ConversationSource::Desktop,
            language: "en".to_string(),
            status: crate::models::conversation::ConversationStatus::Completed,
            discarded: false,
            deleted: false,
            starred: false,
            is_locked: false,
            folder_id: None,
            structured: Structured {
                title: "Rust title".to_string(),
                overview: "Rust overview".to_string(),
                emoji: "R".to_string(),
                category: Category::Technology,
                action_items: vec![],
                events: vec![],
            },
            transcript_segments: vec![],
            apps_results: vec![],
            geolocation: None,
            photos: vec![],
            input_device_name: None,
        };
        let doc = service.conversation_to_firestore(&conversation, "contract-user-8547");

        let url = conversation_patch_url(
            "https://firestore.googleapis.com/v1/projects/contract/databases/(default)/documents",
            "contract-user-8547",
            "conversation-1",
            &doc,
        );

        assert!(url.contains("updateMask.fieldPaths=id"));
        assert!(url.contains("updateMask.fieldPaths=created_at"));
        assert!(!url.contains("updateMask.fieldPaths=structured&"));
        assert!(url.contains("updateMask.fieldPaths=structured.title"));
        assert!(url.contains("updateMask.fieldPaths=structured.overview"));
        assert!(url.contains("updateMask.fieldPaths=structured.emoji"));
        assert!(url.contains("updateMask.fieldPaths=structured.category"));
        assert!(url.contains("updateMask.fieldPaths=transcript_segments"));
        assert!(!url.contains("plugins_results"));
        assert!(!url.contains("python_owned_field"));

        let existing = json!({
            "fields": {
                "python_owned_field": {"stringValue": "keep"},
                "structured": {
                    "mapValue": {
                        "fields": {
                            "title": {"stringValue": "old"},
                            "python_nested_field": {"stringValue": "keep nested"}
                        }
                    }
                }
            }
        });
        let patched =
            apply_update_mask_for_contract(existing, &doc, &conversation_update_mask_query(&doc));
        assert_eq!(
            patched["fields"]["python_owned_field"]["stringValue"],
            "keep"
        );
        assert_eq!(
            patched["fields"]["structured"]["mapValue"]["fields"]["python_nested_field"]
                ["stringValue"],
            "keep nested"
        );
        assert_eq!(
            patched["fields"]["structured"]["mapValue"]["fields"]["title"]["stringValue"],
            "Rust title"
        );
    }

    fn apply_update_mask_for_contract(
        mut existing: Value,
        patch: &Value,
        mask_query: &str,
    ) -> Value {
        for field in mask_query
            .split('&')
            .filter_map(|part| part.strip_prefix("updateMask.fieldPaths="))
            .map(|part| urlencoding::decode(part).unwrap().into_owned())
        {
            let patch_value = value_at_field_path(&patch["fields"], &field).cloned();
            if let Some(value) = patch_value {
                set_value_at_field_path(&mut existing["fields"], &field, value);
            }
        }
        existing
    }

    fn value_at_field_path<'a>(fields: &'a Value, field_path: &str) -> Option<&'a Value> {
        let mut current = fields;
        for (index, segment) in field_path.split('.').enumerate() {
            if index == 0 {
                current = current.get(segment)?;
            } else {
                current = current.get("mapValue")?.get("fields")?.get(segment)?;
            }
        }
        Some(current)
    }

    fn set_value_at_field_path(fields: &mut Value, field_path: &str, value: Value) {
        let mut current = fields;
        let parts = field_path.split('.').collect::<Vec<_>>();
        for (index, segment) in parts.iter().enumerate() {
            if index == parts.len() - 1 {
                current[*segment] = value;
                return;
            }
            current = &mut current[*segment]["mapValue"]["fields"];
        }
    }
}
