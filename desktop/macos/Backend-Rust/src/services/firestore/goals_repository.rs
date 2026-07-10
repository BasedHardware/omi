use super::*;

impl FirestoreService {
    pub async fn get_user_goals(
        &self,
        uid: &str,
        limit: usize,
    ) -> Result<Vec<GoalDB>, Box<dyn std::error::Error + Send + Sync>> {
        // Query the user's goals subcollection directly
        let url = format!("{}/{}/{}:runQuery", self.base_url(), USERS_COLLECTION, uid);

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
                tracing::info!(
                    "Deactivating oldest goal {} to make room for new goal",
                    oldest.id
                );
                self.update_goal(
                    uid,
                    &oldest.id,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    Some(false),
                    None,
                )
                .await?;
            }
        }

        // Generate a unique ID
        let now = Utc::now();
        let goal_id =
            document_id_from_seed(&format!("{}-{}-{}", uid, title, now.timestamp_millis()));

        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            GOALS_SUBCOLLECTION,
            goal_id
        );

        let mut fields = json!({
            "id": {"stringValue": &goal_id},
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
            fields["description"] = json!({"stringValue": d});
        }

        if let Some(u) = unit {
            fields["unit"] = json!({"stringValue": u});
        }

        if let Some(s) = source {
            fields["source"] = json!({"stringValue": s});
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
            fields.insert(
                "completed_at".to_string(),
                json!({"timestampValue": cat.to_rfc3339()}),
            );
        }

        // Always update updated_at
        update_fields.push("updated_at");
        fields.insert(
            "updated_at".to_string(),
            json!({"timestampValue": now.to_rfc3339()}),
        );

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
        let goal = self
            .get_goal(uid, goal_id)
            .await?
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
        let goal = self
            .update_goal(
                uid,
                goal_id,
                None,
                None,
                None,
                Some(current_value),
                None,
                None,
                None,
                None,
                None,
            )
            .await?;

        // Also save history entry (inline, fast write)
        if let Err(e) = self
            .save_goal_progress_history(uid, goal_id, current_value)
            .await
        {
            tracing::warn!("Failed to save goal progress history: {}", e);
        }

        // Auto-complete if current_value >= target_value
        if current_value >= goal.target_value && goal.completed_at.is_none() {
            tracing::info!(
                "Goal {} completed! current_value={} >= target_value={}",
                goal_id,
                current_value,
                goal.target_value
            );
            let completed_goal = self
                .update_goal(
                    uid,
                    goal_id,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    Some(false),
                    Some(Utc::now()),
                )
                .await?;
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
        let url = format!("{}/{}/{}:runQuery", self.base_url(), USERS_COLLECTION, uid);

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

        tracing::debug!(
            "Saved goal history for {}/{}: {} on {}",
            uid,
            goal_id,
            value,
            date_key
        );
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
                    let recorded_at = self
                        .parse_timestamp_optional(fields, "recorded_at")
                        .unwrap_or_else(Utc::now);
                    history.push(GoalHistoryEntry {
                        date,
                        value,
                        recorded_at,
                    });
                }
            }
        }

        tracing::info!(
            "Found {} history entries for goal {}",
            history.len(),
            goal_id
        );
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

        tracing::info!(
            "Daily score for user {}: {}/{} tasks completed",
            uid,
            completed,
            total
        );
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

        tracing::info!(
            "Weekly score for user {}: {}/{} tasks completed",
            uid,
            completed,
            total
        );
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

        tracing::info!(
            "Overall score for user {}: {}/{} tasks completed",
            uid,
            completed,
            total
        );
        Ok((completed, total))
    }

    /// Parse a goal from Firestore document
    fn parse_goal(&self, doc: &Value) -> Result<GoalDB, Box<dyn std::error::Error + Send + Sync>> {
        let fields = doc.get("fields").ok_or("Missing fields")?;
        let name_path = doc.get("name").and_then(|n| n.as_str()).unwrap_or("");
        let id = name_path.split('/').last().unwrap_or("").to_string();

        let goal_type_str = self
            .parse_string(fields, "goal_type")
            .unwrap_or_else(|| "boolean".to_string());
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
            created_at: self
                .parse_timestamp_optional(fields, "created_at")
                .unwrap_or_else(Utc::now),
            updated_at: self
                .parse_timestamp_optional(fields, "updated_at")
                .unwrap_or_else(Utc::now),
            completed_at: {
                if fields.get("completed_at").is_some() {
                    Some(
                        self.parse_timestamp_optional(fields, "completed_at")
                            .unwrap_or_else(Utc::now),
                    )
                } else {
                    None
                }
            },
            source: self.parse_string(fields, "source"),
        })
    }

    /// Parse double value from Firestore fields
    fn parse_double(&self, fields: &Value, key: &str) -> Option<f64> {
        fields.get(key).and_then(|v| {
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
}
