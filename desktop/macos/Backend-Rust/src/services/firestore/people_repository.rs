use super::*;

impl FirestoreService {
    pub async fn get_people(
        &self,
        uid: &str,
    ) -> Result<Vec<crate::models::Person>, Box<dyn std::error::Error + Send + Sync>> {
        let parent = format!("{}/{}/{}", self.base_url(), USERS_COLLECTION, uid);

        let structured_query = json!({
            "from": [{"collectionId": PEOPLE_SUBCOLLECTION}],
            "orderBy": [{"field": {"fieldPath": "name"}, "direction": "ASCENDING"}]
        });

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
            tracing::error!("Firestore query error for people: {}", error_text);
            return Ok(vec![]);
        }

        let results: Vec<Value> = response.json().await?;
        let people = results
            .into_iter()
            .filter_map(|doc| doc.get("document").and_then(|d| self.parse_person(d).ok()))
            .collect();

        Ok(people)
    }

    /// Create a new person
    pub async fn create_person(
        &self,
        uid: &str,
        name: &str,
    ) -> Result<crate::models::Person, Box<dyn std::error::Error + Send + Sync>> {
        let person_id = uuid::Uuid::new_v4().to_string();
        let now = Utc::now();

        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            PEOPLE_SUBCOLLECTION,
            person_id
        );

        let fields = json!({
            "name": {"stringValue": name},
            "created_at": {"timestampValue": now.to_rfc3339()},
            "updated_at": {"timestampValue": now.to_rfc3339()}
        });

        let doc = json!({"fields": fields});

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore create person error: {}", error_text).into());
        }

        tracing::info!("Created person '{}' ({}) for user {}", name, person_id, uid);

        Ok(crate::models::Person {
            id: person_id,
            name: name.to_string(),
            created_at: now,
            updated_at: now,
        })
    }

    /// Update a person's name
    pub async fn update_person_name(
        &self,
        uid: &str,
        person_id: &str,
        new_name: &str,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let now = Utc::now();
        let url = format!(
            "{}/{}/{}/{}/{}?updateMask.fieldPaths=name&updateMask.fieldPaths=updated_at",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            PEOPLE_SUBCOLLECTION,
            person_id
        );

        let fields = json!({
            "name": {"stringValue": new_name},
            "updated_at": {"timestampValue": now.to_rfc3339()}
        });

        let doc = json!({"fields": fields});

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore update person error: {}", error_text).into());
        }

        Ok(())
    }

    /// Delete a person
    pub async fn delete_person(
        &self,
        uid: &str,
        person_id: &str,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            PEOPLE_SUBCOLLECTION,
            person_id
        );

        let response = self
            .build_request(reqwest::Method::DELETE, &url)
            .await?
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore delete person error: {}", error_text).into());
        }

        tracing::info!("Deleted person {} for user {}", person_id, uid);
        Ok(())
    }

    /// Bulk assign segments in a conversation to a person or user
    pub async fn assign_segments_bulk(
        &self,
        uid: &str,
        conversation_id: &str,
        segment_ids: &[String],
        assign_type: &str,
        value: Option<&str>,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        // Get the current conversation to read segments
        let conv = self
            .get_conversation(uid, conversation_id)
            .await?
            .ok_or("Conversation not found")?;
        let mut segments = conv.transcript_segments;

        // Update matching segments by stable segment id first, then fall back to explicit index targets.
        for target in segment_ids {
            let matched_segment = if let Some(index) = target
                .strip_prefix("#index:")
                .and_then(|value| value.parse::<usize>().ok())
            {
                segments.get_mut(index)
            } else {
                segments
                    .iter_mut()
                    .find(|seg| seg.id.as_deref() == Some(target.as_str()))
            };

            if let Some(seg) = matched_segment {
                match assign_type {
                    "is_user" => {
                        seg.is_user = value.map(|v| v == "true").unwrap_or(false);
                        if seg.is_user {
                            seg.person_id = None;
                        }
                    }
                    "person_id" => {
                        seg.person_id = value.map(|s| s.to_string());
                        seg.is_user = false;
                    }
                    _ => {}
                }
            }
        }

        // Write updated segments back as array
        let segment_values: Vec<Value> = segments
            .iter()
            .map(|seg| {
                let mut fields = json!({
                    "text": {"stringValue": seg.text},
                    "speaker": {"stringValue": seg.speaker},
                    "speaker_id": {"integerValue": seg.speaker_id.to_string()},
                    "is_user": {"booleanValue": seg.is_user},
                    "start": {"doubleValue": seg.start},
                    "end": {"doubleValue": seg.end}
                });
                if let Some(ref id) = seg.id {
                    fields["id"] = json!({"stringValue": id});
                }
                if let Some(ref pid) = seg.person_id {
                    fields["person_id"] = json!({"stringValue": pid});
                }
                json!({"mapValue": {"fields": fields}})
            })
            .collect();

        let url = format!(
            "{}/{}/{}/{}/{}?updateMask.fieldPaths=transcript_segments",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            CONVERSATIONS_SUBCOLLECTION,
            conversation_id
        );

        let doc = json!({
            "fields": {
                "transcript_segments": {
                    "arrayValue": {
                        "values": segment_values
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
            return Err(format!("Firestore assign segments error: {}", error_text).into());
        }

        tracing::info!(
            "Assigned {} segments in conversation {} for user {}",
            segment_ids.len(),
            conversation_id,
            uid
        );
        Ok(())
    }

    /// Parse a person document from Firestore
    fn parse_person(
        &self,
        doc: &Value,
    ) -> Result<crate::models::Person, Box<dyn std::error::Error + Send + Sync>> {
        let fields = doc.get("fields").ok_or("Missing fields")?;
        let name_path = doc.get("name").and_then(|n| n.as_str()).unwrap_or("");
        let id = name_path.split('/').last().unwrap_or("").to_string();

        Ok(crate::models::Person {
            id,
            name: self.parse_string(fields, "name").unwrap_or_default(),
            created_at: self
                .parse_timestamp_optional(fields, "created_at")
                .unwrap_or_else(Utc::now),
            updated_at: self
                .parse_timestamp_optional(fields, "updated_at")
                .unwrap_or_else(Utc::now),
        })
    }
}
