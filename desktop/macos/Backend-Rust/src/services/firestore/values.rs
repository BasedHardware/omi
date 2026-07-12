use chrono::{DateTime, Utc};
use serde_json::Value;

use crate::models::ActionItemDB;

pub(super) fn string_field(fields: &Value, key: &str) -> Option<String> {
    fields
        .get(key)?
        .get("stringValue")?
        .as_str()
        .map(str::to_owned)
}

pub(super) fn bool_field(fields: &Value, key: &str) -> Option<bool> {
    fields.get(key)?.get("booleanValue")?.as_bool()
}

pub(super) fn i32_field(fields: &Value, key: &str) -> Option<i32> {
    fields.get(key)?.get("integerValue")?.as_str()?.parse().ok()
}

fn timestamp_field(fields: &Value, key: &str) -> Option<DateTime<Utc>> {
    fields
        .get(key)?
        .get("timestampValue")?
        .as_str()
        .and_then(|timestamp| DateTime::parse_from_rfc3339(timestamp).ok())
        .map(|timestamp| timestamp.with_timezone(&Utc))
}

pub(super) fn parse_action_item(
    doc: &Value,
) -> Result<ActionItemDB, Box<dyn std::error::Error + Send + Sync>> {
    let fields = doc.get("fields").ok_or("Missing fields")?;
    let id = doc
        .get("name")
        .and_then(Value::as_str)
        .and_then(|name| name.rsplit('/').next())
        .unwrap_or_default()
        .to_owned();

    Ok(ActionItemDB {
        id,
        description: string_field(fields, "description").unwrap_or_default(),
        completed: bool_field(fields, "completed").unwrap_or(false),
        created_at: timestamp_field(fields, "created_at").unwrap_or_else(Utc::now),
        updated_at: timestamp_field(fields, "updated_at"),
        due_at: timestamp_field(fields, "due_at"),
        completed_at: timestamp_field(fields, "completed_at"),
        conversation_id: string_field(fields, "conversation_id"),
        source: string_field(fields, "source"),
        priority: string_field(fields, "priority"),
        metadata: string_field(fields, "metadata"),
        deleted: bool_field(fields, "deleted"),
        deleted_by: string_field(fields, "deleted_by"),
        deleted_at: timestamp_field(fields, "deleted_at"),
        deleted_reason: string_field(fields, "deleted_reason"),
        kept_task_id: string_field(fields, "kept_task_id"),
        category: string_field(fields, "category"),
        goal_id: string_field(fields, "goal_id"),
        relevance_score: i32_field(fields, "relevance_score"),
        sort_order: i32_field(fields, "sort_order"),
        indent_level: i32_field(fields, "indent_level"),
        from_staged: bool_field(fields, "from_staged"),
        recurrence_rule: string_field(fields, "recurrence_rule"),
        recurrence_parent_id: string_field(fields, "recurrence_parent_id"),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn parses_action_item_wire_document() {
        let doc = json!({
            "name": "projects/test/databases/(default)/documents/users/u/action_items/item-1",
            "fields": {
                "description": {"stringValue": "Ship it"},
                "completed": {"booleanValue": true},
                "created_at": {"timestampValue": "2026-07-01T10:00:00Z"},
                "conversation_id": {"stringValue": "conversation-1"},
                "relevance_score": {"integerValue": "7"},
                "from_staged": {"booleanValue": false}
            }
        });

        let item = parse_action_item(&doc).expect("valid action-item document");

        assert_eq!(item.id, "item-1");
        assert_eq!(item.description, "Ship it");
        assert!(item.completed);
        assert_eq!(item.conversation_id.as_deref(), Some("conversation-1"));
        assert_eq!(item.relevance_score, Some(7));
        assert_eq!(item.from_staged, Some(false));
    }

    #[test]
    fn rejects_documents_without_fields() {
        assert!(parse_action_item(&json!({})).is_err());
    }
}
