// Action Items routes
// Endpoints: GET /v1/action-items, PATCH/DELETE /v1/action-items/{id}

use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    routing::get,
    Json, Router,
};
use serde::Deserialize;

use crate::auth::AuthUser;
use crate::models::{AcceptTasksRequest, AcceptTasksResponse, ActionItemDB, ActionItemsListResponse, ActionItemStatusResponse, BatchCreateActionItemsRequest, BatchUpdateScoresRequest, BatchUpdateSortOrdersRequest, CreateActionItemRequest, ShareTasksRequest, ShareTasksResponse, SharedTaskInfo, SharedTasksResponse, UpdateActionItemRequest};
use crate::AppState;

#[derive(Deserialize)]
pub struct SoftDeleteActionItemRequest {
    /// Who is deleting: "ai_dedup", "user"
    pub deleted_by: String,
    /// Reason for deletion (optional for user-initiated deletes)
    #[serde(default)]
    pub reason: Option<String>,
    /// ID of the task that was kept instead (optional for user-initiated deletes)
    #[serde(default)]
    pub kept_task_id: Option<String>,
}

#[derive(Deserialize)]
pub struct GetActionItemsQuery {
    #[serde(default = "default_limit")]
    pub limit: usize,
    #[serde(default)]
    pub offset: usize,
    /// Optional filter: true = completed only, false = pending only, None = all
    pub completed: Option<bool>,
    /// Optional filter by conversation ID
    pub conversation_id: Option<String>,
    /// ISO8601 date - filter created_at >= start_date
    pub start_date: Option<String>,
    /// ISO8601 date - filter created_at <= end_date
    pub end_date: Option<String>,
    /// ISO8601 date - filter due_at >= due_start_date
    pub due_start_date: Option<String>,
    /// ISO8601 date - filter due_at <= due_end_date
    pub due_end_date: Option<String>,
    /// Sort field: "due_at", "created_at", "priority" (default: created_at DESC)
    pub sort_by: Option<String>,
    /// If true, return ONLY soft-deleted items. Default: exclude deleted items.
    pub deleted: Option<bool>,
}

fn default_limit() -> usize {
    100
}

/// POST /v1/action-items - Create a new action item
async fn create_action_item(
    State(state): State<AppState>,
    user: AuthUser,
    Json(request): Json<CreateActionItemRequest>,
) -> Result<Json<ActionItemDB>, StatusCode> {
    tracing::info!(
        "Creating action item for user {} with source={:?}, priority={:?}",
        user.uid,
        request.source,
        request.priority
    );

    match state
        .firestore
        .create_action_item(
            &user.uid,
            &request.description,
            request.due_at,
            request.source.as_deref(),
            request.priority.as_deref(),
            request.metadata.as_deref(),
            request.category.as_deref(),
            request.relevance_score,
            None, // from_staged
            request.recurrence_rule.as_deref(),
            request.recurrence_parent_id.as_deref(),
        )
        .await
    {
        Ok(item) => Ok(Json(item)),
        Err(e) => {
            tracing::error!("Failed to create action item: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

/// GET /v1/action-items - Fetch user action items
async fn get_action_items(
    State(state): State<AppState>,
    user: AuthUser,
    Query(query): Query<GetActionItemsQuery>,
) -> Json<ActionItemsListResponse> {
    tracing::info!(
        "Getting action items for user {} with limit={}, offset={}, completed={:?}, conversation_id={:?}, sort_by={:?}, deleted={:?}",
        user.uid,
        query.limit,
        query.offset,
        query.completed,
        query.conversation_id,
        query.sort_by,
        query.deleted
    );

    // Fetch limit + 1 to determine if there are more items
    let fetch_limit = query.limit + 1;

    match state
        .firestore
        .get_action_items(
            &user.uid,
            fetch_limit,
            query.offset,
            query.completed,
            query.conversation_id.as_deref(),
            query.start_date.as_deref(),
            query.end_date.as_deref(),
            query.due_start_date.as_deref(),
            query.due_end_date.as_deref(),
            query.sort_by.as_deref(),
            query.deleted,
        )
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
            tracing::error!("Failed to get action items: {}", e);
            Json(ActionItemsListResponse {
                items: vec![],
                has_more: false,
            })
        }
    }
}

/// GET /v1/action-items/{id} - Get a single action item
async fn get_action_item_by_id(
    State(state): State<AppState>,
    user: AuthUser,
    Path(item_id): Path<String>,
) -> Result<Json<ActionItemDB>, StatusCode> {
    tracing::info!("Getting action item {} for user {}", item_id, user.uid);

    match state.firestore.get_action_item_by_id(&user.uid, &item_id).await {
        Ok(Some(item)) => Ok(Json(item)),
        Ok(None) => Err(StatusCode::NOT_FOUND),
        Err(e) => {
            tracing::error!("Failed to get action item: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

/// PATCH /v1/action-items/{id} - Update an action item
async fn update_action_item(
    State(state): State<AppState>,
    user: AuthUser,
    Path(item_id): Path<String>,
    Json(request): Json<UpdateActionItemRequest>,
) -> Result<Json<ActionItemDB>, StatusCode> {
    tracing::info!("Updating action item {} for user {}", item_id, user.uid);

    match state
        .firestore
        .update_action_item(
            &user.uid,
            &item_id,
            request.completed,
            request.description.as_deref(),
            request.due_at,
            request.priority.as_deref(),
            request.category.as_deref(),
            request.goal_id.as_deref(),
            request.relevance_score,
            request.sort_order,
            request.indent_level,
            request.recurrence_rule.as_deref(),
        )
        .await
    {
        Ok(item) => Ok(Json(item)),
        Err(e) => {
            tracing::error!("Failed to update action item: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

/// POST /v1/action-items/batch - Create multiple action items at once
async fn batch_create_action_items(
    State(state): State<AppState>,
    user: AuthUser,
    Json(request): Json<BatchCreateActionItemsRequest>,
) -> Result<Json<Vec<ActionItemDB>>, StatusCode> {
    tracing::info!(
        "Batch creating {} action items for user {}",
        request.items.len(),
        user.uid
    );

    let mut created_items = Vec::new();

    for item_request in request.items {
        match state
            .firestore
            .create_action_item(
                &user.uid,
                &item_request.description,
                item_request.due_at,
                item_request.source.as_deref(),
                item_request.priority.as_deref(),
                item_request.metadata.as_deref(),
                item_request.category.as_deref(),
                item_request.relevance_score,
                None, // from_staged
                item_request.recurrence_rule.as_deref(),
                item_request.recurrence_parent_id.as_deref(),
            )
            .await
        {
            Ok(item) => created_items.push(item),
            Err(e) => {
                tracing::error!("Failed to create action item in batch: {}", e);
                // Continue with other items, don't fail the whole batch
            }
        }
    }

    Ok(Json(created_items))
}

/// PATCH /v1/action-items/batch - Batch update sort orders and indent levels
async fn batch_update_sort_orders(
    State(state): State<AppState>,
    user: AuthUser,
    Json(request): Json<BatchUpdateSortOrdersRequest>,
) -> Result<Json<ActionItemStatusResponse>, StatusCode> {
    tracing::info!(
        "Batch updating {} sort orders for user {}",
        request.items.len(),
        user.uid
    );

    let items: Vec<(String, i32, i32)> = request
        .items
        .into_iter()
        .map(|s| (s.id, s.sort_order, s.indent_level))
        .collect();

    match state.firestore.batch_update_sort_orders(&user.uid, &items).await {
        Ok(()) => Ok(Json(ActionItemStatusResponse {
            status: "ok".to_string(),
        })),
        Err(e) => {
            tracing::error!("Failed to batch update sort orders: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

/// DELETE /v1/action-items/{id} - Delete an action item
async fn delete_action_item(
    State(state): State<AppState>,
    user: AuthUser,
    Path(item_id): Path<String>,
) -> Result<Json<ActionItemStatusResponse>, StatusCode> {
    tracing::info!("Deleting action item {} for user {}", item_id, user.uid);

    match state.firestore.delete_action_item(&user.uid, &item_id).await {
        Ok(()) => Ok(Json(ActionItemStatusResponse {
            status: "ok".to_string(),
        })),
        Err(e) => {
            tracing::error!("Failed to delete action item: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

/// POST /v1/action-items/{id}/soft-delete - Soft-delete an action item (mark as deleted)
async fn soft_delete_action_item(
    State(state): State<AppState>,
    user: AuthUser,
    Path(item_id): Path<String>,
    Json(request): Json<SoftDeleteActionItemRequest>,
) -> Result<Json<ActionItemDB>, StatusCode> {
    let reason = request.reason.as_deref().unwrap_or("");
    let kept_task_id = request.kept_task_id.as_deref().unwrap_or("");

    tracing::info!(
        "Soft-deleting action item {} for user {} (by: {}, reason: {})",
        item_id,
        user.uid,
        request.deleted_by,
        reason
    );

    match state
        .firestore
        .soft_delete_action_item(
            &user.uid,
            &item_id,
            &request.deleted_by,
            reason,
            kept_task_id,
        )
        .await
    {
        Ok(item) => Ok(Json(item)),
        Err(e) => {
            tracing::error!("Failed to soft-delete action item: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

/// PATCH /v1/action-items/batch-scores - Batch update relevance scores
async fn batch_update_scores(
    State(state): State<AppState>,
    user: AuthUser,
    Json(request): Json<BatchUpdateScoresRequest>,
) -> Result<Json<ActionItemStatusResponse>, StatusCode> {
    tracing::info!(
        "Batch updating {} relevance scores for user {}",
        request.scores.len(),
        user.uid
    );

    let scores: Vec<(String, i32)> = request
        .scores
        .into_iter()
        .map(|s| (s.id, s.relevance_score))
        .collect();

    match state.firestore.batch_update_scores(&user.uid, &scores).await {
        Ok(()) => Ok(Json(ActionItemStatusResponse {
            status: "ok".to_string(),
        })),
        Err(e) => {
            tracing::error!("Failed to batch update scores: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

/// POST /v1/action-items/share - Share tasks via a link
async fn share_tasks(
    State(state): State<AppState>,
    user: AuthUser,
    Json(request): Json<ShareTasksRequest>,
) -> Result<Json<ShareTasksResponse>, StatusCode> {
    let task_count = request.task_ids.len();
    if task_count == 0 || task_count > 20 {
        tracing::warn!("Invalid task_ids count: {}", task_count);
        return Err(StatusCode::BAD_REQUEST);
    }

    // Verify ownership of each task
    for id in &request.task_ids {
        match state.firestore.get_action_item_by_id(&user.uid, id).await {
            Ok(Some(_)) => {}
            Ok(None) => {
                tracing::warn!("Task {} not found for user {}", id, user.uid);
                return Err(StatusCode::NOT_FOUND);
            }
            Err(e) => {
                tracing::error!("Failed to verify task ownership: {}", e);
                return Err(StatusCode::INTERNAL_SERVER_ERROR);
            }
        }
    }

    // Get sender display name from Firebase token
    let display_name = user.name.clone().unwrap_or_else(|| "Someone".to_string());

    // Generate token and store in Redis
    let token = uuid::Uuid::new_v4().simple().to_string();

    if let Some(redis) = &state.redis {
        if let Err(e) = redis.store_task_share(&token, &user.uid, &display_name, &request.task_ids).await {
            tracing::error!("Failed to store task share in Redis: {}", e);
            return Err(StatusCode::INTERNAL_SERVER_ERROR);
        }
    } else {
        tracing::error!("Redis not configured");
        return Err(StatusCode::INTERNAL_SERVER_ERROR);
    }

    let url = format!("https://h.omi.me/tasks/{}", token);
    tracing::info!("User {} shared {} tasks, token={}", user.uid, task_count, token);

    Ok(Json(ShareTasksResponse { url, token }))
}

/// GET /v1/action-items/shared/:token - Get shared tasks (public, no auth)
async fn get_shared_tasks(
    State(state): State<AppState>,
    Path(token): Path<String>,
) -> Result<Json<SharedTasksResponse>, StatusCode> {
    let redis = state.redis.as_ref().ok_or(StatusCode::INTERNAL_SERVER_ERROR)?;

    let (sender_uid, sender_name, task_ids) = match redis.get_task_share(&token).await {
        Ok(Some(data)) => data,
        Ok(None) => return Err(StatusCode::NOT_FOUND),
        Err(e) => {
            tracing::error!("Failed to get task share from Redis: {}", e);
            return Err(StatusCode::INTERNAL_SERVER_ERROR);
        }
    };

    // Fetch each task from sender's Firestore (only expose description + due_at)
    let mut tasks = Vec::new();
    for id in &task_ids {
        match state.firestore.get_action_item_by_id(&sender_uid, id).await {
            Ok(Some(item)) => {
                tasks.push(SharedTaskInfo {
                    description: item.description,
                    due_at: item.due_at,
                });
            }
            _ => {
                // Task may have been deleted since sharing — skip it
            }
        }
    }

    let count = tasks.len();
    Ok(Json(SharedTasksResponse {
        sender_name,
        tasks,
        count,
    }))
}

/// POST /v1/action-items/accept - Accept shared tasks (authenticated)
async fn accept_tasks(
    State(state): State<AppState>,
    user: AuthUser,
    Json(request): Json<AcceptTasksRequest>,
) -> Result<Json<AcceptTasksResponse>, StatusCode> {
    let redis = state.redis.as_ref().ok_or(StatusCode::INTERNAL_SERVER_ERROR)?;

    let (sender_uid, _sender_name, task_ids) = match redis.get_task_share(&request.token).await {
        Ok(Some(data)) => data,
        Ok(None) => return Err(StatusCode::NOT_FOUND),
        Err(e) => {
            tracing::error!("Failed to get task share from Redis: {}", e);
            return Err(StatusCode::INTERNAL_SERVER_ERROR);
        }
    };

    // Block self-accept
    if sender_uid == user.uid {
        return Err(StatusCode::BAD_REQUEST);
    }

    // Atomic accept — prevent double-accept
    match redis.try_accept_task_share(&request.token, &user.uid).await {
        Ok(true) => {} // newly accepted
        Ok(false) => return Err(StatusCode::CONFLICT), // already accepted
        Err(e) => {
            tracing::error!("Failed to accept task share: {}", e);
            return Err(StatusCode::INTERNAL_SERVER_ERROR);
        }
    }

    // Create tasks in recipient's Firestore
    let mut created_ids = Vec::new();
    for id in &task_ids {
        match state.firestore.get_action_item_by_id(&sender_uid, id).await {
            Ok(Some(item)) => {
                let metadata = serde_json::json!({
                    "shared_from": sender_uid,
                    "share_token": request.token,
                })
                .to_string();

                match state
                    .firestore
                    .create_action_item(
                        &user.uid,
                        &item.description,
                        item.due_at,
                        Some("shared"),
                        item.priority.as_deref(),
                        Some(&metadata),
                        item.category.as_deref(),
                        item.relevance_score,
                        None, // from_staged
                        None, // recurrence_rule
                        None, // recurrence_parent_id
                    )
                    .await
                {
                    Ok(new_item) => created_ids.push(new_item.id),
                    Err(e) => {
                        tracing::error!("Failed to create shared task: {}", e);
                    }
                }
            }
            _ => {} // skip deleted tasks
        }
    }

    let count = created_ids.len();
    tracing::info!(
        "User {} accepted {} tasks from share token={}",
        user.uid,
        count,
        request.token
    );

    Ok(Json(AcceptTasksResponse {
        created: created_ids,
        count,
    }))
}

pub fn action_items_routes() -> Router<AppState> {
    Router::new()
        .route("/v1/action-items", get(get_action_items).post(create_action_item))
        .route("/v1/action-items/batch", axum::routing::post(batch_create_action_items).patch(batch_update_sort_orders))
        .route("/v1/action-items/batch-scores", axum::routing::patch(batch_update_scores))
        .route("/v1/action-items/share", axum::routing::post(share_tasks))
        .route("/v1/action-items/shared/:token", get(get_shared_tasks))
        .route("/v1/action-items/accept", axum::routing::post(accept_tasks))
        .route(
            "/v1/action-items/:id",
            get(get_action_item_by_id).patch(update_action_item).delete(delete_action_item),
        )
        .route(
            "/v1/action-items/:id/soft-delete",
            axum::routing::post(soft_delete_action_item),
        )
}
