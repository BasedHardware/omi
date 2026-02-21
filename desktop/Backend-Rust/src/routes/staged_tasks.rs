// Staged Tasks routes
// Endpoints: POST/GET /v1/staged-tasks, DELETE /v1/staged-tasks/{id},
//            PATCH /v1/staged-tasks/batch-scores, POST /v1/staged-tasks/promote

use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    routing::{get, patch, post},
    Json, Router,
};
use serde::Deserialize;

use crate::auth::AuthUser;
use crate::models::{
    ActionItemDB, ActionItemStatusResponse, ActionItemsListResponse, BatchUpdateScoresRequest,
    CreateActionItemRequest, PromoteResponse,
};
use crate::AppState;

#[derive(Deserialize)]
pub struct GetStagedTasksQuery {
    #[serde(default = "default_limit")]
    pub limit: usize,
    #[serde(default)]
    pub offset: usize,
}

fn default_limit() -> usize {
    100
}

/// POST /v1/staged-tasks - Create a new staged task
async fn create_staged_task(
    State(state): State<AppState>,
    user: AuthUser,
    Json(request): Json<CreateActionItemRequest>,
) -> Result<Json<ActionItemDB>, StatusCode> {
    tracing::info!(
        "Creating staged task for user {} with source={:?}",
        user.uid,
        request.source
    );

    match state
        .firestore
        .create_staged_task(
            &user.uid,
            &request.description,
            request.due_at,
            request.source.as_deref(),
            request.priority.as_deref(),
            request.metadata.as_deref(),
            request.category.as_deref(),
            request.relevance_score,
        )
        .await
    {
        Ok(item) => Ok(Json(item)),
        Err(e) => {
            tracing::error!("Failed to create staged task: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

/// GET /v1/staged-tasks - List staged tasks ordered by relevance_score ASC
async fn get_staged_tasks(
    State(state): State<AppState>,
    user: AuthUser,
    Query(query): Query<GetStagedTasksQuery>,
) -> Json<ActionItemsListResponse> {
    tracing::info!(
        "Getting staged tasks for user {} with limit={}, offset={}",
        user.uid,
        query.limit,
        query.offset
    );

    let fetch_limit = query.limit + 1;

    match state
        .firestore
        .get_staged_tasks(&user.uid, fetch_limit, query.offset)
        .await
    {
        Ok(mut items) => {
            let has_more = items.len() > query.limit;
            if has_more {
                items.truncate(query.limit);
            }
            Json(ActionItemsListResponse { items, has_more })
        }
        Err(e) => {
            tracing::error!("Failed to get staged tasks: {}", e);
            Json(ActionItemsListResponse {
                items: vec![],
                has_more: false,
            })
        }
    }
}

/// DELETE /v1/staged-tasks/{id} - Hard-delete a staged task
async fn delete_staged_task(
    State(state): State<AppState>,
    user: AuthUser,
    Path(item_id): Path<String>,
) -> Result<Json<ActionItemStatusResponse>, StatusCode> {
    tracing::info!("Deleting staged task {} for user {}", item_id, user.uid);

    match state
        .firestore
        .delete_staged_task(&user.uid, &item_id)
        .await
    {
        Ok(()) => Ok(Json(ActionItemStatusResponse {
            status: "ok".to_string(),
        })),
        Err(e) => {
            tracing::error!("Failed to delete staged task: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

/// PATCH /v1/staged-tasks/batch-scores - Batch update relevance scores
async fn batch_update_staged_scores(
    State(state): State<AppState>,
    user: AuthUser,
    Json(request): Json<BatchUpdateScoresRequest>,
) -> Result<Json<ActionItemStatusResponse>, StatusCode> {
    tracing::info!(
        "Batch updating {} staged task scores for user {}",
        request.scores.len(),
        user.uid
    );

    let scores: Vec<(String, i32)> = request
        .scores
        .into_iter()
        .map(|s| (s.id, s.relevance_score))
        .collect();

    match state
        .firestore
        .batch_update_staged_scores(&user.uid, &scores)
        .await
    {
        Ok(()) => Ok(Json(ActionItemStatusResponse {
            status: "ok".to_string(),
        })),
        Err(e) => {
            tracing::error!("Failed to batch update staged scores: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

/// POST /v1/staged-tasks/promote - Promote top staged task to action_items
///
/// 1. Get active AI action_items (from_staged=true, !completed, !deleted)
/// 2. If >= 5, return { promoted: false }
/// 3. Get top-ranked staged tasks (batch of 10 for dedup)
/// 4. Skip any whose description already exists in active action_items
/// 5. Create in action_items with from_staged=true
/// 6. Hard-delete from staged_tasks (including skipped duplicates)
/// 7. Return { promoted: true, promoted_task }
async fn promote_staged_task(
    State(state): State<AppState>,
    user: AuthUser,
) -> Result<Json<PromoteResponse>, StatusCode> {
    tracing::info!("Promote staged task requested for user {}", user.uid);

    // Step 1: Get active AI tasks and their descriptions for dedup
    let active_ai_items = match state
        .firestore
        .get_active_ai_action_items(&user.uid)
        .await
    {
        Ok(items) => items,
        Err(e) => {
            tracing::error!("Failed to get active AI items: {}", e);
            return Err(StatusCode::INTERNAL_SERVER_ERROR);
        }
    };

    let active_count = active_ai_items.len();
    tracing::info!(
        "User {} has {} active AI tasks in action_items",
        user.uid,
        active_count
    );
    if active_count >= 5 {
        return Ok(Json(PromoteResponse {
            promoted: false,
            reason: Some(format!("Already have {} active AI tasks (max 5)", active_count)),
            promoted_task: None,
        }));
    }

    // Build set of existing descriptions for dedup (strip [screen] suffix for comparison)
    let existing_descriptions: std::collections::HashSet<String> = active_ai_items
        .iter()
        .map(|item| {
            item.description
                .trim_start_matches("[screen] ")
                .trim_end_matches(" [screen]")
                .to_lowercase()
        })
        .collect();

    // Step 2: Get top-ranked staged tasks (fetch a batch for dedup skipping)
    let staged_tasks = match state.firestore.get_staged_tasks(&user.uid, 20, 0).await {
        Ok(tasks) => tasks,
        Err(e) => {
            tracing::error!("Failed to get staged tasks: {}", e);
            return Err(StatusCode::INTERNAL_SERVER_ERROR);
        }
    };

    if staged_tasks.is_empty() {
        return Ok(Json(PromoteResponse {
            promoted: false,
            reason: Some("No staged tasks available".to_string()),
            promoted_task: None,
        }));
    }

    // Step 3: Find first non-duplicate task, deleting duplicates along the way
    // Also track descriptions we've seen within this batch to deduplicate staged_tasks internally
    let mut selected_task = None;
    let mut seen_descriptions: std::collections::HashSet<String> = std::collections::HashSet::new();
    let mut duplicate_ids: Vec<String> = Vec::new();

    for task in staged_tasks {
        let normalized = task
            .description
            .trim_start_matches("[screen] ")
            .trim_end_matches(" [screen]")
            .to_lowercase();

        if existing_descriptions.contains(&normalized) || seen_descriptions.contains(&normalized) {
            // Duplicate of action_items OR duplicate within staged_tasks — mark for deletion
            tracing::info!(
                "Skipping duplicate staged task {} (\"{}\")",
                task.id,
                task.description
            );
            duplicate_ids.push(task.id.clone());
            continue;
        }

        seen_descriptions.insert(normalized);

        if selected_task.is_none() {
            selected_task = Some(task);
        } else {
            // Already found our candidate — keep scanning for duplicates to clean up
        }
    }

    // Clean up all duplicates in the background
    for dup_id in &duplicate_ids {
        let _ = state
            .firestore
            .delete_staged_task(&user.uid, dup_id)
            .await;
    }
    if !duplicate_ids.is_empty() {
        tracing::info!(
            "Cleaned up {} duplicate staged tasks for user {}",
            duplicate_ids.len(),
            user.uid
        );
    }

    let top_task = match selected_task {
        Some(task) => task,
        None => {
            return Ok(Json(PromoteResponse {
                promoted: false,
                reason: Some("All candidate staged tasks are duplicates".to_string()),
                promoted_task: None,
            }));
        }
    };

    // Step 4: Create in action_items (from_staged=true marks it as promoted)
    let promoted_item = match state
        .firestore
        .create_action_item(
            &user.uid,
            &top_task.description,
            top_task.due_at,
            top_task.source.as_deref(),
            top_task.priority.as_deref(),
            top_task.metadata.as_deref(),
            top_task.category.as_deref(),
            top_task.relevance_score,
            Some(true), // from_staged: promoted from staged_tasks
            None, // recurrence_rule
            None, // recurrence_parent_id
        )
        .await
    {
        Ok(item) => item,
        Err(e) => {
            tracing::error!("Failed to create promoted action item: {}", e);
            return Err(StatusCode::INTERNAL_SERVER_ERROR);
        }
    };

    // Step 5: Hard-delete from staged_tasks
    if let Err(e) = state
        .firestore
        .delete_staged_task(&user.uid, &top_task.id)
        .await
    {
        tracing::error!(
            "Failed to delete staged task {} after promotion: {}",
            top_task.id,
            e
        );
    }

    tracing::info!(
        "Promoted staged task {} -> action item {} for user {}",
        top_task.id,
        promoted_item.id,
        user.uid
    );

    Ok(Json(PromoteResponse {
        promoted: true,
        reason: None,
        promoted_task: Some(promoted_item),
    }))
}

/// POST /v1/staged-tasks/migrate - One-time migration of existing AI tasks
///
/// Moves excess AI tasks from action_items to staged_tasks using batch commits.
/// Keeps top 5 in action_items, prefixes with [screen].
async fn migrate_ai_tasks(
    State(state): State<AppState>,
    user: AuthUser,
) -> Result<Json<ActionItemStatusResponse>, StatusCode> {
    tracing::info!("Migrating AI tasks for user {}", user.uid);

    // Get all non-completed, non-deleted action items (paginate to get everything)
    let mut all_items: Vec<ActionItemDB> = Vec::new();
    let mut offset = 0;
    let batch_size = 500;
    loop {
        match state
            .firestore
            .get_action_items(
                &user.uid,
                batch_size,
                offset,
                Some(false), // not completed
                None,
                None,
                None,
                None,
                None,
                None,
                None, // not deleted (default)
            )
            .await
        {
            Ok(items) => {
                let count = items.len();
                all_items.extend(items);
                if count < batch_size {
                    break;
                }
                offset += count;
            }
            Err(e) => {
                tracing::error!("Failed to get action items for migration: {}", e);
                return Err(StatusCode::INTERNAL_SERVER_ERROR);
            }
        }
    }

    tracing::info!(
        "Migration: fetched {} total active action items for user {}",
        all_items.len(),
        user.uid
    );

    // Filter to AI tasks (source contains "screenshot")
    let mut ai_tasks: Vec<ActionItemDB> = all_items
        .into_iter()
        .filter(|item| {
            item.source
                .as_ref()
                .map_or(false, |s| s.contains("screenshot"))
        })
        .collect();

    tracing::info!(
        "Migration: found {} AI (screenshot) tasks for user {}",
        ai_tasks.len(),
        user.uid
    );

    if ai_tasks.is_empty() {
        return Ok(Json(ActionItemStatusResponse {
            status: "ok".to_string(),
        }));
    }

    // Sort by relevance_score ASC (best first)
    ai_tasks.sort_by(|a, b| {
        let score_a = a.relevance_score.unwrap_or(i32::MAX);
        let score_b = b.relevance_score.unwrap_or(i32::MAX);
        score_a.cmp(&score_b)
    });

    // Tag top 5 with [screen] suffix (small number, do individually)
    for task in ai_tasks.iter().take(5) {
        if !task.description.ends_with(" [screen]") && !task.description.starts_with("[screen] ") {
            let prefixed = format!("{} [screen]", task.description);
            if let Err(e) = state
                .firestore
                .update_action_item(
                    &user.uid,
                    &task.id,
                    None,
                    Some(&prefixed),
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None, // recurrence_rule
                )
                .await
            {
                tracing::error!("Failed to prefix task {}: {}", task.id, e);
            }
        }
    }

    // Move the rest via batch commits: create in staged_tasks + delete from action_items
    let tasks_to_move: Vec<ActionItemDB> = ai_tasks.into_iter().skip(5).collect();
    if tasks_to_move.is_empty() {
        tracing::info!("Migration: only 5 or fewer AI tasks, nothing to move");
        return Ok(Json(ActionItemStatusResponse {
            status: "ok".to_string(),
        }));
    }

    tracing::info!("Migration: moving {} AI tasks via batch commits", tasks_to_move.len());

    let migrated_count = match state
        .firestore
        .batch_migrate_to_staged(&user.uid, &tasks_to_move)
        .await
    {
        Ok(count) => count,
        Err(e) => {
            tracing::error!("Migration batch commit failed: {}", e);
            return Err(StatusCode::INTERNAL_SERVER_ERROR);
        }
    };

    tracing::info!(
        "Migration complete: {} AI tasks moved to staged_tasks for user {}",
        migrated_count,
        user.uid
    );

    Ok(Json(ActionItemStatusResponse {
        status: "ok".to_string(),
    }))
}

/// POST /v1/staged-tasks/migrate-conversation-items
/// Migrates action items created by the old conversation extraction path
/// (have conversation_id but no source) to staged_tasks.
/// Idempotent — safe to call multiple times.
async fn migrate_conversation_items(
    State(state): State<AppState>,
    user: AuthUser,
) -> Result<Json<serde_json::Value>, StatusCode> {
    match state
        .firestore
        .migrate_conversation_action_items_to_staged(&user.uid)
        .await
    {
        Ok((migrated, deleted)) => Ok(Json(serde_json::json!({
            "status": "ok",
            "migrated": migrated,
            "deleted": deleted
        }))),
        Err(e) => {
            tracing::error!("Failed to migrate conversation items: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

pub fn staged_tasks_routes() -> Router<AppState> {
    Router::new()
        .route(
            "/v1/staged-tasks",
            get(get_staged_tasks).post(create_staged_task),
        )
        .route("/v1/staged-tasks/batch-scores", patch(batch_update_staged_scores))
        .route("/v1/staged-tasks/promote", post(promote_staged_task))
        .route("/v1/staged-tasks/migrate", post(migrate_ai_tasks))
        .route("/v1/staged-tasks/migrate-conversation-items", post(migrate_conversation_items))
        .route("/v1/staged-tasks/:id", axum::routing::delete(delete_staged_task))
}
