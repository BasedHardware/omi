use super::*;

impl FirestoreService {
    pub(super) async fn get_user_document(
        &self,
        uid: &str,
    ) -> Result<Value, Box<dyn std::error::Error + Send + Sync>> {
        let url = format!("{}/{}/{}", self.base_url(), USERS_COLLECTION, uid);
        let response = self
            .build_request(reqwest::Method::GET, &url)
            .await?
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Failed to get user document: {}", error_text).into());
        }

        Ok(response.json().await?)
    }

    pub(crate) async fn get_user_byok_state(
        &self,
        uid: &str,
    ) -> Result<crate::byok::ByokState, Box<dyn std::error::Error + Send + Sync>> {
        let doc = self.get_user_document(uid).await?;
        Ok(parse_byok_state_from_doc(&doc))
    }

    pub(crate) async fn get_user_effective_plan(
        &self,
        uid: &str,
    ) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
        let doc = self.get_user_document(uid).await?;
        let plan = parse_effective_plan_from_doc(&doc);

        if let Some(subscription) = doc
            .get("fields")
            .and_then(|fields| fields.get("subscription"))
            .and_then(|subscription| subscription.get("mapValue"))
            .and_then(|subscription| subscription.get("fields"))
        {
            let raw_plan = subscription
                .get("plan")
                .and_then(|plan| plan.get("stringValue"))
                .and_then(Value::as_str)
                .unwrap_or("basic");
            if raw_plan != "basic" && raw_plan != "free" && plan == "basic" {
                tracing::info!(
                    "paywall: paid plan '{}' fell back to basic for uid={} (expired or missing period_end)",
                    raw_plan,
                    uid
                );
            }
        }

        Ok(plan)
    }

    pub(crate) async fn get_user_creation_time(
        &self,
        project_id: &str,
        uid: &str,
    ) -> Result<Option<i64>, Box<dyn std::error::Error + Send + Sync>> {
        let access_token = self.get_access_token().await?;
        let url = format!(
            "https://identitytoolkit.googleapis.com/v1/projects/{}/accounts:lookup",
            project_id
        );
        let response = self
            .client
            .post(&url)
            .bearer_auth(access_token)
            .json(&json!({"localId": [uid]}))
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firebase accounts:lookup failed: {}", error_text).into());
        }

        let body: Value = response.json().await?;
        Ok(body
            .get("users")
            .and_then(Value::as_array)
            .and_then(|users| users.first())
            .and_then(|user| user.get("createdAt"))
            .and_then(Value::as_str)
            .and_then(|created_at| created_at.parse().ok()))
    }

    pub(super) async fn update_user_fields(
        &self,
        uid: &str,
        fields: Value,
        update_mask: &[&str],
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let mask = update_mask
            .iter()
            .map(|field| format!("updateMask.fieldPaths={field}"))
            .collect::<Vec<_>>()
            .join("&");
        let url = format!("{}/{}/{}?{}", self.base_url(), USERS_COLLECTION, uid, mask);
        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&json!({"fields": fields}))
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Failed to update user fields: {}", error_text).into());
        }

        Ok(())
    }
}
