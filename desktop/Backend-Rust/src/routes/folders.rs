// Folder routes

use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    routing::{get, patch, post},
    Json, Router,
};
use serde::Serialize;

use crate::models::{
    BulkMoveRequest, BulkMoveResponse, CreateFolderRequest, DeleteFolderQuery, Folder,
    MoveToFolderRequest, ReorderFoldersRequest, UpdateFolderRequest,
};
use crate::auth::AuthUser;
use crate::AppState;

/// Status response for operations
#[derive(Serialize)]
struct StatusResponse {
    status: String,
}

/// Create folder routes
pub fn folder_routes() -> Router<AppState> {
    Router::new()
        .route("/v1/folders", get(get_folders).post(create_folder))
        .route(
            "/v1/folders/:id",
            patch(update_folder).delete(delete_folder),
        )
        .route("/v1/folders/reorder", post(reorder_folders))
        .route(
            "/v1/folders/:id/conversations/bulk-move",
            post(bulk_move_conversations),
        )
        .route(
            "/v1/conversations/:id/folder",
            patch(move_conversation_to_folder),
        )
}

/// GET /v1/folders - Get all folders for the user
async fn get_folders(
    State(state): State<AppState>,
    user: AuthUser,
) -> Result<Json<Vec<Folder>>, StatusCode> {
    tracing::info!("Getting folders for user {}", user.uid);

    match state.firestore.get_folders(&user.uid).await {
        Ok(folders) => Ok(Json(folders)),
        Err(e) => {
            tracing::error!("Failed to get folders: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

/// POST /v1/folders - Create a new folder
async fn create_folder(
    State(state): State<AppState>,
    user: AuthUser,
    Json(request): Json<CreateFolderRequest>,
) -> Result<Json<Folder>, StatusCode> {
    tracing::info!("Creating folder '{}' for user {}", request.name, user.uid);

    match state
        .firestore
        .create_folder(
            &user.uid,
            &request.name,
            request.description.as_deref(),
            request.color.as_deref(),
        )
        .await
    {
        Ok(folder) => Ok(Json(folder)),
        Err(e) => {
            tracing::error!("Failed to create folder: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

/// PATCH /v1/folders/:id - Update a folder
async fn update_folder(
    State(state): State<AppState>,
    user: AuthUser,
    Path(folder_id): Path<String>,
    Json(request): Json<UpdateFolderRequest>,
) -> Result<Json<Folder>, StatusCode> {
    tracing::info!("Updating folder {} for user {}", folder_id, user.uid);

    match state
        .firestore
        .update_folder(
            &user.uid,
            &folder_id,
            request.name.as_deref(),
            request.description.as_deref(),
            request.color.as_deref(),
            request.order,
        )
        .await
    {
        Ok(folder) => Ok(Json(folder)),
        Err(e) => {
            tracing::error!("Failed to update folder: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

/// DELETE /v1/folders/:id - Delete a folder
async fn delete_folder(
    State(state): State<AppState>,
    user: AuthUser,
    Path(folder_id): Path<String>,
    Query(query): Query<DeleteFolderQuery>,
) -> StatusCode {
    tracing::info!("Deleting folder {} for user {}", folder_id, user.uid);

    match state
        .firestore
        .delete_folder(&user.uid, &folder_id, query.move_to_folder_id.as_deref())
        .await
    {
        Ok(()) => StatusCode::NO_CONTENT,
        Err(e) => {
            tracing::error!("Failed to delete folder: {}", e);
            StatusCode::INTERNAL_SERVER_ERROR
        }
    }
}

/// POST /v1/folders/reorder - Reorder folders
async fn reorder_folders(
    State(state): State<AppState>,
    user: AuthUser,
    Json(request): Json<ReorderFoldersRequest>,
) -> Result<Json<StatusResponse>, StatusCode> {
    tracing::info!("Reordering folders for user {}", user.uid);

    match state
        .firestore
        .reorder_folders(&user.uid, &request.folder_ids)
        .await
    {
        Ok(()) => Ok(Json(StatusResponse {
            status: "ok".to_string(),
        })),
        Err(e) => {
            tracing::error!("Failed to reorder folders: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

/// POST /v1/folders/:id/conversations/bulk-move - Bulk move conversations to folder
async fn bulk_move_conversations(
    State(state): State<AppState>,
    user: AuthUser,
    Path(folder_id): Path<String>,
    Json(request): Json<BulkMoveRequest>,
) -> Result<Json<BulkMoveResponse>, StatusCode> {
    tracing::info!(
        "Bulk moving {} conversations to folder {} for user {}",
        request.conversation_ids.len(),
        folder_id,
        user.uid
    );

    match state
        .firestore
        .bulk_move_to_folder(&user.uid, &folder_id, &request.conversation_ids)
        .await
    {
        Ok(moved_count) => Ok(Json(BulkMoveResponse { moved_count })),
        Err(e) => {
            tracing::error!("Failed to bulk move conversations: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

/// PATCH /v1/conversations/:id/folder - Move conversation to folder
async fn move_conversation_to_folder(
    State(state): State<AppState>,
    user: AuthUser,
    Path(conversation_id): Path<String>,
    Json(request): Json<MoveToFolderRequest>,
) -> Result<Json<StatusResponse>, StatusCode> {
    tracing::info!(
        "Moving conversation {} to folder {:?} for user {}",
        conversation_id,
        request.folder_id,
        user.uid
    );

    match state
        .firestore
        .set_conversation_folder(&user.uid, &conversation_id, request.folder_id.as_deref())
        .await
    {
        Ok(()) => Ok(Json(StatusResponse {
            status: "ok".to_string(),
        })),
        Err(e) => {
            tracing::error!("Failed to move conversation to folder: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}
