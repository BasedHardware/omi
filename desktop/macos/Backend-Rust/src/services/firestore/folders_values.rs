use super::*;

impl FirestoreService {
    pub(super) fn parse_folder(
        &self,
        doc: &Value,
    ) -> Result<Folder, Box<dyn std::error::Error + Send + Sync>> {
        let fields = doc.get("fields").ok_or("Missing fields")?;
        let name_path = doc.get("name").and_then(|n| n.as_str()).unwrap_or("");
        let id = name_path.split('/').last().unwrap_or("").to_string();

        Ok(Folder {
            id,
            name: self.parse_string(fields, "name").unwrap_or_default(),
            description: self.parse_string(fields, "description"),
            color: self
                .parse_string(fields, "color")
                .unwrap_or_else(|| "#6B7280".to_string()),
            created_at: self
                .parse_timestamp_optional(fields, "created_at")
                .unwrap_or_else(Utc::now),
            updated_at: self
                .parse_timestamp_optional(fields, "updated_at")
                .unwrap_or_else(Utc::now),
            order: self.parse_int(fields, "order").unwrap_or(0),
            is_default: self.parse_bool(fields, "is_default").unwrap_or(false),
            is_system: self.parse_bool(fields, "is_system").unwrap_or(false),
            category_mapping: self.parse_string(fields, "category_mapping"),
            conversation_count: self.parse_int(fields, "conversation_count").unwrap_or(0),
        })
    }
}
