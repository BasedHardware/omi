// Advice routes
// Endpoints: GET/POST /v1/advice, PATCH/DELETE /v1/advice/{id}

use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    routing::{get, patch},
    Json, Router,
};

use crate::auth::AuthUser;
use crate::models::{AdviceDB, AdviceStatusResponse, CreateAdviceRequest, GetAdviceQuery, UpdateAdviceRequest};
use crate::AppState;

/// POST /v1/advice - Create new advice
async fn create_advice(
    State(state): State<AppState>,
    user: AuthUser,
    Json(request): Json<CreateAdviceRequest>,
) -> Result<Json<AdviceDB>, StatusCode> {
    tracing::info!(
        "Creating advice for user {} with category={:?}, source_app={:?}",
        user.uid,
        request.category,
        request.source_app
    );

    match state
        .firestore
        .create_advice(
            &user.uid,
            &request.content,
            request.category,
            request.reasoning.as_deref(),
            request.source_app.as_deref(),
            request.confidence,
            request.context_summary.as_deref(),
            request.current_activity.as_deref(),
        )
        .await
    {
        Ok(advice) => Ok(Json(advice)),
        Err(e) => {
            tracing::error!("Failed to create advice: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

/// GET /v1/advice - Fetch user advice history
async fn get_advice(
    State(state): State<AppState>,
    user: AuthUser,
    Query(query): Query<GetAdviceQuery>,
) -> Json<Vec<AdviceDB>> {
    tracing::info!(
        "Getting advice for user {} with limit={}, offset={}, category={:?}, include_dismissed={}",
        user.uid,
        query.limit,
        query.offset,
        query.category,
        query.include_dismissed
    );

    match state
        .firestore
        .get_advice(
            &user.uid,
            query.limit,
            query.offset,
            query.category.as_deref(),
            query.include_dismissed,
        )
        .await
    {
        Ok(advice) => Json(advice),
        Err(e) => {
            tracing::error!("Failed to get advice: {}", e);
            Json(vec![])
        }
    }
}

/// PATCH /v1/advice/{id} - Update advice (mark as read/dismissed)
async fn update_advice(
    State(state): State<AppState>,
    user: AuthUser,
    Path(advice_id): Path<String>,
    Json(request): Json<UpdateAdviceRequest>,
) -> Result<Json<AdviceDB>, StatusCode> {
    tracing::info!("Updating advice {} for user {}", advice_id, user.uid);

    match state
        .firestore
        .update_advice(&user.uid, &advice_id, request.is_read, request.is_dismissed)
        .await
    {
        Ok(advice) => Ok(Json(advice)),
        Err(e) => {
            tracing::error!("Failed to update advice: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

/// DELETE /v1/advice/{id} - Delete advice permanently
async fn delete_advice(
    State(state): State<AppState>,
    user: AuthUser,
    Path(advice_id): Path<String>,
) -> Result<Json<AdviceStatusResponse>, StatusCode> {
    tracing::info!("Deleting advice {} for user {}", advice_id, user.uid);

    match state.firestore.delete_advice(&user.uid, &advice_id).await {
        Ok(()) => Ok(Json(AdviceStatusResponse {
            status: "ok".to_string(),
        })),
        Err(e) => {
            tracing::error!("Failed to delete advice: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

/// POST /v1/advice/mark-all-read - Mark all advice as read
async fn mark_all_read(
    State(state): State<AppState>,
    user: AuthUser,
) -> Result<Json<AdviceStatusResponse>, StatusCode> {
    tracing::info!("Marking all advice as read for user {}", user.uid);

    match state.firestore.mark_all_advice_read(&user.uid).await {
        Ok(count) => {
            tracing::info!("Marked {} advice as read for user {}", count, user.uid);
            Ok(Json(AdviceStatusResponse {
                status: format!("marked {} as read", count),
            }))
        }
        Err(e) => {
            tracing::error!("Failed to mark all advice as read: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

pub fn advice_routes() -> Router<AppState> {
    Router::new()
        .route("/v1/advice", get(get_advice).post(create_advice))
        .route("/v1/advice/mark-all-read", axum::routing::post(mark_all_read))
        .route(
            "/v1/advice/:id",
            patch(update_advice).delete(delete_advice),
        )
}
