use super::*;

impl FirestoreService {
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
            filters.into_iter().next()
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
                tracing::error!("Firestore query error for memories: {}", error_text);
                return Err(format!("Firestore query error: {}", error_text).into());
            }

            let results: Vec<Value> = response.json().await?;
            let fetched_count = results
                .iter()
                .filter(|doc| doc.get("document").is_some())
                .count();

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
                .filter(|m| match tags {
                    Some(filter_tags) if filter_tags.len() > 1 => {
                        filter_tags[1..].iter().all(|tag| m.tags.contains(tag))
                    }
                    _ => true,
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
        self.get_memories_filtered(uid, limit, 0, None, None, false)
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
        let tags_values: Vec<Value> = tags.iter().map(|t| json!({"stringValue": t})).collect();

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
}
