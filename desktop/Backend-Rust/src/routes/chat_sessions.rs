// Chat Sessions routes
// Endpoints: POST /v2/chat-sessions, GET /v2/chat-sessions, GET /v2/chat-sessions/{id},
//            PATCH /v2/chat-sessions/{id}, DELETE /v2/chat-sessions/{id}

use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    routing::get,
    Json, Router,
};

use crate::auth::AuthUser;
use crate::models::{
    ChatSessionDB, ChatSessionStatusResponse, CreateChatSessionRequest, GetChatSessionsQuery,
    UpdateChatSessionRequest,
};
use crate::AppState;

/// POST /v2/chat-sessions - Create a new chat session
async fn create_chat_session(
    State(state): State<AppState>,
    user: AuthUser,
    Json(request): Json<CreateChatSessionRequest>,
) -> Result<Json<ChatSessionDB>, StatusCode> {
    tracing::info!(
        "Creating chat session for user {} with app_id={:?}",
        user.uid,
        request.app_id
    );

    match state
        .firestore
        .create_chat_session(&user.uid, request.title.as_deref(), request.app_id.as_deref())
        .await
    {
        Ok(session) => Ok(Json(session)),
        Err(e) => {
            tracing::error!("Failed to create chat session: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

/// GET /v2/chat-sessions - List user's chat sessions
async fn get_chat_sessions(
    State(state): State<AppState>,
    user: AuthUser,
    Query(query): Query<GetChatSessionsQuery>,
) -> Json<Vec<ChatSessionDB>> {
    tracing::info!(
        "Getting chat sessions for user {} with app_id={:?}, limit={}, offset={}, starred={:?}",
        user.uid,
        query.app_id,
        query.limit,
        query.offset,
        query.starred
    );

    match state
        .firestore
        .get_chat_sessions(
            &user.uid,
            query.app_id.as_deref(),
            query.limit,
            query.offset,
            query.starred,
        )
        .await
    {
        Ok(sessions) => Json(sessions),
        Err(e) => {
            tracing::error!("Failed to get chat sessions: {}", e);
            Json(vec![])
        }
    }
}

/// GET /v2/chat-sessions/{id} - Get a single chat session
async fn get_chat_session(
    State(state): State<AppState>,
    user: AuthUser,
    Path(session_id): Path<String>,
) -> Result<Json<ChatSessionDB>, StatusCode> {
    tracing::info!(
        "Getting chat session {} for user {}",
        session_id,
        user.uid
    );

    match state
        .firestore
        .get_chat_session(&user.uid, &session_id)
        .await
    {
        Ok(Some(session)) => Ok(Json(session)),
        Ok(None) => Err(StatusCode::NOT_FOUND),
        Err(e) => {
            tracing::error!("Failed to get chat session: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

/// PATCH /v2/chat-sessions/{id} - Update a chat session (title, starred)
async fn update_chat_session(
    State(state): State<AppState>,
    user: AuthUser,
    Path(session_id): Path<String>,
    Json(request): Json<UpdateChatSessionRequest>,
) -> Result<Json<ChatSessionDB>, StatusCode> {
    tracing::info!(
        "Updating chat session {} for user {} with title={:?}, starred={:?}",
        session_id,
        user.uid,
        request.title,
        request.starred
    );

    match state
        .firestore
        .update_chat_session(
            &user.uid,
            &session_id,
            request.title.as_deref(),
            request.starred,
        )
        .await
    {
        Ok(session) => Ok(Json(session)),
        Err(e) => {
            tracing::error!("Failed to update chat session: {}", e);
            if e.to_string().contains("not found") {
                Err(StatusCode::NOT_FOUND)
            } else {
                Err(StatusCode::INTERNAL_SERVER_ERROR)
            }
        }
    }
}

/// DELETE /v2/chat-sessions/{id} - Delete a chat session and its messages
async fn delete_chat_session(
    State(state): State<AppState>,
    user: AuthUser,
    Path(session_id): Path<String>,
) -> Result<Json<ChatSessionStatusResponse>, StatusCode> {
    tracing::info!(
        "Deleting chat session {} for user {}",
        session_id,
        user.uid
    );

    // Delete the session and cascade delete messages
    match state
        .firestore
        .delete_chat_session(&user.uid, &session_id)
        .await
    {
        Ok(()) => Ok(Json(ChatSessionStatusResponse {
            status: "ok".to_string(),
        })),
        Err(e) => {
            tracing::error!("Failed to delete chat session: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

pub fn chat_sessions_routes() -> Router<AppState> {
    Router::new()
        .route(
            "/v2/chat-sessions",
            get(get_chat_sessions).post(create_chat_session),
        )
        .route(
            "/v2/chat-sessions/:id",
            get(get_chat_session)
                .patch(update_chat_session)
                .delete(delete_chat_session),
        )
}
