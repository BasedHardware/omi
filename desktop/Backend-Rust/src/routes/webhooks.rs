// Webhook routes (Sentry feedback -> Firestore action items)

use axum::{
    body::Bytes,
    extract::State,
    http::{HeaderMap, StatusCode},
    routing::post,
    Json, Router,
};
use hmac::{Hmac, Mac};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::Sha256;

use crate::AppState;

type HmacSha256 = Hmac<Sha256>;

/// Sentry webhook issue payload
#[derive(Deserialize)]
struct SentryWebhookPayload {
    action: String,
    data: SentryWebhookData,
}

#[derive(Deserialize)]
struct SentryWebhookData {
    issue: SentryIssue,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct SentryIssue {
    id: String,
    short_id: Option<String>,
    title: Option<String>,
    issue_category: Option<String>,
}

#[derive(Serialize)]
struct WebhookResponse {
    status: String,
}

/// POST /v1/webhooks/sentry - Handle Sentry issue webhooks
async fn handle_sentry_webhook(
    State(state): State<AppState>,
    headers: HeaderMap,
    body: Bytes,
) -> Result<Json<WebhookResponse>, StatusCode> {
    // Log incoming Sentry headers for debugging
    let sentry_headers: Vec<String> = headers
        .iter()
        .filter(|(k, _)| k.as_str().starts_with("sentry-hook"))
        .map(|(k, v)| format!("{}={}", k, v.to_str().unwrap_or("?")))
        .collect();
    tracing::info!("Sentry webhook: received request, headers: [{}]", sentry_headers.join(", "));

    // Handle Sentry verification/installation pings (return 200 immediately)
    let hook_resource = headers
        .get("sentry-hook-resource")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("");
    if hook_resource == "installation" {
        tracing::info!("Sentry webhook: responding to installation verification ping");
        return Ok(Json(WebhookResponse {
            status: "ok".to_string(),
        }));
    }

    // Verify HMAC signature if secret is configured
    if let Some(secret) = &state.config.sentry_webhook_secret {
        let signature = headers
            .get("sentry-hook-signature")
            .and_then(|v| v.to_str().ok());

        match signature {
            Some(sig) => {
                let mut mac = HmacSha256::new_from_slice(secret.as_bytes()).map_err(|e| {
                    tracing::error!("Sentry webhook: HMAC key error: {}", e);
                    StatusCode::INTERNAL_SERVER_ERROR
                })?;
                mac.update(&body);
                let expected = hex::encode(mac.finalize().into_bytes());

                if expected != sig {
                    tracing::warn!("Sentry webhook: signature mismatch (expected={}, got={})", expected, sig);
                    return Err(StatusCode::UNAUTHORIZED);
                }
                tracing::info!("Sentry webhook: signature verified");
            }
            None => {
                tracing::warn!("Sentry webhook: no signature header, proceeding anyway (Sentry may omit it)");
            }
        }
    } else {
        tracing::warn!("Sentry webhook: SENTRY_WEBHOOK_SECRET not set, skipping signature verification");
    }

    // Parse the payload
    let payload: SentryWebhookPayload = serde_json::from_slice(&body).map_err(|e| {
        tracing::error!("Sentry webhook: failed to parse payload: {}", e);
        StatusCode::BAD_REQUEST
    })?;

    // Only process "created" actions for feedback issues
    if payload.action != "created" {
        tracing::info!("Sentry webhook: ignoring action={}", payload.action);
        return Ok(Json(WebhookResponse {
            status: "ignored".to_string(),
        }));
    }

    let issue_category = payload
        .data
        .issue
        .issue_category
        .as_deref()
        .unwrap_or("");
    if issue_category != "feedback" {
        tracing::info!(
            "Sentry webhook: ignoring issueCategory={}",
            issue_category
        );
        return Ok(Json(WebhookResponse {
            status: "ignored".to_string(),
        }));
    }

    let admin_uid = state
        .config
        .sentry_admin_uid
        .as_deref()
        .ok_or_else(|| {
            tracing::error!("Sentry webhook: SENTRY_ADMIN_UID not configured");
            StatusCode::INTERNAL_SERVER_ERROR
        })?;

    let issue_id = &payload.data.issue.id;
    let short_id = payload
        .data
        .issue
        .short_id
        .as_deref()
        .unwrap_or("unknown");
    let issue_title = payload.data.issue.title.as_deref().unwrap_or("");

    tracing::info!(
        "Sentry webhook: processing feedback issue {} ({})",
        issue_id,
        short_id
    );

    // Dedup + relevance score: fetch existing items once for both checks
    let existing_items = state
        .firestore
        .get_action_items(admin_uid, 500, 0, None, None, None, None, None, None, None, None)
        .await
        .unwrap_or_default();

    let already_exists = existing_items.iter().any(|item| {
        if item.source.as_deref() != Some("sentry_feedback") {
            return false;
        }
        if let Some(meta_str) = &item.metadata {
            if let Ok(meta) = serde_json::from_str::<Value>(meta_str) {
                return meta.get("sentry_issue_id").and_then(|v| v.as_str()) == Some(issue_id);
            }
        }
        false
    });

    if already_exists {
        tracing::info!(
            "Sentry webhook: issue {} ({}) already exists as action item, skipping",
            issue_id,
            short_id
        );
        return Ok(Json(WebhookResponse {
            status: "duplicate".to_string(),
        }));
    }

    // Dynamically calculate top-10% relevance score from existing tasks
    let max_score = existing_items.iter().filter_map(|i| i.relevance_score).max().unwrap_or(100);
    let top_10_score = std::cmp::max(1, (max_score as f64 * 0.1).round() as i32);

    // Fetch full event details from Sentry API
    let (feedback_message, reporter_name, reporter_email, metadata) =
        fetch_sentry_event_details(&state, issue_id, short_id).await;

    // Build description
    let description = if !feedback_message.is_empty() {
        format!("[Sentry Feedback] {}: {}", short_id, feedback_message)
    } else if !issue_title.is_empty() {
        format!("[Sentry Feedback] {}: {}", short_id, issue_title)
    } else {
        format!("[Sentry Feedback] {}", short_id)
    };

    // Build metadata JSON
    let mut meta = json!({
        "sentry_issue_id": issue_id,
        "sentry_short_id": short_id,
        "sentry_url": format!("https://mediar-n5.sentry.io/issues/{}/", issue_id),
        "tags": ["bug"],
    });

    if !reporter_name.is_empty() {
        meta["reporter_name"] = json!(reporter_name);
    }
    if !reporter_email.is_empty() {
        meta["reporter_email"] = json!(reporter_email);
    }
    if let Some(extra) = metadata {
        // Merge extra fields from event details
        if let Value::Object(extra_map) = extra {
            if let Value::Object(ref mut meta_map) = meta {
                for (k, v) in extra_map {
                    meta_map.insert(k, v);
                }
            }
        }
    }

    let metadata_str = serde_json::to_string(&meta).unwrap_or_default();

    // Create action item
    match state
        .firestore
        .create_action_item(
            admin_uid,
            &description,
            None,                          // due_at
            Some("sentry_feedback"),       // source
            Some("high"),                  // priority
            Some(&metadata_str),           // metadata
            Some("bug"),                   // category
            Some(top_10_score),            // relevance_score
            None,                          // from_staged
            None,                          // recurrence_rule
            None,                          // recurrence_parent_id
        )
        .await
    {
        Ok(item) => {
            tracing::info!(
                "Sentry webhook: created action item {} for issue {}",
                item.id,
                issue_id
            );
            Ok(Json(WebhookResponse {
                status: "created".to_string(),
            }))
        }
        Err(e) => {
            tracing::error!(
                "Sentry webhook: failed to create action item for issue {}: {}",
                issue_id,
                e
            );
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

/// Fetch full event details from Sentry API for rich context
async fn fetch_sentry_event_details(
    state: &AppState,
    issue_id: &str,
    short_id: &str,
) -> (String, String, String, Option<Value>) {
    let auth_token = match &state.config.sentry_auth_token {
        Some(t) => t,
        None => {
            tracing::warn!("Sentry webhook: SENTRY_AUTH_TOKEN not set, skipping event fetch");
            return (String::new(), String::new(), String::new(), None);
        }
    };

    let url = format!(
        "https://sentry.io/api/0/issues/{}/events/latest/",
        issue_id
    );

    let client = reqwest::Client::new();
    let response = match client
        .get(&url)
        .header("Authorization", format!("Bearer {}", auth_token))
        .send()
        .await
    {
        Ok(r) => r,
        Err(e) => {
            tracing::error!("Sentry API request failed for issue {}: {}", issue_id, e);
            return (String::new(), String::new(), String::new(), None);
        }
    };

    if !response.status().is_success() {
        tracing::error!(
            "Sentry API returned {} for issue {}",
            response.status(),
            issue_id
        );
        return (String::new(), String::new(), String::new(), None);
    }

    let event: Value = match response.json().await {
        Ok(v) => v,
        Err(e) => {
            tracing::error!("Failed to parse Sentry event JSON for issue {}: {}", issue_id, e);
            return (String::new(), String::new(), String::new(), None);
        }
    };

    // Extract feedback message from context
    let feedback_message = event
        .pointer("/context/feedback/message")
        .or_else(|| event.pointer("/contexts/feedback/message"))
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();

    // Extract reporter info from context
    let reporter_name = event
        .pointer("/context/feedback/name")
        .or_else(|| event.pointer("/contexts/feedback/name"))
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();

    let reporter_email = event
        .pointer("/context/feedback/contact_email")
        .or_else(|| event.pointer("/contexts/feedback/contact_email"))
        .or_else(|| event.pointer("/user/email"))
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();

    // Build rich metadata from event
    let mut extra = json!({});

    // Tags (flatten to key-value map)
    if let Some(tags) = event.get("tags").and_then(|t| t.as_array()) {
        let mut tags_map = json!({});
        for tag in tags {
            if let (Some(key), Some(value)) = (
                tag.get("key").or_else(|| tag.get(0 as usize)).and_then(|v| v.as_str()),
                tag.get("value").or_else(|| tag.get(1 as usize)).and_then(|v| v.as_str()),
            ) {
                tags_map[key] = json!(value);
                // Also extract specific top-level fields from tags
                match key {
                    "app.version" | "version" => {
                        extra["app_version"] = json!(value);
                    }
                    "app.build" => {
                        extra["app_build"] = json!(value);
                    }
                    "os" | "os.name" => {
                        if extra.get("os").is_none() {
                            extra["os"] = json!(value);
                        }
                    }
                    "device.model" | "device" => {
                        extra["device_model"] = json!(value);
                    }
                    "environment" => {
                        extra["environment"] = json!(value);
                    }
                    _ => {}
                }
            }
        }
        extra["tags"] = tags_map;
    }

    // Contexts (device, os, app, etc.)
    if let Some(contexts) = event.get("contexts") {
        // Extract OS info
        if let Some(os) = contexts.get("os") {
            let os_name = os.get("name").and_then(|v| v.as_str()).unwrap_or("");
            let os_version = os.get("version").and_then(|v| v.as_str()).unwrap_or("");
            if !os_name.is_empty() {
                extra["os"] = json!(format!("{} {}", os_name, os_version).trim().to_string());
            }
        }

        // Extract device info
        if let Some(device) = contexts.get("device") {
            if let Some(model) = device.get("model").and_then(|v| v.as_str()) {
                extra["device_model"] = json!(model);
            }
        }

        // Extract app info
        if let Some(app) = contexts.get("app") {
            if let Some(version) = app.get("app_version").and_then(|v| v.as_str()) {
                extra["app_version"] = json!(version);
            }
            if let Some(build) = app.get("app_build").and_then(|v| v.as_str()) {
                extra["app_build"] = json!(build);
            }
        }

        extra["contexts"] = contexts.clone();
    }

    tracing::info!(
        "Sentry event details for {}: feedback='{}', reporter='{} <{}>'",
        short_id,
        feedback_message.chars().take(80).collect::<String>(),
        reporter_name,
        reporter_email,
    );

    (feedback_message, reporter_name, reporter_email, Some(extra))
}

/// POST /v1/webhooks/sentry/poll - Poll Sentry for new feedback and create action items
/// This is needed because Sentry webhooks don't fire for feedback category issues
/// (see https://github.com/getsentry/sentry/issues/89436)
async fn poll_sentry_feedback(
    State(state): State<AppState>,
) -> Result<Json<Value>, StatusCode> {
    let admin_uid = state
        .config
        .sentry_admin_uid
        .as_deref()
        .ok_or_else(|| {
            tracing::error!("Sentry poll: SENTRY_ADMIN_UID not configured");
            StatusCode::INTERNAL_SERVER_ERROR
        })?;

    let auth_token = state
        .config
        .sentry_auth_token
        .as_deref()
        .ok_or_else(|| {
            tracing::error!("Sentry poll: SENTRY_AUTH_TOKEN not configured");
            StatusCode::INTERNAL_SERVER_ERROR
        })?;

    tracing::info!("Sentry poll: fetching recent feedback issues");

    // 1. Fetch existing sentry_feedback action items to get already-processed issue IDs
    let existing_items = state
        .firestore
        .get_action_items(
            admin_uid,
            500,   // limit — must be large enough to include all sentry_feedback items
            0,     // offset
            None,  // completed_filter
            None,  // conversation_id
            None,  // start_date
            None,  // end_date
            None,  // due_start_date
            None,  // due_end_date
            None,  // sort_by
            None,  // include_deleted
        )
        .await
        .unwrap_or_default();

    // Extract sentry_issue_ids from existing action items' metadata
    let mut existing_issue_ids: std::collections::HashSet<String> = std::collections::HashSet::new();
    for item in &existing_items {
        if item.source.as_deref() != Some("sentry_feedback") {
            continue;
        }
        if let Some(meta_str) = &item.metadata {
            if let Ok(meta) = serde_json::from_str::<Value>(meta_str) {
                if let Some(id) = meta.get("sentry_issue_id").and_then(|v| v.as_str()) {
                    existing_issue_ids.insert(id.to_string());
                }
            }
        }
    }

    // Find the max relevance_score across all items to calculate dynamic top-10% score
    let max_relevance_score = existing_items
        .iter()
        .filter_map(|item| item.relevance_score)
        .max()
        .unwrap_or(100); // default if no scored tasks exist

    let top_10_score = std::cmp::max(1, (max_relevance_score as f64 * 0.1).round() as i32);

    tracing::info!(
        "Sentry poll: found {} existing sentry_feedback action items, max_score={}, top_10%_score={}",
        existing_issue_ids.len(),
        max_relevance_score,
        top_10_score,
    );

    // 2. Fetch recent feedback issues from Sentry
    let client = reqwest::Client::new();
    let sentry_url = "https://sentry.io/api/0/organizations/mediar-n5/issues/?query=issue.category:feedback&limit=25&sort=date";

    let response = client
        .get(sentry_url)
        .header("Authorization", format!("Bearer {}", auth_token))
        .send()
        .await
        .map_err(|e| {
            tracing::error!("Sentry poll: API request failed: {}", e);
            StatusCode::INTERNAL_SERVER_ERROR
        })?;

    if !response.status().is_success() {
        tracing::error!("Sentry poll: API returned {}", response.status());
        return Err(StatusCode::INTERNAL_SERVER_ERROR);
    }

    let issues: Vec<Value> = response.json().await.map_err(|e| {
        tracing::error!("Sentry poll: failed to parse issues: {}", e);
        StatusCode::INTERNAL_SERVER_ERROR
    })?;

    tracing::info!("Sentry poll: fetched {} feedback issues from Sentry", issues.len());

    // 3. Create action items for new issues
    let mut created = 0;
    let mut skipped = 0;

    for issue in &issues {
        let issue_id = issue.get("id").and_then(|v| v.as_str()).unwrap_or("");
        let short_id = issue.get("shortId").and_then(|v| v.as_str()).unwrap_or("unknown");

        if issue_id.is_empty() {
            continue;
        }

        // Skip if already processed
        if existing_issue_ids.contains(issue_id) {
            skipped += 1;
            continue;
        }

        let issue_title = issue.get("title").and_then(|v| v.as_str()).unwrap_or("");

        tracing::info!("Sentry poll: processing new feedback issue {} ({})", issue_id, short_id);

        // Fetch full event details
        let (feedback_message, reporter_name, reporter_email, metadata) =
            fetch_sentry_event_details(&state, issue_id, short_id).await;

        // Build description
        let description = if !feedback_message.is_empty() {
            format!("[Sentry Feedback] {}: {}", short_id, feedback_message)
        } else if !issue_title.is_empty() {
            format!("[Sentry Feedback] {}: {}", short_id, issue_title)
        } else {
            format!("[Sentry Feedback] {}", short_id)
        };

        // Build metadata JSON
        let mut meta = json!({
            "sentry_issue_id": issue_id,
            "sentry_short_id": short_id,
            "sentry_url": format!("https://mediar-n5.sentry.io/issues/{}/", issue_id),
            "tags": ["bug"],
        });

        if !reporter_name.is_empty() {
            meta["reporter_name"] = json!(reporter_name);
        }
        if !reporter_email.is_empty() {
            meta["reporter_email"] = json!(reporter_email);
        }
        if let Some(extra) = metadata {
            if let Value::Object(extra_map) = extra {
                if let Value::Object(ref mut meta_map) = meta {
                    for (k, v) in extra_map {
                        meta_map.insert(k, v);
                    }
                }
            }
        }

        let metadata_str = serde_json::to_string(&meta).unwrap_or_default();

        match state
            .firestore
            .create_action_item(
                admin_uid,
                &description,
                None,
                Some("sentry_feedback"),
                Some("high"),
                Some(&metadata_str),
                Some("bug"),
                Some(top_10_score),
                None, // from_staged
                None, // recurrence_rule
                None, // recurrence_parent_id
            )
            .await
        {
            Ok(item) => {
                tracing::info!(
                    "Sentry poll: created action item {} for issue {} ({})",
                    item.id,
                    issue_id,
                    short_id
                );
                created += 1;
            }
            Err(e) => {
                tracing::error!(
                    "Sentry poll: failed to create action item for issue {}: {}",
                    issue_id,
                    e
                );
            }
        }
    }

    tracing::info!(
        "Sentry poll: done. created={}, skipped={} (already existed), total_fetched={}",
        created,
        skipped,
        issues.len()
    );

    Ok(Json(json!({
        "status": "ok",
        "created": created,
        "skipped": skipped,
        "total_fetched": issues.len()
    })))
}

pub fn webhook_routes() -> Router<AppState> {
    Router::new()
        .route("/v1/webhooks/sentry", post(handle_sentry_webhook))
        .route("/v1/webhooks/sentry/poll", post(poll_sentry_feedback))
}
