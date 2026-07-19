use super::*;

impl FirestoreService {
    pub(crate) async fn upsert_screen_activity(
        &self,
        uid: &str,
        rows: &[crate::models::screen_activity::ScreenActivityRow],
    ) -> Result<usize, Box<dyn std::error::Error + Send + Sync>> {
        if rows.is_empty() {
            return Ok(0);
        }

        let mut written = 0;

        for chunk in rows.chunks(500) {
            let writes: Vec<Value> = chunk
                .iter()
                .map(|row| {
                    let doc_name = format!(
                        "projects/{}/databases/(default)/documents/{}/{}/{}/{}",
                        self.project_id,
                        USERS_COLLECTION,
                        uid,
                        SCREEN_ACTIVITY_SUBCOLLECTION,
                        row.id
                    );

                    // Truncate OCR text to 1000 chars
                    let ocr_truncated: String = row.ocr_text.chars().take(1000).collect();

                    json!({
                        "update": {
                            "name": doc_name,
                            "fields": {
                                "timestamp": {"stringValue": &row.timestamp},
                                "appName": {"stringValue": &row.app_name},
                                "windowTitle": {"stringValue": &row.window_title},
                                "ocrText": {"stringValue": ocr_truncated},
                            }
                        }
                    })
                })
                .collect();

            let commit_url = format!(
                "https://firestore.googleapis.com/v1/projects/{}/databases/(default)/documents:commit",
                self.project_id
            );

            let body = json!({ "writes": writes });

            let response = self
                .build_request(reqwest::Method::POST, &commit_url)
                .await?
                .json(&body)
                .send()
                .await?;

            if !response.status().is_success() {
                let error_text = response.text().await?;
                return Err(format!(
                    "Firestore screen_activity batch commit error: {}",
                    error_text
                )
                .into());
            }

            written += chunk.len();
        }

        tracing::info!(
            "Screen activity Firestore write uid={} count={}",
            uid,
            written
        );
        Ok(written)
    }
}
