use super::*;

fn normalized_conversation_source(source: Option<&str>) -> &str {
    match source {
        None => "desktop",
        Some(
            source @ ("desktop" | "phone" | "omi" | "friend" | "workflow" | "openglass"
            | "screenpipe" | "sdcard" | "fieldy" | "bee" | "xor" | "frame" | "limitless"
            | "plaud" | "onboarding"),
        ) => source,
        Some("friend_com") => "friendcom",
        Some("apple_watch") => "applewatch",
        Some("external_integration") => "externalintegration",
        Some(_) => "unknown",
    }
}

fn action_item_source(doc: &Value) -> Result<String, &'static str> {
    let fields = doc.get("fields").ok_or("Missing fields in document")?;
    let raw_source = fields
        .get("source")
        .and_then(|source| source.get("stringValue"))
        .and_then(Value::as_str);
    Ok(format!(
        "transcription:{}",
        normalized_conversation_source(raw_source)
    ))
}

impl FirestoreService {
    pub(super) async fn get_action_item_source_from_conversation(
        &self,
        uid: &str,
        conversation_id: &str,
    ) -> Result<Option<String>, Box<dyn std::error::Error + Send + Sync>> {
        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            CONVERSATIONS_SUBCOLLECTION,
            conversation_id
        );

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
        Ok(Some(action_item_source(&doc)?))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn source_normalization_matches_legacy_conversation_enum() {
        assert_eq!(normalized_conversation_source(None), "desktop");
        assert_eq!(normalized_conversation_source(Some("omi")), "omi");
        assert_eq!(
            normalized_conversation_source(Some("external_integration")),
            "externalintegration"
        );
        assert_eq!(
            normalized_conversation_source(Some("apple_watch")),
            "applewatch"
        );
        assert_eq!(
            normalized_conversation_source(Some("new-device")),
            "unknown"
        );
    }

    #[test]
    fn action_item_source_requires_a_firestore_document_but_defaults_missing_source() {
        assert_eq!(
            action_item_source(&json!({"fields": {}})).as_deref(),
            Ok("transcription:desktop")
        );
        assert!(action_item_source(&json!({})).is_err());
    }
}
