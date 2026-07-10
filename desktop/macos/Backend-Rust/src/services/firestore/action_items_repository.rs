use super::*;

impl FirestoreService {
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
            filters.into_iter().next()
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
                tracing::error!("Firestore query error for action_items: {}", error_text);
                return Err(format!("Firestore query error: {}", error_text).into());
            }

            let results: Vec<Value> = response.json().await?;
            let fetched_count = results
                .iter()
                .filter(|doc| doc.get("document").is_some())
                .count();

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
        self.enrich_action_items_with_source(uid, &mut action_items)
            .await;

        // Post-query sort matching Python backend behavior (used by iOS/Flutter app):
        // 1. Items WITH due_at come first (sorted by due_at ascending)
        // 2. Items WITHOUT due_at come last
        // 3. Tie-breaker: created_at descending (newest first)
        action_items.sort_by(|a, b| match (&a.due_at, &b.due_at) {
            (Some(due_a), Some(due_b)) => due_a
                .cmp(due_b)
                .then_with(|| b.created_at.cmp(&a.created_at)),
            (Some(_), None) => std::cmp::Ordering::Less,
            (None, Some(_)) => std::cmp::Ordering::Greater,
            (None, None) => b.created_at.cmp(&a.created_at),
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
                    action_item.source =
                        Some(format!("transcription:{:?}", conv.source).to_lowercase());
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
        clear_due_at: bool,
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

        if clear_due_at {
            field_paths.push("due_at");
            fields["due_at"] = json!({"nullValue": null});
        } else if let Some(due) = due_at {
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
                    action_item.source =
                        Some(format!("transcription:{:?}", conv.source).to_lowercase());
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
            "deleted",
            "deleted_by",
            "deleted_at",
            "deleted_reason",
            "kept_task_id",
            "updated_at",
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

        tracing::info!(
            "Soft-deleted action item {} for user {} (by: {}, reason: {})",
            item_id,
            uid,
            deleted_by,
            reason
        );
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
                        },
                        "currentDocument": {
                            "exists": true
                        }
                    })
                })
                .collect();

            // Use batchWrite (not commit) so deleted-doc failures don't block other updates
            let batch_url = format!(
                "https://firestore.googleapis.com/v1/projects/{}/databases/(default)/documents:batchWrite",
                self.project_id
            );

            let body = json!({ "writes": writes });

            let response = self
                .build_request(reqwest::Method::POST, &batch_url)
                .await?
                .json(&body)
                .send()
                .await?;

            if !response.status().is_success() {
                let error_text = response.text().await?;
                return Err(format!("Firestore batchWrite error: {}", error_text).into());
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
                        },
                        "currentDocument": {
                            "exists": true
                        }
                    })
                })
                .collect();

            // Use batchWrite (not commit) so deleted-doc failures don't block other updates
            let batch_url = format!(
                "https://firestore.googleapis.com/v1/projects/{}/databases/(default)/documents:batchWrite",
                self.project_id
            );

            let body = json!({ "writes": writes });

            let response = self
                .build_request(reqwest::Method::POST, &batch_url)
                .await?
                .json(&body)
                .send()
                .await?;

            if !response.status().is_success() {
                let error_text = response.text().await?;
                return Err(format!("Firestore batchWrite error: {}", error_text).into());
            }
        }

        tracing::info!("Batch updated {} sort orders for user {}", items.len(), uid);
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
        if existing
            .iter()
            .any(|t| t.description.trim().to_lowercase() == desc_lower)
        {
            let preview: String = description.chars().take(80).collect();
            tracing::info!(
                "Skipping duplicate staged task for user {}: {}",
                uid,
                preview
            );
            // Return the existing item instead of creating a duplicate
            if let Some(existing_item) = existing
                .into_iter()
                .find(|t| t.description.trim().to_lowercase() == desc_lower)
            {
                return Ok(existing_item);
            }
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
            .get_action_items(
                uid,
                10000,
                0,
                Some(false),
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            )
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
        let filters = vec![json!({
            "fieldFilter": {
                "field": {"fieldPath": "completed"},
                "op": "EQUAL",
                "value": {"booleanValue": false}
            }
        })];

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
                "limit": limit.saturating_add(offset)
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
                return Err(
                    format!("Firestore batch commit staged scores error: {}", error_text).into(),
                );
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
        let mut count = 0usize;
        let mut offset = 0usize;
        let limit = 500usize;
        loop {
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
                    "limit": limit,
                    "offset": offset
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
            let docs: Vec<&Value> = results.iter().filter_map(|r| r.get("document")).collect();
            let fetched_count = docs.len();
            count += docs
                .into_iter()
                .filter_map(|doc| self.parse_action_item(doc).ok())
                .filter(|item| item.deleted != Some(true) && item.from_staged == Some(true))
                .count();

            if fetched_count < limit {
                break;
            }
            offset += fetched_count;
        }

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
            .filter(|item| item.deleted != Some(true) && item.from_staged == Some(true))
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
}
