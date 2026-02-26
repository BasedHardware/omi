// Chat Messages routes - For chat persistence
// Endpoints: POST, GET, DELETE /v2/messages, PATCH /v2/messages/{id}/rating

use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    routing::{get, patch},
    Json, Router,
};

use crate::auth::AuthUser;
use crate::models::{
    DeleteMessagesQuery, GetMessagesQuery, MessageDB, MessageStatusResponse, RateMessageRequest,
    SaveMessageRequest, SaveMessageResponse,
};
use crate::AppState;

/// POST /v2/messages - Save a chat message
async fn save_message(
    State(state): State<AppState>,
    user: AuthUser,
    Json(request): Json<SaveMessageRequest>,
) -> Result<Json<SaveMessageResponse>, StatusCode> {
    tracing::info!(
        "Saving {} message for user {} (app_id={:?})",
        request.sender,
        user.uid,
        request.app_id
    );

    // Validate sender
    if request.sender != "human" && request.sender != "ai" {
        tracing::warn!("Invalid sender: {}", request.sender);
        return Err(StatusCode::BAD_REQUEST);
    }

    // Validate text is not empty
    if request.text.trim().is_empty() {
        tracing::warn!("Empty message text");
        return Err(StatusCode::BAD_REQUEST);
    }

    match state
        .firestore
        .save_message(
            &user.uid,
            &request.text,
            &request.sender,
            request.app_id.as_deref(),
            request.session_id.as_deref(),
            request.metadata.as_deref(),
        )
        .await
    {
        Ok(message) => Ok(Json(SaveMessageResponse {
            id: message.id,
            created_at: message.created_at,
        })),
        Err(e) => {
            tracing::error!("Failed to save message: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

/// GET /v2/messages - Get chat message history
async fn get_messages(
    State(state): State<AppState>,
    user: AuthUser,
    Query(query): Query<GetMessagesQuery>,
) -> Json<Vec<MessageDB>> {
    tracing::info!(
        "Getting messages for user {} (app_id={:?}, session_id={:?}, limit={}, offset={})",
        user.uid,
        query.app_id,
        query.session_id,
        query.limit,
        query.offset
    );

    match state
        .firestore
        .get_messages(
            &user.uid,
            query.app_id.as_deref(),
            query.session_id.as_deref(),
            query.limit,
            query.offset,
        )
        .await
    {
        Ok(messages) => Json(messages),
        Err(e) => {
            tracing::error!("Failed to get messages: {}", e);
            Json(vec![])
        }
    }
}

/// DELETE /v2/messages - Clear chat message history
async fn delete_messages(
    State(state): State<AppState>,
    user: AuthUser,
    Query(query): Query<DeleteMessagesQuery>,
) -> Result<Json<MessageStatusResponse>, StatusCode> {
    tracing::info!(
        "Deleting messages for user {} (app_id={:?})",
        user.uid,
        query.app_id
    );

    match state
        .firestore
        .delete_messages(&user.uid, query.app_id.as_deref())
        .await
    {
        Ok(count) => Ok(Json(MessageStatusResponse {
            status: "ok".to_string(),
            deleted_count: Some(count),
        })),
        Err(e) => {
            tracing::error!("Failed to delete messages: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

/// PATCH /v2/messages/{id}/rating - Rate a message (thumbs up/down)
async fn rate_message(
    State(state): State<AppState>,
    user: AuthUser,
    Path(message_id): Path<String>,
    Json(request): Json<RateMessageRequest>,
) -> Result<Json<MessageStatusResponse>, StatusCode> {
    // Validate rating value if present
    if let Some(rating) = request.rating {
        if rating != 1 && rating != -1 {
            tracing::warn!("Invalid rating value: {}", rating);
            return Err(StatusCode::BAD_REQUEST);
        }
    }

    tracing::info!(
        "Rating message {} for user {} with rating={:?}",
        message_id,
        user.uid,
        request.rating
    );

    match state
        .firestore
        .update_message_rating(&user.uid, &message_id, request.rating)
        .await
    {
        Ok(()) => Ok(Json(MessageStatusResponse {
            status: "ok".to_string(),
            deleted_count: None,
        })),
        Err(e) => {
            tracing::error!("Failed to rate message: {}", e);
            if e.to_string().contains("not found") {
                Err(StatusCode::NOT_FOUND)
            } else {
                Err(StatusCode::INTERNAL_SERVER_ERROR)
            }
        }
    }
}

pub fn messages_routes() -> Router<AppState> {
    Router::new()
        .route(
            "/v2/messages",
            get(get_messages).post(save_message).delete(delete_messages),
        )
        .route("/v2/messages/:id/rating", patch(rate_message))
}
