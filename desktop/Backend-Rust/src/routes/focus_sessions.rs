// Focus Sessions routes
// Endpoints: POST /v1/focus-sessions, GET /v1/focus-sessions, DELETE /v1/focus-sessions/{id}, GET /v1/focus-stats

use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    routing::get,
    Json, Router,
};

use crate::auth::AuthUser;
use crate::models::{
    CreateFocusSessionRequest, FocusSessionDB, FocusSessionStatusResponse, FocusStats,
    GetFocusSessionsQuery, GetFocusStatsQuery,
};
use crate::AppState;

/// POST /v1/focus-sessions - Create a new focus session
async fn create_focus_session(
    State(state): State<AppState>,
    user: AuthUser,
    Json(request): Json<CreateFocusSessionRequest>,
) -> Result<Json<FocusSessionDB>, StatusCode> {
    tracing::info!(
        "Creating focus session for user {} with status={}, app={}",
        user.uid,
        request.status,
        request.app_or_site
    );

    match state
        .firestore
        .create_focus_session(
            &user.uid,
            &request.status,
            &request.app_or_site,
            &request.description,
            request.message.as_deref(),
        )
        .await
    {
        Ok(session) => Ok(Json(session)),
        Err(e) => {
            tracing::error!("Failed to create focus session: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

/// GET /v1/focus-sessions - Fetch user focus sessions
async fn get_focus_sessions(
    State(state): State<AppState>,
    user: AuthUser,
    Query(query): Query<GetFocusSessionsQuery>,
) -> Json<Vec<FocusSessionDB>> {
    tracing::info!(
        "Getting focus sessions for user {} with limit={}, offset={}, date={:?}",
        user.uid,
        query.limit,
        query.offset,
        query.date
    );

    match state
        .firestore
        .get_focus_sessions(&user.uid, query.limit, query.offset, query.date.as_deref())
        .await
    {
        Ok(sessions) => Json(sessions),
        Err(e) => {
            tracing::error!("Failed to get focus sessions: {}", e);
            Json(vec![])
        }
    }
}

/// DELETE /v1/focus-sessions/{id} - Delete a focus session
async fn delete_focus_session(
    State(state): State<AppState>,
    user: AuthUser,
    Path(session_id): Path<String>,
) -> Result<Json<FocusSessionStatusResponse>, StatusCode> {
    tracing::info!("Deleting focus session {} for user {}", session_id, user.uid);

    match state
        .firestore
        .delete_focus_session(&user.uid, &session_id)
        .await
    {
        Ok(()) => Ok(Json(FocusSessionStatusResponse {
            status: "ok".to_string(),
        })),
        Err(e) => {
            tracing::error!("Failed to delete focus session: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

/// GET /v1/focus-stats - Get focus statistics for a date
async fn get_focus_stats(
    State(state): State<AppState>,
    user: AuthUser,
    Query(query): Query<GetFocusStatsQuery>,
) -> Result<Json<FocusStats>, StatusCode> {
    let date = query.date.unwrap_or_else(|| {
        chrono::Utc::now().format("%Y-%m-%d").to_string()
    });

    tracing::info!("Getting focus stats for user {} on date {}", user.uid, date);

    match state.firestore.get_focus_stats(&user.uid, &date).await {
        Ok(stats) => Ok(Json(stats)),
        Err(e) => {
            tracing::error!("Failed to get focus stats: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

pub fn focus_sessions_routes() -> Router<AppState> {
    Router::new()
        .route(
            "/v1/focus-sessions",
            get(get_focus_sessions).post(create_focus_session),
        )
        .route("/v1/focus-sessions/:id", axum::routing::delete(delete_focus_session))
        .route("/v1/focus-stats", get(get_focus_stats))
}
