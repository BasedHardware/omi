use super::*;

impl FirestoreService {
    pub async fn get_folders(
        &self,
        uid: &str,
    ) -> Result<Vec<Folder>, Box<dyn std::error::Error + Send + Sync>> {
        let parent = format!("{}/{}/{}", self.base_url(), USERS_COLLECTION, uid);

        let structured_query = json!({
            "from": [{"collectionId": FOLDERS_SUBCOLLECTION}],
            "orderBy": [{"field": {"fieldPath": "order"}, "direction": "ASCENDING"}]
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
            return Err(format!("Firestore query error: {}", error_text).into());
        }

        let results: Vec<Value> = response.json().await?;
        let folders = results
            .into_iter()
            .filter_map(|doc| doc.get("document").and_then(|d| self.parse_folder(d).ok()))
            .collect();

        Ok(folders)
    }

    /// Create a new folder
    pub async fn create_folder(
        &self,
        uid: &str,
        name: &str,
        description: Option<&str>,
        color: Option<&str>,
    ) -> Result<Folder, Box<dyn std::error::Error + Send + Sync>> {
        let folder_id = uuid::Uuid::new_v4().to_string();
        let now = Utc::now();

        let existing = self.get_folders(uid).await?;
        let order = existing.len() as i32;

        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            FOLDERS_SUBCOLLECTION,
            folder_id
        );

        let mut fields = json!({
            "name": {"stringValue": name},
            "color": {"stringValue": color.unwrap_or("#6B7280")},
            "order": {"integerValue": order.to_string()},
            "is_default": {"booleanValue": false},
            "is_system": {"booleanValue": false},
            "conversation_count": {"integerValue": "0"},
            "created_at": {"timestampValue": now.to_rfc3339()},
            "updated_at": {"timestampValue": now.to_rfc3339()}
        });

        if let Some(desc) = description {
            fields["description"] = json!({"stringValue": desc});
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

        tracing::info!("Created folder {} for user {}", folder_id, uid);

        Ok(Folder {
            id: folder_id,
            name: name.to_string(),
            description: description.map(|s| s.to_string()),
            color: color.unwrap_or("#6B7280").to_string(),
            created_at: now,
            updated_at: now,
            order,
            is_default: false,
            is_system: false,
            category_mapping: None,
            conversation_count: 0,
        })
    }

    /// Update a folder
    pub async fn update_folder(
        &self,
        uid: &str,
        folder_id: &str,
        name: Option<&str>,
        description: Option<&str>,
        color: Option<&str>,
        order: Option<i32>,
    ) -> Result<Folder, Box<dyn std::error::Error + Send + Sync>> {
        let now = Utc::now();
        let mut field_paths: Vec<&str> = vec!["updated_at"];
        let mut fields = json!({
            "updated_at": {"timestampValue": now.to_rfc3339()}
        });

        if let Some(n) = name {
            field_paths.push("name");
            fields["name"] = json!({"stringValue": n});
        }

        if let Some(d) = description {
            field_paths.push("description");
            fields["description"] = json!({"stringValue": d});
        }

        if let Some(c) = color {
            field_paths.push("color");
            fields["color"] = json!({"stringValue": c});
        }

        if let Some(o) = order {
            field_paths.push("order");
            fields["order"] = json!({"integerValue": o.to_string()});
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
            FOLDERS_SUBCOLLECTION,
            folder_id,
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
        let folder = self.parse_folder(&updated_doc)?;

        tracing::info!("Updated folder {} for user {}", folder_id, uid);
        Ok(folder)
    }

    /// Delete a folder
    pub async fn delete_folder(
        &self,
        uid: &str,
        folder_id: &str,
        move_to_folder_id: Option<&str>,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        loop {
            let conversations = self
                .get_conversations(
                    uid,
                    500,
                    0,
                    true,
                    &[],
                    None,
                    None,
                    Some(folder_id),
                    None,
                    None,
                    "created_at",
                )
                .await?;
            if conversations.is_empty() {
                break;
            }
            for conv in conversations {
                self.set_conversation_folder(uid, &conv.id, move_to_folder_id)
                    .await?;
            }
        }

        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            FOLDERS_SUBCOLLECTION,
            folder_id
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

        tracing::info!("Deleted folder {} for user {}", folder_id, uid);
        Ok(())
    }

    /// Set conversation folder
    pub async fn set_conversation_folder(
        &self,
        uid: &str,
        conversation_id: &str,
        folder_id: Option<&str>,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let url = format!(
            "{}/{}/{}/{}/{}?updateMask.fieldPaths=folder_id",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            CONVERSATIONS_SUBCOLLECTION,
            conversation_id
        );

        let doc = if let Some(fid) = folder_id {
            json!({"fields": {"folder_id": {"stringValue": fid}}})
        } else {
            json!({"fields": {"folder_id": {"nullValue": null}}})
        };

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
            "Set conversation {} folder to {:?} for user {}",
            conversation_id,
            folder_id,
            uid
        );
        Ok(())
    }

    /// Bulk move conversations to a folder
    pub async fn bulk_move_to_folder(
        &self,
        uid: &str,
        folder_id: &str,
        conversation_ids: &[String],
    ) -> Result<i32, Box<dyn std::error::Error + Send + Sync>> {
        let mut moved_count = 0;
        for conv_id in conversation_ids {
            if self
                .set_conversation_folder(uid, conv_id, Some(folder_id))
                .await
                .is_ok()
            {
                moved_count += 1;
            }
        }
        tracing::info!(
            "Bulk moved {} conversations to folder {} for user {}",
            moved_count,
            folder_id,
            uid
        );
        Ok(moved_count)
    }

    /// Reorder folders
    pub async fn reorder_folders(
        &self,
        uid: &str,
        folder_ids: &[String],
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        for (index, folder_id) in folder_ids.iter().enumerate() {
            let url = format!(
                "{}/{}/{}/{}/{}?updateMask.fieldPaths=order",
                self.base_url(),
                USERS_COLLECTION,
                uid,
                FOLDERS_SUBCOLLECTION,
                folder_id
            );

            let doc = json!({"fields": {"order": {"integerValue": index.to_string()}}});
            let response = self
                .build_request(reqwest::Method::PATCH, &url)
                .await?
                .json(&doc)
                .send()
                .await?;
            if !response.status().is_success() {
                let error_text = response.text().await?;
                return Err(format!("Firestore reorder error: {}", error_text).into());
            }
        }
        tracing::info!("Reordered {} folders for user {}", folder_ids.len(), uid);
        Ok(())
    }
}
