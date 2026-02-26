// Goals routes
// Endpoints: GET /v1/goals/all, POST /v1/goals, PATCH /v1/goals/:id, PATCH /v1/goals/:id/progress, DELETE /v1/goals/:id

use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    routing::{get, patch, post},
    Json, Router,
};

use crate::auth::AuthUser;
use crate::models::{
    CreateGoalRequest, GoalDB, GoalHistoryQuery, GoalHistoryResponse, GoalStatusResponse, GoalType,
    GoalsListResponse, UpdateGoalProgressQuery, UpdateGoalRequest,
};
use crate::AppState;

/// GET /v1/goals/completed - Get completed goals for history
async fn get_completed_goals(
    State(state): State<AppState>,
    user: AuthUser,
) -> Result<Json<GoalsListResponse>, StatusCode> {
    tracing::info!("Getting completed goals for user {}", user.uid);

    match state.firestore.get_completed_goals(&user.uid, 50).await {
        Ok(goals) => Ok(Json(GoalsListResponse { goals })),
        Err(e) => {
            tracing::error!("Failed to get completed goals: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

/// GET /v1/goals/all - Get all active goals (up to 3)
async fn get_all_goals(
    State(state): State<AppState>,
    user: AuthUser,
) -> Result<Json<GoalsListResponse>, StatusCode> {
    tracing::info!("Getting all goals for user {}", user.uid);

    match state.firestore.get_user_goals(&user.uid, 3).await {
        Ok(goals) => Ok(Json(GoalsListResponse { goals })),
        Err(e) => {
            tracing::error!("Failed to get goals: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

/// POST /v1/goals - Create a new goal
async fn create_goal(
    State(state): State<AppState>,
    user: AuthUser,
    Json(request): Json<CreateGoalRequest>,
) -> Result<Json<GoalDB>, StatusCode> {
    tracing::info!(
        "Creating goal '{}' for user {} with type={:?}",
        request.title,
        user.uid,
        request.goal_type
    );

    let target_value = request.target_value.unwrap_or_else(|| {
        match request.goal_type {
            GoalType::Boolean => 1.0,
            _ => 100.0,
        }
    });

    match state
        .firestore
        .create_goal(
            &user.uid,
            &request.title,
            request.description.as_deref(),
            request.goal_type,
            target_value,
            request.current_value.unwrap_or(0.0),
            request.min_value.unwrap_or(0.0),
            request.max_value.unwrap_or(100.0),
            request.unit.as_deref(),
            request.source.as_deref(),
        )
        .await
    {
        Ok(goal) => Ok(Json(goal)),
        Err(e) => {
            tracing::error!("Failed to create goal: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

/// PATCH /v1/goals/:id - Update a goal
async fn update_goal(
    State(state): State<AppState>,
    user: AuthUser,
    Path(goal_id): Path<String>,
    Json(request): Json<UpdateGoalRequest>,
) -> Result<Json<GoalDB>, StatusCode> {
    tracing::info!("Updating goal {} for user {}", goal_id, user.uid);

    let completed_at = request.completed_at.as_ref().and_then(|s| {
        chrono::DateTime::parse_from_rfc3339(s).ok().map(|dt| dt.with_timezone(&chrono::Utc))
    });

    match state
        .firestore
        .update_goal(
            &user.uid,
            &goal_id,
            request.title.as_deref(),
            request.description.as_deref(),
            request.target_value,
            request.current_value,
            request.min_value,
            request.max_value,
            request.unit.as_deref(),
            request.is_active,
            completed_at,
        )
        .await
    {
        Ok(goal) => Ok(Json(goal)),
        Err(e) => {
            tracing::error!("Failed to update goal: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

/// PATCH /v1/goals/:id/progress - Update goal progress
async fn update_goal_progress(
    State(state): State<AppState>,
    user: AuthUser,
    Path(goal_id): Path<String>,
    Query(query): Query<UpdateGoalProgressQuery>,
) -> Result<Json<GoalDB>, StatusCode> {
    tracing::info!(
        "Updating progress for goal {} to {} for user {}",
        goal_id,
        query.current_value,
        user.uid
    );

    match state
        .firestore
        .update_goal_progress(&user.uid, &goal_id, query.current_value)
        .await
    {
        Ok(goal) => Ok(Json(goal)),
        Err(e) => {
            tracing::error!("Failed to update goal progress: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

/// GET /v1/goals/:id/history - Get progress history for a goal
async fn get_goal_history(
    State(state): State<AppState>,
    user: AuthUser,
    Path(goal_id): Path<String>,
    Query(query): Query<GoalHistoryQuery>,
) -> Result<Json<GoalHistoryResponse>, StatusCode> {
    tracing::info!(
        "Getting history for goal {} (days={}) for user {}",
        goal_id,
        query.days,
        user.uid
    );

    match state
        .firestore
        .get_goal_history(&user.uid, &goal_id, query.days)
        .await
    {
        Ok(history) => Ok(Json(GoalHistoryResponse { history })),
        Err(e) => {
            tracing::error!("Failed to get goal history: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

/// DELETE /v1/goals/:id - Soft-delete a goal (set is_active=false, no completed_at)
async fn delete_goal(
    State(state): State<AppState>,
    user: AuthUser,
    Path(goal_id): Path<String>,
) -> Result<Json<GoalStatusResponse>, StatusCode> {
    tracing::info!("Soft-deleting goal {} for user {}", goal_id, user.uid);

    match state
        .firestore
        .update_goal(
            &user.uid,
            &goal_id,
            None,  // title
            None,  // description
            None,  // target_value
            None,  // current_value
            None,  // min_value
            None,  // max_value
            None,  // unit
            Some(false),  // is_active = false
            None,  // completed_at = None (distinguishes abandoned from completed)
        )
        .await
    {
        Ok(_) => Ok(Json(GoalStatusResponse {
            status: "deleted".to_string(),
        })),
        Err(e) => {
            tracing::error!("Failed to soft-delete goal: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

/// Build the goals router
pub fn goals_routes() -> Router<AppState> {
    Router::new()
        .route("/v1/goals/all", get(get_all_goals))
        .route("/v1/goals/completed", get(get_completed_goals))
        .route("/v1/goals", post(create_goal))
        .route("/v1/goals/:id", patch(update_goal).delete(delete_goal))
        .route("/v1/goals/:id/progress", patch(update_goal_progress))
        .route("/v1/goals/:id/history", get(get_goal_history))
}
