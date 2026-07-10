use super::values::memory_is_public;
use super::*;

pub(super) fn build_public_memories_query(limit: usize, offset: usize) -> Value {
    json!({
        "structuredQuery": {
            "from": [{"collectionId": MEMORIES_SUBCOLLECTION}],
            "orderBy": [
                {"field": {"fieldPath": "scoring"}, "direction": "DESCENDING"},
                {"field": {"fieldPath": "created_at"}, "direction": "DESCENDING"}
            ],
            "limit": limit,
            "offset": offset
        }
    })
}

pub(super) fn memory_counts_as_public(memory: &MemoryDB) -> bool {
    memory_is_public(memory)
}

impl FirestoreService {
    pub async fn get_user_persona(
        &self,
        uid: &str,
    ) -> Result<Option<PersonaDB>, Box<dyn std::error::Error + Send + Sync>> {
        let parent = self.base_url();

        // Query for persona with matching uid and persona capability
        let query = json!({
            "structuredQuery": {
                "from": [{"collectionId": APPS_COLLECTION}],
                "where": {
                    "compositeFilter": {
                        "op": "AND",
                        "filters": [
                            {
                                "fieldFilter": {
                                    "field": {"fieldPath": "uid"},
                                    "op": "EQUAL",
                                    "value": {"stringValue": uid}
                                }
                            },
                            {
                                "fieldFilter": {
                                    "field": {"fieldPath": "capabilities"},
                                    "op": "ARRAY_CONTAINS",
                                    "value": {"stringValue": "persona"}
                                }
                            }
                        ]
                    }
                },
                "limit": 1
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
            return Ok(None);
        }

        let results: Vec<Value> = response.json().await?;

        // Return first matching persona
        for result in results {
            if let Some(doc) = result.get("document") {
                return Ok(Some(self.parse_persona(doc)?));
            }
        }

        Ok(None)
    }

    /// Create a new persona for user
    pub async fn create_persona(
        &self,
        uid: &str,
        name: &str,
        username: Option<&str>,
        description: &str,
        persona_prompt: Option<&str>,
        author: &str,
        email: Option<&str>,
    ) -> Result<PersonaDB, Box<dyn std::error::Error + Send + Sync>> {
        // Generate ULID-style ID
        let persona_id = ulid::Ulid::new().to_string();
        let now = Utc::now();

        let url = format!("{}/{}/{}", self.base_url(), APPS_COLLECTION, persona_id);

        let mut fields = json!({
            "id": {"stringValue": &persona_id},
            "uid": {"stringValue": uid},
            "name": {"stringValue": name},
            "description": {"stringValue": description},
            "image": {"stringValue": ""},
            "category": {"stringValue": "personality-emulation"},
            "capabilities": {"arrayValue": {"values": [{"stringValue": "persona"}]}},
            "approved": {"booleanValue": false},
            "status": {"stringValue": "under-review"},
            "private": {"booleanValue": false},
            "author": {"stringValue": author},
            "created_at": {"timestampValue": now.to_rfc3339()},
            "updated_at": {"timestampValue": now.to_rfc3339()}
        });

        if let Some(uname) = username {
            fields["username"] = json!({"stringValue": uname});
        }
        if let Some(prompt) = persona_prompt {
            fields["persona_prompt"] = json!({"stringValue": prompt});
        }
        if let Some(e) = email {
            fields["email"] = json!({"stringValue": e});
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

        tracing::info!("Created persona {} for user {}", persona_id, uid);

        Ok(PersonaDB {
            id: persona_id,
            uid: uid.to_string(),
            name: name.to_string(),
            username: username.map(|s| s.to_string()),
            description: description.to_string(),
            image: String::new(),
            category: "personality-emulation".to_string(),
            capabilities: vec!["persona".to_string()],
            persona_prompt: persona_prompt.map(|s| s.to_string()),
            approved: false,
            status: "under-review".to_string(),
            is_private: false,
            author: author.to_string(),
            email: email.map(|s| s.to_string()),
            created_at: now,
            updated_at: now,
        })
    }

    /// Update an existing persona
    pub async fn update_persona(
        &self,
        persona_id: &str,
        name: Option<&str>,
        description: Option<&str>,
        persona_prompt: Option<&str>,
        image: Option<&str>,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let now = Utc::now();
        let mut update_fields = vec!["updated_at"];
        let mut fields = json!({
            "updated_at": {"timestampValue": now.to_rfc3339()}
        });

        if let Some(n) = name {
            fields["name"] = json!({"stringValue": n});
            update_fields.push("name");
        }
        if let Some(d) = description {
            fields["description"] = json!({"stringValue": d});
            update_fields.push("description");
        }
        if let Some(p) = persona_prompt {
            fields["persona_prompt"] = json!({"stringValue": p});
            update_fields.push("persona_prompt");
        }
        if let Some(i) = image {
            fields["image"] = json!({"stringValue": i});
            update_fields.push("image");
        }

        let update_mask = update_fields
            .iter()
            .map(|f| format!("updateMask.fieldPaths={}", f))
            .collect::<Vec<_>>()
            .join("&");

        let url = format!(
            "{}/{}/{}?{}",
            self.base_url(),
            APPS_COLLECTION,
            persona_id,
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

        tracing::info!("Updated persona {}", persona_id);
        Ok(())
    }

    /// Delete a persona
    pub async fn delete_persona(
        &self,
        persona_id: &str,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let url = format!("{}/{}/{}", self.base_url(), APPS_COLLECTION, persona_id);

        let response = self
            .build_request(reqwest::Method::DELETE, &url)
            .await?
            .send()
            .await?;

        if !response.status().is_success() && response.status() != reqwest::StatusCode::NOT_FOUND {
            let error_text = response.text().await?;
            return Err(format!("Firestore delete error: {}", error_text).into());
        }

        tracing::info!("Deleted persona {}", persona_id);
        Ok(())
    }

    /// Check if a username is available
    pub async fn is_username_available(
        &self,
        username: &str,
    ) -> Result<bool, Box<dyn std::error::Error + Send + Sync>> {
        let parent = self.base_url();

        let query = json!({
            "structuredQuery": {
                "from": [{"collectionId": APPS_COLLECTION}],
                "where": {
                    "fieldFilter": {
                        "field": {"fieldPath": "username"},
                        "op": "EQUAL",
                        "value": {"stringValue": username}
                    }
                },
                "limit": 1
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
            return Ok(false);
        }

        let results: Vec<Value> = response.json().await?;

        // Username is available if no documents found
        let has_document = results.iter().any(|r| r.get("document").is_some());
        Ok(!has_document)
    }

    /// Get public memories for a user (for persona generation)
    pub async fn get_public_memories(
        &self,
        uid: &str,
        limit: usize,
        offset: usize,
    ) -> Result<Vec<MemoryDB>, Box<dyn std::error::Error + Send + Sync>> {
        let parent = format!("{}/{}/{}", self.base_url(), USERS_COLLECTION, uid);

        let query = build_public_memories_query(limit, offset);

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
        let memories = self.parse_public_memory_query_results(uid, results);

        tracing::info!("Found {} public memories for user {}", memories.len(), uid);
        Ok(memories)
    }

    /// Count public memories for a user
    pub async fn count_public_memories(
        &self,
        uid: &str,
    ) -> Result<i32, Box<dyn std::error::Error + Send + Sync>> {
        let parent = format!("{}/{}/{}", self.base_url(), USERS_COLLECTION, uid);
        let mut count = 0i32;
        let mut offset = 0usize;
        let limit = 500usize;

        loop {
            let query = build_public_memories_query(limit, offset);

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
            let fetched_count = results
                .iter()
                .filter(|doc| doc.get("document").is_some())
                .count();
            count += results
                .iter()
                .filter_map(|doc| {
                    doc.get("document")
                        .and_then(|d| self.parse_memory(d, uid).ok())
                })
                .filter(memory_counts_as_public)
                .count() as i32;
            if fetched_count < limit {
                break;
            }
            offset += fetched_count;
        }

        Ok(count)
    }

    pub(super) fn parse_public_memory_query_results(
        &self,
        uid: &str,
        results: Vec<Value>,
    ) -> Vec<MemoryDB> {
        results
            .into_iter()
            .filter_map(|doc| {
                doc.get("document")
                    .and_then(|d| self.parse_memory(d, uid).ok())
            })
            // Match Python get_user_public_memories: Firestore limit/offset first, then only visibility filter.
            .filter(memory_counts_as_public)
            .collect()
    }

    /// Parse a persona from Firestore document
    fn parse_persona(
        &self,
        doc: &Value,
    ) -> Result<PersonaDB, Box<dyn std::error::Error + Send + Sync>> {
        let fields = doc.get("fields").ok_or("Missing fields")?;
        let name_path = doc.get("name").and_then(|n| n.as_str()).unwrap_or("");
        let id = name_path.split('/').last().unwrap_or("").to_string();

        let capabilities = {
            let caps = self.parse_string_array(fields, "capabilities");
            if caps.is_empty() {
                vec!["persona".to_string()]
            } else {
                caps
            }
        };

        Ok(PersonaDB {
            id,
            uid: self.parse_string(fields, "uid").unwrap_or_default(),
            name: self.parse_string(fields, "name").unwrap_or_default(),
            username: self.parse_string(fields, "username"),
            description: self.parse_string(fields, "description").unwrap_or_default(),
            image: self.parse_string(fields, "image").unwrap_or_default(),
            category: self
                .parse_string(fields, "category")
                .unwrap_or_else(|| "personality-emulation".to_string()),
            capabilities,
            persona_prompt: self.parse_string(fields, "persona_prompt"),
            approved: self.parse_bool(fields, "approved").unwrap_or(false),
            status: self
                .parse_string(fields, "status")
                .unwrap_or_else(|| "under-review".to_string()),
            is_private: self.parse_bool(fields, "private").unwrap_or(false),
            author: self.parse_string(fields, "author").unwrap_or_default(),
            email: self.parse_string(fields, "email"),
            created_at: self
                .parse_timestamp_optional(fields, "created_at")
                .unwrap_or_else(Utc::now),
            updated_at: self
                .parse_timestamp_optional(fields, "updated_at")
                .unwrap_or_else(Utc::now),
        })
    }
}

#[cfg(test)]
#[allow(clippy::unwrap_used)]
mod contract_tests {
    use super::*;
    use chrono::TimeZone;

    fn memory(
        id: &str,
        visibility: &str,
        invalidated: bool,
        user_review: Option<bool>,
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
            visibility: visibility.to_string(),
            manually_added: false,
            scoring: None,
            source: None,
            input_device_name: None,
            confidence: None,
            source_app: None,
            context_summary: None,
            is_read: false,
            is_dismissed: false,
            tags: vec![],
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

    fn memory_doc(
        id: &str,
        visibility: Option<&str>,
        invalidated: bool,
        user_review: Option<bool>,
    ) -> Value {
        let created_at = "2026-01-02T03:04:05+00:00";
        let mut fields = json!({
            "content": {"stringValue": id},
            "category": {"stringValue": "system"},
            "created_at": {"timestampValue": created_at},
            "updated_at": {"timestampValue": created_at}
        });
        if let Some(visibility) = visibility {
            fields["visibility"] = json!({"stringValue": visibility});
        }
        if let Some(review) = user_review {
            fields["user_review"] = json!({"booleanValue": review});
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
    fn contract_public_memory_query_does_not_filter_missing_visibility_in_firestore() {
        let query = build_public_memories_query(100, 20);
        let structured = &query["structuredQuery"];

        assert!(structured.get("where").is_none());
        assert_eq!(structured["orderBy"][0]["field"]["fieldPath"], "scoring");
        assert_eq!(structured["orderBy"][1]["field"]["fieldPath"], "created_at");
        assert_eq!(structured["limit"], 100);
        assert_eq!(structured["offset"], 20);
    }

    #[test]
    fn contract_public_memory_filter_matches_python_visibility_only() {
        assert!(memory_counts_as_public(&memory(
            "public", "public", false, None
        )));
        assert!(!memory_counts_as_public(&memory(
            "private", "private", false, None
        )));
        assert!(memory_counts_as_public(&memory(
            "rejected",
            "public",
            false,
            Some(false)
        )));
        assert!(memory_counts_as_public(&memory(
            "invalidated",
            "public",
            true,
            None
        )));

        let service = FirestoreService::new_for_contract(None);
        let query = build_public_memories_query(3, 2);
        assert_eq!(query["structuredQuery"]["limit"], 3);
        assert_eq!(query["structuredQuery"]["offset"], 2);

        let parsed = service.parse_public_memory_query_results(
            "contract-user-8547",
            vec![
                memory_doc("missing-visibility", None, false, None),
                memory_doc("private", Some("private"), false, None),
                memory_doc("rejected", Some("public"), false, Some(false)),
                memory_doc("invalidated", Some("public"), true, None),
            ],
        );

        assert_eq!(
            parsed
                .iter()
                .map(|memory| memory.id.as_str())
                .collect::<Vec<_>>(),
            vec!["missing-visibility", "rejected", "invalidated"]
        );
    }
}
