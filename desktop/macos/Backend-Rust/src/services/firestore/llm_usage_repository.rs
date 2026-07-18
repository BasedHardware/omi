use super::*;

impl FirestoreService {
    // =========================================================================
    // LLM USAGE

    /// Atomically increment LLM usage counters for a user on a given date.
    /// Uses Firestore REST commit with FieldTransforms (server-side atomic increments).
    pub(crate) async fn record_llm_usage(
        &self,
        uid: &str,
        input: i64,
        output: i64,
        cache_read: i64,
        cache_write: i64,
        total: i64,
        cost: f64,
        account: &str,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let date_key = Utc::now().format("%Y-%m-%d").to_string();
        let doc_path = format!(
            "projects/{}/databases/(default)/documents/{}/{}/{}/{}",
            self.project_id, USERS_COLLECTION, uid, LLM_USAGE_SUBCOLLECTION, date_key
        );
        let commit_url = format!(
            "https://firestore.googleapis.com/v1/projects/{}/databases/(default)/documents:commit",
            self.project_id
        );
        // Write to account-specific prefix (e.g. "desktop_chat_omi" or "desktop_chat_personal")
        // Also continue writing to "desktop_chat" for backward compat with existing queries
        let acct_prefix = format!("desktop_chat_{}", account);
        let body = json!({
            "writes": [{
                "transform": {
                    "document": doc_path,
                    "fieldTransforms": [
                        { "fieldPath": "desktop_chat.input_tokens",       "increment": { "integerValue": input.to_string() } },
                        { "fieldPath": "desktop_chat.output_tokens",      "increment": { "integerValue": output.to_string() } },
                        { "fieldPath": "desktop_chat.cache_read_tokens",  "increment": { "integerValue": cache_read.to_string() } },
                        { "fieldPath": "desktop_chat.cache_write_tokens", "increment": { "integerValue": cache_write.to_string() } },
                        { "fieldPath": "desktop_chat.total_tokens",       "increment": { "integerValue": total.to_string() } },
                        { "fieldPath": "desktop_chat.cost_usd",           "increment": { "doubleValue": cost } },
                        { "fieldPath": "desktop_chat.call_count",         "increment": { "integerValue": "1" } },
                        { "fieldPath": format!("{}.input_tokens", acct_prefix),       "increment": { "integerValue": input.to_string() } },
                        { "fieldPath": format!("{}.output_tokens", acct_prefix),      "increment": { "integerValue": output.to_string() } },
                        { "fieldPath": format!("{}.cache_read_tokens", acct_prefix),  "increment": { "integerValue": cache_read.to_string() } },
                        { "fieldPath": format!("{}.cache_write_tokens", acct_prefix), "increment": { "integerValue": cache_write.to_string() } },
                        { "fieldPath": format!("{}.total_tokens", acct_prefix),       "increment": { "integerValue": total.to_string() } },
                        { "fieldPath": format!("{}.cost_usd", acct_prefix),           "increment": { "doubleValue": cost } },
                        { "fieldPath": format!("{}.call_count", acct_prefix),         "increment": { "integerValue": "1" } },
                    ]
                }
            }]
        });
        let resp = self
            .build_request(reqwest::Method::POST, &commit_url)
            .await?
            .json(&body)
            .send()
            .await?;
        if !resp.status().is_success() {
            return Err(resp.text().await?.into());
        }
        Ok(())
    }

    /// Increment the total desktop question counter and, when provided, an
    /// account-specific quota counter for rollout-safe breakdown fallback.
    pub(crate) async fn record_desktop_chat_quota_question_with_account(
        &self,
        uid: &str,
        account: Option<&str>,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let date_key = Utc::now().format("%Y-%m-%d").to_string();
        let doc_path = format!(
            "projects/{}/databases/(default)/documents/{}/{}/{}/{}",
            self.project_id, USERS_COLLECTION, uid, LLM_USAGE_SUBCOLLECTION, date_key
        );
        let commit_url = format!(
            "https://firestore.googleapis.com/v1/projects/{}/databases/(default)/documents:commit",
            self.project_id
        );
        let mut field_transforms = vec![
            json!({ "fieldPath": "desktop_chat.quota_questions", "increment": { "integerValue": "1" } }),
        ];
        if let Some(account) = account {
            field_transforms.push(
                json!({ "fieldPath": format!("desktop_chat_{}.quota_questions", account), "increment": { "integerValue": "1" } }),
            );
        }
        let body = json!({
            "writes": [{
                "transform": {
                    "document": doc_path,
                    "fieldTransforms": field_transforms
                }
            }]
        });
        let resp = self
            .build_request(reqwest::Method::POST, &commit_url)
            .await?
            .json(&body)
            .send()
            .await?;
        if !resp.status().is_success() {
            return Err(resp.text().await?.into());
        }
        Ok(())
    }

    /// Record a minted realtime session for out-of-band billing reconciliation.
    ///
    /// The realtime WS is client↔provider direct, so the backend never sees the
    /// minutes/tokens inline. This persists a NON-SECRET record of each minted session
    /// (the doc id is a hash of the token via `document_id_from_seed`; the token itself
    /// is never stored) so a reconciliation job can later attribute provider usage to
    /// the user and write the cost into the llm_usage ledger via
    /// `record_llm_usage(.., "realtime")`. `status` starts "minted"; the reconciler
    /// flips it to "reconciled".
    pub(crate) async fn record_realtime_session(
        &self,
        uid: &str,
        token: &str,
        provider: &str,
        model: &str,
        expires_at: &str,
        max_minutes: i64,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let session_id = document_id_from_seed(token);
        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            REALTIME_SESSIONS_SUBCOLLECTION,
            session_id
        );
        let minted_at = Utc::now().format("%Y-%m-%dT%H:%M:%SZ").to_string();
        let doc = json!({
            "fields": {
                "provider":    { "stringValue": provider },
                "model":       { "stringValue": model },
                "status":      { "stringValue": "minted" },
                "minted_at":   { "timestampValue": minted_at },
                "expires_at":  { "stringValue": expires_at },
                "max_minutes": { "integerValue": max_minutes.to_string() },
            }
        });
        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&doc)
            .send()
            .await?;
        if !response.status().is_success() {
            return Err(format!(
                "Firestore realtime-session write error: {}",
                response.text().await?
            )
            .into());
        }
        Ok(())
    }
}
