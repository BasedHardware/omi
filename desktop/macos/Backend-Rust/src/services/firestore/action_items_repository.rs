use super::*;

struct ActionItemsQuery<'a> {
    completed: Option<bool>,
    conversation_id: Option<&'a str>,
    created_after: Option<&'a str>,
    created_before: Option<&'a str>,
    due_after: Option<&'a str>,
    due_before: Option<&'a str>,
    sort_by: Option<&'a str>,
}

struct NewActionItem<'a> {
    description: &'a str,
    due_at: Option<&'a DateTime<Utc>>,
    source: Option<&'a str>,
    priority: Option<&'a str>,
    metadata: Option<&'a str>,
    category: Option<&'a str>,
    relevance_score: Option<i32>,
    from_staged: Option<bool>,
    recurrence_rule: Option<&'a str>,
    recurrence_parent_id: Option<&'a str>,
}

impl NewActionItem<'_> {
    fn firestore_document(&self, now: &DateTime<Utc>) -> Value {
        let mut fields = json!({
            "description": {"stringValue": self.description},
            "completed": {"booleanValue": false},
            "created_at": {"timestampValue": now.to_rfc3339()},
            "updated_at": {"timestampValue": now.to_rfc3339()}
        });

        if let Some(value) = self.due_at {
            fields["due_at"] = json!({"timestampValue": value.to_rfc3339()});
        }
        if let Some(value) = self.source {
            fields["source"] = json!({"stringValue": value});
        }
        if let Some(value) = self.priority {
            fields["priority"] = json!({"stringValue": value});
        }
        if let Some(value) = self.metadata {
            fields["metadata"] = json!({"stringValue": value});
        }
        if let Some(value) = self.category {
            fields["category"] = json!({"stringValue": value});
        }
        if let Some(value) = self.relevance_score {
            fields["relevance_score"] = json!({"integerValue": value.to_string()});
        }
        if let Some(value) = self.from_staged {
            fields["from_staged"] = json!({"booleanValue": value});
        }
        if let Some(value) = self.recurrence_rule {
            fields["recurrence_rule"] = json!({"stringValue": value});
        }
        if let Some(value) = self.recurrence_parent_id {
            fields["recurrence_parent_id"] = json!({"stringValue": value});
        }

        json!({"fields": fields})
    }
}

enum FilterValue<'a> {
    Bool(bool),
    String(&'a str),
    Timestamp(&'a str),
}

impl FilterValue<'_> {
    fn into_wire_value(self) -> Value {
        match self {
            Self::Bool(value) => json!({"booleanValue": value}),
            Self::String(value) => json!({"stringValue": value}),
            Self::Timestamp(value) => json!({"timestampValue": value}),
        }
    }
}

fn push_filter(
    filters: &mut Vec<Value>,
    field: &str,
    operation: &str,
    value: Option<FilterValue<'_>>,
) {
    if let Some(value) = value {
        filters.push(json!({
            "fieldFilter": {
                "field": {"fieldPath": field},
                "op": operation,
                "value": value.into_wire_value()
            }
        }));
    }
}

impl ActionItemsQuery<'_> {
    fn firestore_query(&self, limit: usize, offset: usize) -> Value {
        let mut filters = Vec::new();
        push_filter(
            &mut filters,
            "completed",
            "EQUAL",
            self.completed.map(FilterValue::Bool),
        );
        push_filter(
            &mut filters,
            "conversation_id",
            "EQUAL",
            self.conversation_id.map(FilterValue::String),
        );
        push_filter(
            &mut filters,
            "created_at",
            "GREATER_THAN_OR_EQUAL",
            self.created_after.map(FilterValue::Timestamp),
        );
        push_filter(
            &mut filters,
            "created_at",
            "LESS_THAN_OR_EQUAL",
            self.created_before.map(FilterValue::Timestamp),
        );
        push_filter(
            &mut filters,
            "due_at",
            "GREATER_THAN_OR_EQUAL",
            self.due_after.map(FilterValue::Timestamp),
        );
        push_filter(
            &mut filters,
            "due_at",
            "LESS_THAN_OR_EQUAL",
            self.due_before.map(FilterValue::Timestamp),
        );

        let mut query = json!({
            "from": [{"collectionId": ACTION_ITEMS_SUBCOLLECTION}],
            "orderBy": self.order_by(),
            "limit": limit,
            "offset": offset
        });
        match filters.len() {
            0 => {}
            1 => query["where"] = filters.remove(0),
            _ => {
                query["where"] = json!({
                    "compositeFilter": {"op": "AND", "filters": filters}
                });
            }
        }
        json!({"structuredQuery": query})
    }

    fn order_by(&self) -> Value {
        match self.sort_by {
            Some("due_at") => json!([
                {"field": {"fieldPath": "due_at"}, "direction": "ASCENDING"},
                {"field": {"fieldPath": "created_at"}, "direction": "DESCENDING"}
            ]),
            Some("priority") => json!([
                {"field": {"fieldPath": "priority"}, "direction": "DESCENDING"},
                {"field": {"fieldPath": "created_at"}, "direction": "DESCENDING"}
            ]),
            _ => json!([
                {"field": {"fieldPath": "created_at"}, "direction": "DESCENDING"}
            ]),
        }
    }
}

impl FirestoreService {
    pub(crate) async fn get_action_items(
        &self,
        uid: &str,
        limit: usize,
        offset: usize,
        completed_filter: Option<bool>,
        conversation_id: Option<&str>,
        start_date: Option<&str>,
        end_date: Option<&str>,
        due_start_date: Option<&str>,
        due_end_date: Option<&str>,
        sort_by: Option<&str>,
        include_deleted: Option<bool>,
    ) -> Result<Vec<ActionItemDB>, Box<dyn std::error::Error + Send + Sync>> {
        let parent = format!("{}/{}/{}", self.base_url(), USERS_COLLECTION, uid);
        let query = ActionItemsQuery {
            completed: completed_filter,
            conversation_id,
            created_after: start_date,
            created_before: end_date,
            due_after: due_start_date,
            due_before: due_end_date,
            sort_by,
        };

        // Firestore cannot reliably filter `deleted` because older documents omit it.
        // Fetch until post-filtering has produced a full page or Firestore is exhausted.
        let mut action_items = Vec::new();
        let mut current_offset = offset;
        let fetch_batch = limit.max(500);
        loop {
            let response = self
                .build_request(reqwest::Method::POST, &format!("{}:runQuery", parent))
                .await?
                .json(&query.firestore_query(fetch_batch, current_offset))
                .send()
                .await?;
            if !response.status().is_success() {
                let error_text = response.text().await?;
                tracing::error!("Firestore query error for action_items: {}", error_text);
                return Err(format!("Firestore query error: {}", error_text).into());
            }

            let results: Vec<Value> = response.json().await?;
            let fetched_count = results
                .iter()
                .filter(|result| result.get("document").is_some())
                .count();
            action_items.extend(
                results
                    .into_iter()
                    .filter_map(|result| result.get("document").cloned())
                    .filter_map(|document| values::parse_action_item(&document).ok())
                    .filter(|item| match include_deleted {
                        Some(true) => item.deleted == Some(true),
                        _ => item.deleted != Some(true),
                    }),
            );
            current_offset += fetched_count;

            if fetched_count < fetch_batch {
                break;
            }
            if action_items.len() >= limit {
                action_items.truncate(limit);
                break;
            }
        }

        self.enrich_action_items_with_source(uid, &mut action_items)
            .await;
        action_items.sort_by(|left, right| match (&left.due_at, &right.due_at) {
            (Some(left_due), Some(right_due)) => left_due
                .cmp(right_due)
                .then_with(|| right.created_at.cmp(&left.created_at)),
            (Some(_), None) => std::cmp::Ordering::Less,
            (None, Some(_)) => std::cmp::Ordering::Greater,
            (None, None) => right.created_at.cmp(&left.created_at),
        });

        Ok(action_items)
    }

    async fn enrich_action_items_with_source(&self, uid: &str, items: &mut [ActionItemDB]) {
        use std::collections::{HashMap, HashSet};

        let conversation_ids: HashSet<&str> = items
            .iter()
            .filter(|item| item.source.is_none())
            .filter_map(|item| item.conversation_id.as_deref())
            .collect();
        if conversation_ids.is_empty() {
            return;
        }

        let mut source_by_conversation = HashMap::new();
        let conversation_ids: Vec<&str> = conversation_ids.into_iter().collect();
        for chunk in conversation_ids.chunks(10) {
            let requests = chunk
                .iter()
                .map(|id| self.get_action_item_source_from_conversation(uid, id));
            let results = futures::future::join_all(requests).await;

            for (id, result) in chunk.iter().zip(results) {
                if let Ok(Some(source)) = result {
                    source_by_conversation.insert((*id).to_owned(), source);
                }
            }
        }

        for item in items.iter_mut().filter(|item| item.source.is_none()) {
            if let Some(conversation_id) = &item.conversation_id {
                item.source = source_by_conversation.get(conversation_id).cloned();
            }
        }
    }

    pub(crate) async fn create_action_item(
        &self,
        uid: &str,
        description: &str,
        due_at: Option<DateTime<Utc>>,
        source: Option<&str>,
        priority: Option<&str>,
        metadata: Option<&str>,
        category: Option<&str>,
        relevance_score: Option<i32>,
        from_staged: Option<bool>,
        recurrence_rule: Option<&str>,
        recurrence_parent_id: Option<&str>,
    ) -> Result<ActionItemDB, Box<dyn std::error::Error + Send + Sync>> {
        let item_id = uuid::Uuid::new_v4().to_string();
        let now = Utc::now();
        let url = format!(
            "{}/{}/{}/{}/{}",
            self.base_url(),
            USERS_COLLECTION,
            uid,
            ACTION_ITEMS_SUBCOLLECTION,
            item_id
        );
        let new_item = NewActionItem {
            description,
            due_at: due_at.as_ref(),
            source,
            priority,
            metadata,
            category,
            relevance_score,
            from_staged,
            recurrence_rule,
            recurrence_parent_id,
        };

        let response = self
            .build_request(reqwest::Method::PATCH, &url)
            .await?
            .json(&new_item.firestore_document(&now))
            .send()
            .await?;
        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(format!("Firestore create error: {}", error_text).into());
        }

        let created_doc: Value = response.json().await?;
        let action_item = values::parse_action_item(&created_doc)?;
        tracing::info!(
            "Created action item {} for user {} with source={:?}",
            item_id,
            uid,
            source
        );
        Ok(action_item)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn empty_query<'a>() -> ActionItemsQuery<'a> {
        ActionItemsQuery {
            completed: None,
            conversation_id: None,
            created_after: None,
            created_before: None,
            due_after: None,
            due_before: None,
            sort_by: None,
        }
    }

    fn new_action_item(description: &str) -> NewActionItem<'_> {
        NewActionItem {
            description,
            due_at: None,
            source: None,
            priority: None,
            metadata: None,
            category: None,
            relevance_score: None,
            from_staged: None,
            recurrence_rule: None,
            recurrence_parent_id: None,
        }
    }

    #[test]
    fn default_query_has_no_filter_and_orders_newest_first() {
        let query = empty_query().firestore_query(500, 25);
        let structured = &query["structuredQuery"];

        assert!(structured.get("where").is_none());
        assert_eq!(structured["limit"], 500);
        assert_eq!(structured["offset"], 25);
        assert_eq!(
            structured["orderBy"],
            json!([{
                "field": {"fieldPath": "created_at"},
                "direction": "DESCENDING"
            }])
        );
    }

    #[test]
    fn single_filter_uses_a_field_filter_without_composite_wrapper() {
        let mut request = empty_query();
        request.completed = Some(false);

        let query = request.firestore_query(10, 0);
        assert_eq!(
            query["structuredQuery"]["where"],
            json!({
                "fieldFilter": {
                    "field": {"fieldPath": "completed"},
                    "op": "EQUAL",
                    "value": {"booleanValue": false}
                }
            })
        );
    }

    #[test]
    fn combined_filters_preserve_firestore_value_types_and_due_sort() {
        let request = ActionItemsQuery {
            completed: Some(true),
            conversation_id: Some("conversation-1"),
            created_after: Some("2026-07-01T00:00:00Z"),
            created_before: None,
            due_after: None,
            due_before: Some("2026-08-01T00:00:00Z"),
            sort_by: Some("due_at"),
        };

        let query = request.firestore_query(100, 0);
        let structured = &query["structuredQuery"];
        let filters = structured["where"]["compositeFilter"]["filters"]
            .as_array()
            .expect("composite filter list");

        assert_eq!(filters.len(), 4);
        assert_eq!(filters[0]["fieldFilter"]["value"]["booleanValue"], true);
        assert_eq!(
            filters[1]["fieldFilter"]["value"]["stringValue"],
            "conversation-1"
        );
        assert_eq!(
            filters[2]["fieldFilter"]["value"]["timestampValue"],
            "2026-07-01T00:00:00Z"
        );
        assert_eq!(structured["orderBy"][0]["field"]["fieldPath"], "due_at");
    }

    #[test]
    fn new_action_item_document_has_stable_required_fields() {
        let now = DateTime::parse_from_rfc3339("2026-07-12T10:00:00Z")
            .expect("timestamp")
            .with_timezone(&Utc);
        let doc = new_action_item("Ship it").firestore_document(&now);

        assert_eq!(doc["fields"]["description"]["stringValue"], "Ship it");
        assert_eq!(doc["fields"]["completed"]["booleanValue"], false);
        assert_eq!(
            doc["fields"]["created_at"]["timestampValue"],
            "2026-07-12T10:00:00+00:00"
        );
        assert!(doc["fields"].get("source").is_none());
    }

    #[test]
    fn new_action_item_document_encodes_optional_wire_types() {
        let now = DateTime::parse_from_rfc3339("2026-07-12T10:00:00Z")
            .expect("timestamp")
            .with_timezone(&Utc);
        let due_at = DateTime::parse_from_rfc3339("2026-07-13T10:00:00Z")
            .expect("timestamp")
            .with_timezone(&Utc);
        let mut item = new_action_item("Ship it");
        item.due_at = Some(&due_at);
        item.source = Some("manual");
        item.relevance_score = Some(3);
        item.from_staged = Some(true);

        let fields = item.firestore_document(&now)["fields"].clone();
        assert_eq!(
            fields["due_at"]["timestampValue"],
            "2026-07-13T10:00:00+00:00"
        );
        assert_eq!(fields["source"]["stringValue"], "manual");
        assert_eq!(fields["relevance_score"]["integerValue"], "3");
        assert_eq!(fields["from_staged"]["booleanValue"], true);
    }
}
