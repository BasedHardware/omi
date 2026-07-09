use super::*;

impl FirestoreService {
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
            return Err(format!("Firestore query error: {}", error_text).into());
        }

        let results: Vec<Value> = response.json().await?;
        let advice_list = results
            .into_iter()
            .filter_map(|doc| doc.get("document").and_then(|d| self.parse_advice(d).ok()))
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
            self.update_advice(uid, &advice.id, Some(true), None)
                .await?;
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

        let category_str = self
            .parse_string(fields, "category")
            .unwrap_or_else(|| "other".to_string());
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
            created_at: self
                .parse_timestamp_optional(fields, "created_at")
                .unwrap_or_else(Utc::now),
            updated_at: self.parse_timestamp_optional(fields, "updated_at"),
            is_read: self.parse_bool(fields, "is_read").unwrap_or(false),
            is_dismissed: self.parse_bool(fields, "is_dismissed").unwrap_or(false),
        })
    }
}
