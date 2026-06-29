use super::*;

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
    ) -> Result<Vec<MemoryDB>, Box<dyn std::error::Error + Send + Sync>> {
        let parent = format!("{}/{}/{}", self.base_url(), USERS_COLLECTION, uid);

        let query = json!({
            "structuredQuery": {
                "from": [{"collectionId": MEMORIES_SUBCOLLECTION}],
                "where": {
                    "fieldFilter": {
                        "field": {"fieldPath": "visibility"},
                        "op": "EQUAL",
                        "value": {"stringValue": "public"}
                    }
                },
                "orderBy": [{"field": {"fieldPath": "created_at"}, "direction": "DESCENDING"}],
                "limit": limit
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
        let memories: Vec<MemoryDB> = results
            .into_iter()
            .filter_map(|doc| {
                doc.get("document")
                    .and_then(|d| self.parse_memory(d, uid).ok())
            })
            .collect();

        tracing::info!("Found {} public memories for user {}", memories.len(), uid);
        Ok(memories)
    }

    /// Count public memories for a user
    pub async fn count_public_memories(
        &self,
        uid: &str,
    ) -> Result<i32, Box<dyn std::error::Error + Send + Sync>> {
        let memories = self.get_public_memories(uid, 1000).await?;
        Ok(memories.len() as i32)
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
