use super::*;

impl FirestoreService {
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
        let end = offset.saturating_add(limit).min(apps.len());
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
        let end = offset.saturating_add(limit).min(apps.len());
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
        let document = format!("{}/{}/{}", self.base_url(), APPS_COLLECTION, app_id);
        let commit_url = format!(
            "https://firestore.googleapis.com/v1/projects/{}/databases/(default)/documents:commit",
            self.project_id
        );
        let body = json!({
            "writes": [{
                "transform": {
                    "document": document,
                    "fieldTransforms": [{
                        "fieldPath": "installs",
                        "increment": {"integerValue": "1"}
                    }]
                },
                "currentDocument": {"exists": true}
            }]
        });

        let response = self
            .build_request(reqwest::Method::POST, &commit_url)
            .await?
            .json(&body)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Failed to increment app installs: {}", error_text).into());
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
    fn parse_app(&self, doc: &Value) -> Result<App, Box<dyn std::error::Error + Send + Sync>> {
        let fields = doc.get("fields").ok_or("Missing fields in document")?;
        let name = doc.get("name").and_then(|n| n.as_str()).unwrap_or("");
        let id = name.split('/').last().unwrap_or("").to_string();

        Ok(App {
            id,
            name: self.parse_string(fields, "name").unwrap_or_default(),
            description: self.parse_string(fields, "description").unwrap_or_default(),
            image: self.parse_string(fields, "image").unwrap_or_default(),
            category: self
                .parse_string(fields, "category")
                .unwrap_or_else(|| "other".to_string()),
            author: self.parse_string(fields, "author").unwrap_or_default(),
            email: self.parse_string(fields, "email"),
            capabilities: self.parse_string_array(fields, "capabilities"),
            uid: self.parse_string(fields, "uid"),
            approved: self.parse_bool(fields, "approved").unwrap_or(false),
            private: self.parse_bool(fields, "private").unwrap_or(false),
            status: self
                .parse_string(fields, "status")
                .unwrap_or_else(|| "under-review".to_string()),
            chat_prompt: self.parse_string(fields, "chat_prompt"),
            memory_prompt: self.parse_string(fields, "memory_prompt"),
            persona_prompt: self.parse_string(fields, "persona_prompt"),
            external_integration: None,   // TODO: Parse nested object
            proactive_notification: None, // TODO: Parse nested object
            chat_tools: vec![],           // TODO: Parse array of nested objects
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
            category: self
                .parse_string(fields, "category")
                .unwrap_or_else(|| "other".to_string()),
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
            rated_at: self
                .parse_timestamp_optional(fields, "rated_at")
                .unwrap_or_else(Utc::now),
            edited_at: self.parse_timestamp_optional(fields, "edited_at"),
        })
    }
}
