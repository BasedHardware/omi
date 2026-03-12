// People routes - Speaker voice profiles for transcript naming

use axum::{
    extract::{Path, State},
    http::StatusCode,
    routing::get,
    Json, Router,
};

use crate::auth::AuthUser;
use crate::models::{BulkAssignSegmentsRequest, CreatePersonRequest, Person};
use crate::AppState;

/// Create people routes
pub fn people_routes() -> Router<AppState> {
    Router::new()
        .route("/v1/users/people", get(get_people).post(create_person))
        .route(
            "/v1/users/people/:person_id",
            axum::routing::delete(delete_person),
        )
        .route(
            "/v1/users/people/:person_id/name",
            axum::routing::patch(update_person_name),
        )
        .route(
            "/v1/conversations/:conversation_id/segments/assign-bulk",
            axum::routing::patch(assign_segments_bulk),
        )
}

/// GET /v1/users/people - Get all people for the user
async fn get_people(
    State(state): State<AppState>,
    user: AuthUser,
) -> Result<Json<Vec<Person>>, StatusCode> {
    match state.firestore.get_people(&user.uid).await {
        Ok(people) => Ok(Json(people)),
        Err(e) => {
            tracing::error!("Failed to get people: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

/// POST /v1/users/people - Create a new person
async fn create_person(
    State(state): State<AppState>,
    user: AuthUser,
    Json(request): Json<CreatePersonRequest>,
) -> Result<Json<Person>, StatusCode> {
    if request.name.trim().is_empty() {
        return Err(StatusCode::BAD_REQUEST);
    }

    match state.firestore.create_person(&user.uid, &request.name).await {
        Ok(person) => Ok(Json(person)),
        Err(e) => {
            tracing::error!("Failed to create person: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

/// PATCH /v1/users/people/:person_id/name?value=NewName - Update a person's name
async fn update_person_name(
    State(state): State<AppState>,
    user: AuthUser,
    Path(person_id): Path<String>,
    axum::extract::Query(query): axum::extract::Query<NameQuery>,
) -> StatusCode {
    if query.value.trim().is_empty() {
        return StatusCode::BAD_REQUEST;
    }

    match state
        .firestore
        .update_person_name(&user.uid, &person_id, &query.value)
        .await
    {
        Ok(()) => StatusCode::OK,
        Err(e) => {
            tracing::error!("Failed to update person name: {}", e);
            StatusCode::INTERNAL_SERVER_ERROR
        }
    }
}

/// DELETE /v1/users/people/:person_id - Delete a person
async fn delete_person(
    State(state): State<AppState>,
    user: AuthUser,
    Path(person_id): Path<String>,
) -> StatusCode {
    match state.firestore.delete_person(&user.uid, &person_id).await {
        Ok(()) => StatusCode::NO_CONTENT,
        Err(e) => {
            tracing::error!("Failed to delete person: {}", e);
            StatusCode::INTERNAL_SERVER_ERROR
        }
    }
}

/// PATCH /v1/conversations/:conversation_id/segments/assign-bulk
async fn assign_segments_bulk(
    State(state): State<AppState>,
    user: AuthUser,
    Path(conversation_id): Path<String>,
    Json(request): Json<BulkAssignSegmentsRequest>,
) -> StatusCode {
    if request.assign_type != "is_user" && request.assign_type != "person_id" {
        return StatusCode::BAD_REQUEST;
    }

    match state
        .firestore
        .assign_segments_bulk(
            &user.uid,
            &conversation_id,
            &request.segment_ids,
            &request.assign_type,
            request.value.as_deref(),
        )
        .await
    {
        Ok(()) => StatusCode::OK,
        Err(e) => {
            tracing::error!("Failed to assign segments: {}", e);
            StatusCode::INTERNAL_SERVER_ERROR
        }
    }
}

#[derive(serde::Deserialize)]
struct NameQuery {
    value: String,
}
