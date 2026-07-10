use super::*;

impl FirestoreService {
    pub async fn create_focus_session(
        &self,
        uid: &str,
        status: &FocusStatus,
        app_or_site: &str,
        description: &str,
        message: Option<&str>,
    ) -> Result<FocusSessionDB, Box<dyn std::error::Error + Send + Sync>> {
        let session_id = uuid::Uuid::new_v4().to_string();
        let now = Utc::now();

        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            FOCUS_SESSIONS_SUBCOLLECTION,
            session_id
        );

        let status_str = match status {
            FocusStatus::Focused => "focused",
            FocusStatus::Distracted => "distracted",
        };

        let mut fields = json!({
            "status": {"stringValue": status_str},
            "app_or_site": {"stringValue": app_or_site},
            "description": {"stringValue": description},
            "created_at": {"timestampValue": now.to_rfc3339()}
        });

        if let Some(msg) = message {
            fields["message"] = json!({"stringValue": msg});
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

        tracing::info!(
            "Created focus session {} for user {} with status={}",
            session_id,
            uid,
            status_str
        );

        Ok(FocusSessionDB {
            id: session_id,
            status: status.clone(),
            app_or_site: app_or_site.to_string(),
            description: description.to_string(),
            message: message.map(|s| s.to_string()),
            created_at: now,
            duration_seconds: None,
        })
    }

    /// Get focus sessions for a user
    /// Path: users/{uid}/focus_sessions
    pub async fn get_focus_sessions(
        &self,
        uid: &str,
        limit: usize,
        offset: usize,
        date_filter: Option<&str>,
    ) -> Result<Vec<FocusSessionDB>, Box<dyn std::error::Error + Send + Sync>> {
        let parent = format!("{}/{}/{}", self.base_url(), USERS_COLLECTION, uid);

        // Build filters
        let mut filters: Vec<Value> = Vec::new();

        // If date filter provided, filter by date range
        if let Some(date) = date_filter {
            // Parse date and create start/end timestamps
            if let Ok(parsed_date) = chrono::NaiveDate::parse_from_str(date, "%Y-%m-%d") {
                if let (Some(start), Some(end)) = (
                    parsed_date.and_hms_opt(0, 0, 0).map(|dt| dt.and_utc()),
                    parsed_date.and_hms_opt(23, 59, 59).map(|dt| dt.and_utc()),
                ) {
                    filters.push(json!({
                        "fieldFilter": {
                            "field": {"fieldPath": "created_at"},
                            "op": "GREATER_THAN_OR_EQUAL",
                            "value": {"timestampValue": start.to_rfc3339()}
                        }
                    }));
                    filters.push(json!({
                        "fieldFilter": {
                            "field": {"fieldPath": "created_at"},
                            "op": "LESS_THAN_OR_EQUAL",
                            "value": {"timestampValue": end.to_rfc3339()}
                        }
                    }));
                }
            }
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
            "from": [{"collectionId": FOCUS_SESSIONS_SUBCOLLECTION}],
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
                    .and_then(|d| self.parse_focus_session(d).ok())
            })
            .collect();

        Ok(sessions)
    }

    /// Delete a focus session
    pub async fn delete_focus_session(
        &self,
        uid: &str,
        session_id: &str,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            FOCUS_SESSIONS_SUBCOLLECTION,
            session_id
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

        tracing::info!("Deleted focus session {} for user {}", session_id, uid);
        Ok(())
    }

    /// Get focus statistics for a date
    pub async fn get_focus_stats(
        &self,
        uid: &str,
        date: &str,
    ) -> Result<FocusStats, Box<dyn std::error::Error + Send + Sync>> {
        // Get all sessions for the date
        let sessions = self.get_focus_sessions(uid, 1000, 0, Some(date)).await?;

        let mut focused_count: i64 = 0;
        let mut distracted_count: i64 = 0;
        let mut distraction_map: std::collections::HashMap<String, (i64, i64)> =
            std::collections::HashMap::new();

        for session in &sessions {
            match session.status {
                FocusStatus::Focused => focused_count += 1,
                FocusStatus::Distracted => {
                    distracted_count += 1;
                    let entry = distraction_map
                        .entry(session.app_or_site.clone())
                        .or_insert((0, 0));
                    entry.0 += session.duration_seconds.unwrap_or(60); // Default 60s per session
                    entry.1 += 1;
                }
            }
        }

        // Build top distractions
        let mut top_distractions: Vec<DistractionEntry> = distraction_map
            .into_iter()
            .map(|(app, (secs, count))| DistractionEntry {
                app_or_site: app,
                total_seconds: secs,
                count,
            })
            .collect();

        // Sort by total time descending
        top_distractions.sort_by(|a, b| b.total_seconds.cmp(&a.total_seconds));

        // Take top 5
        top_distractions.truncate(5);

        // Estimate minutes (each session ~1 minute if no duration)
        let focused_minutes = focused_count;
        let distracted_minutes = distracted_count;

        Ok(FocusStats {
            date: date.to_string(),
            focused_minutes,
            distracted_minutes,
            session_count: sessions.len() as i64,
            focused_count,
            distracted_count,
            top_distractions,
        })
    }

    /// Parse a focus session from Firestore document
    fn parse_focus_session(
        &self,
        doc: &Value,
    ) -> Result<FocusSessionDB, Box<dyn std::error::Error + Send + Sync>> {
        let name = doc
            .get("name")
            .and_then(|n| n.as_str())
            .ok_or("Missing document name")?;

        let id = name.split('/').last().unwrap_or("unknown").to_string();

        let fields = doc.get("fields").ok_or("Missing fields")?;

        let status_str = self.parse_string(fields, "status").unwrap_or_default();
        let status = match status_str.as_str() {
            "focused" => FocusStatus::Focused,
            _ => FocusStatus::Distracted,
        };

        Ok(FocusSessionDB {
            id,
            status,
            app_or_site: self.parse_string(fields, "app_or_site").unwrap_or_default(),
            description: self.parse_string(fields, "description").unwrap_or_default(),
            message: self.parse_string(fields, "message"),
            created_at: self
                .parse_timestamp_optional(fields, "created_at")
                .unwrap_or_else(Utc::now),
            duration_seconds: self.parse_int(fields, "duration_seconds").map(|v| v as i64),
        })
    }
}
