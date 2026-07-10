use super::values::{conversation_source_wire, memory_category_wire, memory_is_active};
use super::*;

pub(super) fn build_memories_query(
    limit: usize,
    offset: usize,
    categories: Option<&[String]>,
    start_date: Option<&str>,
    end_date: Option<&str>,
    tags: Option<&[String]>,
) -> Value {
    let mut filters: Vec<Value> = Vec::new();

    if let Some(category_values) = categories {
        if !category_values.is_empty() {
            filters.push(json!({
                "fieldFilter": {
                    "field": {"fieldPath": "category"},
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
        "from": [{"collectionId": MEMORIES_SUBCOLLECTION}],
        "orderBy": [
            {"field": {"fieldPath": "scoring"}, "direction": "DESCENDING"},
            {"field": {"fieldPath": "created_at"}, "direction": "DESCENDING"}
        ],
        "limit": limit,
        "offset": offset
    });

    if let Some(where_filter) = where_clause {
        structured_query["where"] = where_filter;
    }

    json!({ "structuredQuery": structured_query })
}

pub(super) fn memory_passes_default_filters(
    memory: &MemoryDB,
    include_dismissed: bool,
    include_invalidated: bool,
    tags: Option<&[String]>,
) -> bool {
    if !memory_is_active(memory, include_invalidated) {
        return false;
    }
    if !include_dismissed && memory.is_dismissed {
        return false;
    }
    match tags {
        Some(filter_tags) if filter_tags.len() > 1 => {
            filter_tags[1..].iter().all(|tag| memory.tags.contains(tag))
        }
        _ => true,
    }
}

#[cfg(test)]
#[allow(clippy::unwrap_used)]
mod contract_tests {
    use super::*;
    use chrono::TimeZone;

    fn fixture() -> Value {
        let path = format!(
            "{}/../../../contract_tests/fixtures/memories.json",
            env!("CARGO_MANIFEST_DIR")
        );
        serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap()
    }

    fn memory(
        id: &str,
        user_review: Option<bool>,
        invalidated: bool,
        tags: Vec<String>,
    ) -> MemoryDB {
        let created_at = Utc.timestamp_opt(1_767_323_045, 0).unwrap();
        MemoryDB {
            id: id.to_string(),
            uid: "contract-user-8547".to_string(),
            content: id.to_string(),
            category: MemoryCategory::System,
            created_at,
            updated_at: created_at,
            memory_id: None,
            conversation_id: None,
            reviewed: false,
            user_review,
            visibility: "public".to_string(),
            manually_added: false,
            scoring: None,
            source: None,
            input_device_name: None,
            confidence: None,
            source_app: None,
            context_summary: None,
            is_read: false,
            is_dismissed: false,
            tags,
            reasoning: None,
            current_activity: None,
            window_title: None,
            data_protection_level: None,
            valid_at: Some(created_at),
            invalid_at: invalidated.then_some(created_at),
            superseded_by: None,
            edited: false,
            is_locked: false,
            kg_extracted: false,
            app_id: None,
        }
    }

    fn field_filter<'a>(filters: &'a [Value], field: &str) -> &'a Value {
        filters
            .iter()
            .find(|filter| filter["fieldFilter"]["field"]["fieldPath"].as_str() == Some(field))
            .unwrap()
    }

    fn memory_doc(id: &str, user_review: Option<bool>, invalidated: bool) -> Value {
        let created_at = "2026-01-02T03:04:05+00:00";
        let mut fields = json!({
            "content": {"stringValue": id},
            "category": {"stringValue": "system"},
            "created_at": {"timestampValue": created_at},
            "updated_at": {"timestampValue": created_at}
        });
        if let Some(review) = user_review {
            fields["user_review"] = json!({"booleanValue": review});
        } else {
            fields["user_review"] = json!({"nullValue": null});
        }
        if invalidated {
            fields["invalid_at"] = json!({"timestampValue": "2026-01-03T00:00:00+00:00"});
        }
        json!({
            "document": {
                "name": format!("projects/contract/databases/(default)/documents/users/contract-user-8547/memories/{}", id),
                "fields": fields
            }
        })
    }

    #[test]
    fn contract_memories_query_and_filter_semantics_match_python() {
        let data = fixture();
        let query_fixture = &data["query"];
        let tags = vec!["first".to_string(), "second".to_string()];
        let categories = query_fixture["categories"]
            .as_array()
            .unwrap()
            .iter()
            .map(|value| value.as_str().unwrap().to_string())
            .collect::<Vec<_>>();
        let query = build_memories_query(
            query_fixture["limit"].as_u64().unwrap() as usize,
            query_fixture["offset"].as_u64().unwrap() as usize,
            Some(&categories),
            query_fixture["start_date"].as_str(),
            query_fixture["end_date"].as_str(),
            Some(&tags),
        );
        let structured = &query["structuredQuery"];
        let filters = structured["where"]["compositeFilter"]["filters"]
            .as_array()
            .unwrap();

        assert_eq!(field_filter(filters, "category")["fieldFilter"]["op"], "IN");
        assert_eq!(
            field_filter(filters, "created_at")["fieldFilter"]["op"],
            "GREATER_THAN_OR_EQUAL"
        );
        assert!(filters.iter().any(|filter| {
            filter["fieldFilter"]["field"]["fieldPath"].as_str() == Some("created_at")
                && filter["fieldFilter"]["op"] == "LESS_THAN_OR_EQUAL"
        }));
        assert_eq!(
            field_filter(filters, "category")["fieldFilter"]["value"]["arrayValue"]["values"][1]
                ["stringValue"],
            "workflow"
        );
        assert_eq!(
            field_filter(filters, "tags")["fieldFilter"]["op"],
            "ARRAY_CONTAINS"
        );
        assert_eq!(structured["orderBy"][0]["field"]["fieldPath"], "scoring");
        assert_eq!(structured["orderBy"][1]["field"]["fieldPath"], "created_at");
        assert_eq!(structured["limit"], query_fixture["limit"]);
        assert_eq!(structured["offset"], query_fixture["offset"]);

        let paged_query = build_memories_query(2, 1, None, None, None, None);
        assert_eq!(paged_query["structuredQuery"]["limit"], 2);
        assert_eq!(paged_query["structuredQuery"]["offset"], 1);

        assert!(memory_passes_default_filters(
            &memory(
                "active",
                None,
                false,
                vec!["first".to_string(), "second".to_string()]
            ),
            false,
            false,
            Some(&tags)
        ));
        assert!(memory_passes_default_filters(
            &memory("invalidated", None, true, tags.clone()),
            false,
            true,
            Some(&tags)
        ));
        assert!(!memory_passes_default_filters(
            &memory("rejected", Some(false), false, tags.clone()),
            false,
            false,
            Some(&tags)
        ));
        assert!(!memory_passes_default_filters(
            &memory("invalidated", None, true, tags.clone()),
            false,
            false,
            Some(&tags)
        ));
        assert!(!memory_passes_default_filters(
            &memory("missing-tag", None, false, vec!["first".to_string()]),
            false,
            false,
            Some(&tags)
        ));

        let service = FirestoreService::new_for_contract(None);
        let page_results = vec![
            memory_doc("rejected-in-page", Some(false), false),
            memory_doc("active-in-page", None, false),
        ];
        let filtered = service.parse_memory_query_results(
            "contract-user-8547",
            page_results,
            false,
            false,
            None,
        );
        assert_eq!(
            filtered
                .iter()
                .map(|memory| memory.id.as_str())
                .collect::<Vec<_>>(),
            vec!["active-in-page"]
        );
    }

    #[test]
    fn contract_create_memory_path_writes_manual_true_and_extracted_null_user_review() {
        let now = Utc.timestamp_opt(1_767_323_045, 0).unwrap();
        let fields = build_create_memory_fields(
            "memory-1",
            "contract-user-8547",
            "content",
            "public",
            &MemoryCategory::Workflow,
            false,
            "00_998_1767323045",
            now,
            &["contract".to_string()],
        );

        assert_eq!(fields["category"]["stringValue"], "workflow");
        assert_eq!(fields["valid_at"]["timestampValue"], now.to_rfc3339());
        assert_eq!(fields["edited"]["booleanValue"], false);
        assert_eq!(fields["is_locked"]["booleanValue"], false);
        assert_eq!(fields["kg_extracted"]["booleanValue"], false);
        assert_eq!(fields["reviewed"]["booleanValue"], false);
        assert_eq!(fields["user_review"]["nullValue"], Value::Null);

        let fields = build_create_memory_fields(
            "memory-manual",
            "contract-user-8547",
            "content",
            "public",
            &MemoryCategory::Manual,
            true,
            "01_998_1767323045",
            now,
            &[],
        );

        assert_eq!(fields["reviewed"]["booleanValue"], true);
        assert_eq!(fields["user_review"]["booleanValue"], true);

        let memory = Memory {
            content: "saved".to_string(),
            category: MemoryCategory::Workflow,
            tags: vec![],
        };
        let fields = build_save_memory_fields(
            "memory-2",
            "contract-user-8547",
            "conversation-1",
            &memory,
            "00_998_1767323045",
            now,
        );

        assert_eq!(fields["category"]["stringValue"], "workflow");
        assert_eq!(fields["valid_at"]["timestampValue"], now.to_rfc3339());
        assert_eq!(fields["user_review"]["nullValue"], Value::Null);
        assert_eq!(fields["memory_id"]["stringValue"], "conversation-1");
    }
}

pub(super) fn build_create_memory_fields(
    memory_id: &str,
    uid: &str,
    content: &str,
    visibility: &str,
    category: &MemoryCategory,
    manually_added: bool,
    scoring: &str,
    now: DateTime<Utc>,
    tags: &[String],
) -> Value {
    let tags_values: Vec<Value> = tags.iter().map(|t| json!({"stringValue": t})).collect();
    let mut fields = json!({
        "id": {"stringValue": memory_id},
        "uid": {"stringValue": uid},
        "content": {"stringValue": content},
        "category": {"stringValue": memory_category_wire(category)},
        "created_at": {"timestampValue": now.to_rfc3339()},
        "updated_at": {"timestampValue": now.to_rfc3339()},
        "valid_at": {"timestampValue": now.to_rfc3339()},
        "reviewed": {"booleanValue": manually_added},
        "visibility": {"stringValue": visibility},
        "manually_added": {"booleanValue": manually_added},
        "scoring": {"stringValue": scoring},
        "is_read": {"booleanValue": false},
        "is_dismissed": {"booleanValue": false},
        "edited": {"booleanValue": false},
        "is_locked": {"booleanValue": false},
        "kg_extracted": {"booleanValue": false},
        "tags": {"arrayValue": {"values": tags_values}}
    });
    if manually_added {
        fields["user_review"] = json!({"booleanValue": true});
    } else {
        fields["user_review"] = json!({"nullValue": null});
    }
    fields
}

pub(super) fn build_save_memory_fields(
    memory_id: &str,
    uid: &str,
    conversation_id: &str,
    memory: &Memory,
    scoring: &str,
    now: DateTime<Utc>,
) -> Value {
    json!({
        "id": {"stringValue": memory_id},
        "uid": {"stringValue": uid},
        "content": {"stringValue": memory.content},
        "category": {"stringValue": memory_category_wire(&memory.category)},
        "created_at": {"timestampValue": now.to_rfc3339()},
        "updated_at": {"timestampValue": now.to_rfc3339()},
        "valid_at": {"timestampValue": now.to_rfc3339()},
        "conversation_id": {"stringValue": conversation_id},
        "memory_id": {"stringValue": conversation_id},
        "reviewed": {"booleanValue": false},
        "user_review": {"nullValue": null},
        "visibility": {"stringValue": "private"},
        "manually_added": {"booleanValue": false},
        "edited": {"booleanValue": false},
        "is_locked": {"booleanValue": false},
        "kg_extracted": {"booleanValue": false},
        "scoring": {"stringValue": scoring},
        "tags": {"arrayValue": {"values": []}}
    })
}

impl FirestoreService {
    pub async fn get_memories_filtered(
        &self,
        uid: &str,
        limit: usize,
        offset: usize,
        categories: Option<&[String]>,
        start_date: Option<&str>,
        end_date: Option<&str>,
        tags: Option<&[String]>,
        include_dismissed: bool,
        include_invalidated: bool,
    ) -> Result<Vec<MemoryDB>, Box<dyn std::error::Error + Send + Sync>> {
        let parent = format!("{}/{}/{}", self.base_url(), USERS_COLLECTION, uid);

        let query = build_memories_query(limit, offset, categories, start_date, end_date, tags);

        let response = self
            .build_request(reqwest::Method::POST, &format!("{}:runQuery", parent))
            .await?
            .json(&query)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            tracing::error!("Firestore query error for memories: {}", error_text);
            return Err(format!("Firestore query error: {}", error_text).into());
        }

        let results: Vec<Value> = response.json().await?;
        let mut memories = self.parse_memory_query_results(
            uid,
            results,
            include_dismissed,
            include_invalidated,
            tags,
        );

        // Enrich memories with source from linked conversations
        self.enrich_memories_with_source(uid, &mut memories).await;

        Ok(memories)
    }

    pub(super) fn parse_memory_query_results(
        &self,
        uid: &str,
        results: Vec<Value>,
        include_dismissed: bool,
        include_invalidated: bool,
        tags: Option<&[String]>,
    ) -> Vec<MemoryDB> {
        results
            .into_iter()
            .filter_map(|doc| {
                doc.get("document")
                    .and_then(|d| self.parse_memory(d, uid).ok())
            })
            // Match Python: Firestore limit/offset already applied, then rejected/invalidated docs are filtered.
            .filter(|m| {
                memory_passes_default_filters(m, include_dismissed, include_invalidated, tags)
            })
            .collect()
    }

    /// Get memories for a user (simple version for backward compatibility)
    /// Copied from Python get_memories
    /// Enriches memories with source from linked conversations
    pub async fn get_memories(
        &self,
        uid: &str,
        limit: usize,
    ) -> Result<Vec<MemoryDB>, Box<dyn std::error::Error + Send + Sync>> {
        self.get_memories_filtered(uid, limit, 0, None, None, None, None, false, false)
            .await
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
                    let source_str = conversation_source_wire(&conv.source);
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

        tracing::info!(
            "Reviewed memory {} for user {} with value {}",
            memory_id,
            uid,
            value
        );
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

        let category_str = memory_category_wire(&actual_category);

        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            MEMORIES_SUBCOLLECTION,
            memory_id
        );

        let mut fields = build_create_memory_fields(
            &memory_id,
            uid,
            content,
            visibility,
            &actual_category,
            is_manual,
            &scoring,
            now,
            tags,
        );

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

        tracing::info!(
            "Created memory {} for user {} (category: {})",
            memory_id,
            uid,
            category_str
        );
        Ok(memory_id)
    }

    /// Create a manual memory (convenience wrapper)
    pub async fn create_manual_memory(
        &self,
        uid: &str,
        content: &str,
        visibility: &str,
    ) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
        self.create_memory(
            uid,
            content,
            visibility,
            None,
            None,
            None,
            None,
            &[],
            None,
            None,
            None,
            None,
        )
        .await
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
        let memory_ids: Vec<String> = self
            .fetch_all_memory_documents(uid)
            .await?
            .iter()
            .filter_map(|doc| {
                let fields = doc.get("fields")?;
                let is_read = fields
                    .get("is_read")
                    .and_then(|v| v.get("booleanValue"))
                    .and_then(|v| v.as_bool())
                    .unwrap_or(false);
                if is_read {
                    return None;
                }
                doc.get("name")
                    .and_then(|n| n.as_str())
                    .map(Self::document_id_from_name)
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

            let response = self
                .build_request(reqwest::Method::PATCH, &url)
                .await?
                .json(&doc)
                .send()
                .await?;
            if !response.status().is_success() {
                let error_text = response.text().await?;
                return Err(format!("Firestore memory update error: {}", error_text).into());
            }
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
        let memory_ids: Vec<String> = self
            .fetch_all_memory_documents(uid)
            .await?
            .iter()
            .filter_map(|doc| {
                doc.get("name")
                    .and_then(|n| n.as_str())
                    .map(Self::document_id_from_name)
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

            let response = self
                .build_request(reqwest::Method::PATCH, &url)
                .await?
                .json(&doc)
                .send()
                .await?;
            if !response.status().is_success() {
                let error_text = response.text().await?;
                return Err(format!("Firestore memory update error: {}", error_text).into());
            }
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
        let memory_ids: Vec<String> = self
            .fetch_all_memory_documents(uid)
            .await?
            .iter()
            .filter_map(|doc| {
                doc.get("name")
                    .and_then(|n| n.as_str())
                    .map(Self::document_id_from_name)
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

            let response = self
                .build_request(reqwest::Method::DELETE, &url)
                .await?
                .send()
                .await?;
            if !response.status().is_success()
                && response.status() != reqwest::StatusCode::NOT_FOUND
            {
                let error_text = response.text().await?;
                return Err(format!("Firestore memory delete error: {}", error_text).into());
            }
        }

        tracing::info!("Deleted {} memories for user {}", count, uid);
        Ok(count)
    }

    async fn fetch_all_memory_documents(
        &self,
        uid: &str,
    ) -> Result<Vec<Value>, Box<dyn std::error::Error + Send + Sync>> {
        let parent = format!("{}/{}/{}", self.base_url(), USERS_COLLECTION, uid);
        let mut documents = Vec::new();
        let mut offset = 0usize;
        let limit = 500usize;

        loop {
            let query = json!({
                "structuredQuery": {
                    "from": [{"collectionId": MEMORIES_SUBCOLLECTION}],
                    "limit": limit,
                    "offset": offset
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
            let batch: Vec<Value> = results
                .into_iter()
                .filter_map(|doc| doc.get("document").cloned())
                .collect();
            let fetched_count = batch.len();
            documents.extend(batch);

            if fetched_count < limit {
                break;
            }
            offset += fetched_count;
        }

        Ok(documents)
    }

    fn document_id_from_name(name: &str) -> String {
        name.split('/').last().unwrap_or("").to_string()
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
                "fields": build_save_memory_fields(
                    &memory_id,
                    uid,
                    conversation_id,
                    memory,
                    &scoring,
                    now,
                )
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
}
