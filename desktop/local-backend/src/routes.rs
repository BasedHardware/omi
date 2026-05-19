use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};

use crate::{
    processing,
    storage::{
        deterministic_id, AppendTranscriptResult, NewActionItem, NewConversation, NewMemory,
        NewProcessingJob, NewTranscriptSegment, UpdateActionItem, UpdateConversation, UpdateMemory,
        UpdateProfile,
    },
    AppState,
};

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/version", get(version))
        .route("/profile/status", get(profile_status))
        .route("/v1/profile", get(get_profile).put(update_profile))
        .route("/v1/settings", get(list_settings).put(update_settings))
        .route(
            "/v1/conversations",
            get(list_conversations).post(create_conversation),
        )
        .route("/v1/conversations/count", get(count_conversations))
        .route(
            "/v1/conversations/:id",
            get(get_conversation)
                .patch(update_conversation)
                .delete(delete_conversation),
        )
        .route(
            "/v1/conversations/:id/transcript-segments",
            post(append_transcript_segment),
        )
        .route(
            "/v1/conversations/:id/finalize-transcript",
            post(finalize_transcript),
        )
        .route("/v1/search/conversations", get(search_conversations))
        .route("/v1/memories", get(list_memories).post(create_memory))
        .route(
            "/v1/memories/:id",
            get(get_memory).patch(update_memory).delete(delete_memory),
        )
        .route(
            "/v1/action-items",
            get(list_action_items).post(create_action_item),
        )
        .route(
            "/v1/action-items/:id",
            get(get_action_item)
                .patch(update_action_item)
                .delete(delete_action_item),
        )
        .route("/v1/processing-jobs", get(list_processing_jobs))
        .route("/v1/processing-jobs/process-next", post(process_next_job))
        .route("/v1/processing-jobs/status", get(processing_status))
        .route("/v1/processing-jobs/:id", get(get_processing_job))
}

#[derive(Debug)]
struct ApiError {
    status: StatusCode,
    message: String,
}

impl ApiError {
    fn bad_request(message: impl Into<String>) -> Self {
        Self {
            status: StatusCode::BAD_REQUEST,
            message: message.into(),
        }
    }

    fn conflict(message: impl Into<String>) -> Self {
        Self {
            status: StatusCode::CONFLICT,
            message: message.into(),
        }
    }

    fn not_found(entity: &str) -> Self {
        Self {
            status: StatusCode::NOT_FOUND,
            message: format!("{entity} not found"),
        }
    }

    fn internal(error: anyhow::Error) -> Self {
        Self {
            status: StatusCode::INTERNAL_SERVER_ERROR,
            message: error.to_string(),
        }
    }
}

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        (
            self.status,
            Json(json!({
                "error": {
                    "code": self.status.as_u16(),
                    "message": self.message,
                    "source": "local_daemon"
                }
            })),
        )
            .into_response()
    }
}

type ApiResult<T> = Result<Json<T>, ApiError>;

#[derive(Serialize)]
struct VersionResponse {
    service: &'static str,
    mode: &'static str,
    version: &'static str,
}

async fn version() -> Json<VersionResponse> {
    Json(VersionResponse {
        service: "omi-local-backend",
        mode: "local",
        version: env!("CARGO_PKG_VERSION"),
    })
}

async fn profile_status(State(state): State<AppState>) -> ApiResult<Value> {
    let profile = state
        .store
        .profile()
        .get_or_create_default()
        .map_err(ApiError::internal)?;
    Ok(Json(json!({
        "mode": "local",
        "authenticated": false,
        "profile": profile,
        "backend": {
            "service": "omi-local-backend",
            "version": env!("CARGO_PKG_VERSION"),
            "data_dir": state.config.data_dir
        }
    })))
}

#[derive(Deserialize)]
struct ListQuery {
    limit: Option<i64>,
}

async fn list_conversations(
    State(state): State<AppState>,
    Query(query): Query<ListQuery>,
) -> ApiResult<Value> {
    let conversations = state
        .store
        .conversations()
        .list(limit_or_default(query.limit))
        .map_err(ApiError::internal)?;
    Ok(Json(json!({ "conversations": conversations })))
}

async fn count_conversations(State(state): State<AppState>) -> ApiResult<Value> {
    let count = state
        .store
        .conversations()
        .count()
        .map_err(ApiError::internal)?;
    Ok(Json(json!({ "count": count })))
}

#[derive(Deserialize)]
struct CreateConversationRequest {
    id: Option<String>,
    session_id: Option<String>,
    title: Option<String>,
    overview: Option<String>,
    started_at: Option<DateTime<Utc>>,
    metadata: Option<Value>,
}

async fn create_conversation(
    State(state): State<AppState>,
    Json(request): Json<CreateConversationRequest>,
) -> ApiResult<Value> {
    let session_id = request.session_id.unwrap_or_else(|| local_id("session"));
    let id = request
        .id
        .unwrap_or_else(|| deterministic_id("conv", &[&session_id]));
    let new_conversation = NewConversation {
        id: id.clone(),
        session_id,
        title: request.title.unwrap_or_default(),
        overview: request.overview.unwrap_or_default(),
        started_at: request.started_at,
        metadata: request.metadata,
    };
    if let Some(existing) = state
        .store
        .conversations()
        .get(&id)
        .map_err(ApiError::internal)?
    {
        if conversation_matches_new(&existing, &new_conversation).map_err(ApiError::internal)? {
            return Ok(Json(json!({ "conversation": existing })));
        }
        return Err(ApiError::conflict(
            "conversation already exists with different content",
        ));
    }
    let conversation = state
        .store
        .conversations()
        .create(new_conversation)
        .map_err(ApiError::internal)?;
    Ok(Json(json!({ "conversation": conversation })))
}

async fn get_conversation(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> ApiResult<Value> {
    let conversation = state
        .store
        .conversations()
        .get(&id)
        .map_err(ApiError::internal)?
        .ok_or_else(|| ApiError::not_found("conversation"))?;
    let transcript_segments = state
        .store
        .transcripts()
        .list_for_conversation(&id)
        .map_err(ApiError::internal)?;
    Ok(Json(json!({
        "conversation": conversation,
        "transcript_segments": transcript_segments
    })))
}

#[derive(Deserialize)]
struct UpdateConversationRequest {
    title: Option<String>,
    overview: Option<String>,
    status: Option<String>,
    ended_at: Option<DateTime<Utc>>,
    metadata: Option<Value>,
    starred: Option<bool>,
}

async fn update_conversation(
    State(state): State<AppState>,
    Path(id): Path<String>,
    Json(request): Json<UpdateConversationRequest>,
) -> ApiResult<Value> {
    let conversation = state
        .store
        .conversations()
        .update(
            &id,
            UpdateConversation {
                title: request.title,
                overview: request.overview,
                status: request.status,
                ended_at: request.ended_at.map(Some),
                metadata: request.metadata,
                starred: request.starred,
            },
        )
        .map_err(ApiError::internal)?
        .ok_or_else(|| ApiError::not_found("conversation"))?;
    Ok(Json(json!({ "conversation": conversation })))
}

async fn delete_conversation(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Result<StatusCode, ApiError> {
    if state
        .store
        .conversations()
        .soft_delete(&id)
        .map_err(ApiError::internal)?
    {
        Ok(StatusCode::NO_CONTENT)
    } else {
        Err(ApiError::not_found("conversation"))
    }
}

#[derive(Deserialize)]
struct AppendSegmentRequest {
    id: Option<String>,
    session_id: Option<String>,
    speaker_id: Option<String>,
    speaker_label: Option<String>,
    text: String,
    start_ms: i64,
    end_ms: i64,
    segment_index: Option<i64>,
    source: Option<String>,
    metadata: Option<Value>,
}

async fn append_transcript_segment(
    State(state): State<AppState>,
    Path(conversation_id): Path<String>,
    Json(request): Json<AppendSegmentRequest>,
) -> ApiResult<Value> {
    let conversation = state
        .store
        .conversations()
        .get(&conversation_id)
        .map_err(ApiError::internal)?
        .ok_or_else(|| ApiError::not_found("conversation"))?;
    if request.text.trim().is_empty() {
        return Err(ApiError::bad_request("transcript segment text is required"));
    }
    let segment_index = match request.segment_index {
        Some(index) => index,
        None => state
            .store
            .transcripts()
            .next_segment_index(&conversation_id)
            .map_err(ApiError::internal)?,
    };
    let id = request.id.unwrap_or_else(|| {
        deterministic_id("seg", &[&conversation_id, &segment_index.to_string()])
    });
    let append_result = state
        .store
        .transcripts()
        .append(NewTranscriptSegment {
            id,
            conversation_id,
            session_id: request.session_id.unwrap_or(conversation.session_id),
            speaker_id: request.speaker_id,
            speaker_label: request.speaker_label,
            text: request.text,
            start_ms: request.start_ms,
            end_ms: request.end_ms,
            segment_index,
            source: request.source,
            metadata: request.metadata,
        })
        .map_err(ApiError::internal)?;
    let segment = match append_result {
        AppendTranscriptResult::Inserted(segment) | AppendTranscriptResult::Existing(segment) => {
            segment
        }
        AppendTranscriptResult::Conflict(_) => {
            return Err(ApiError::conflict(
                "transcript segment already exists with different content at this index",
            ));
        }
    };
    Ok(Json(json!({ "transcript_segment": segment })))
}

async fn finalize_transcript(
    State(state): State<AppState>,
    Path(conversation_id): Path<String>,
) -> ApiResult<Value> {
    state
        .store
        .conversations()
        .get(&conversation_id)
        .map_err(ApiError::internal)?
        .ok_or_else(|| ApiError::not_found("conversation"))?;
    if let Some(job) = state
        .store
        .processing_jobs()
        .reusable_for_conversation("finalize_transcript", &conversation_id)
        .map_err(ApiError::internal)?
    {
        return Ok(Json(json!({ "processing_job": job })));
    }

    let job = state
        .store
        .processing_jobs()
        .enqueue(NewProcessingJob {
            id: local_id("job"),
            kind: "finalize_transcript".to_string(),
            target_conversation_id: Some(conversation_id.clone()),
            max_retries: Some(3),
            payload: Some(json!({ "conversation_id": conversation_id })),
        })
        .map_err(ApiError::internal)?;
    Ok(Json(json!({ "processing_job": job })))
}

#[derive(Deserialize)]
struct SearchQuery {
    q: String,
    limit: Option<i64>,
}

async fn search_conversations(
    State(state): State<AppState>,
    Query(query): Query<SearchQuery>,
) -> ApiResult<Value> {
    if query.q.trim().is_empty() {
        return Err(ApiError::bad_request("search query is required"));
    }
    let results = state
        .store
        .search()
        .conversations(&query.q, limit_or_default(query.limit))
        .map_err(ApiError::internal)?;
    Ok(Json(json!({ "results": results })))
}

async fn list_memories(State(state): State<AppState>) -> ApiResult<Value> {
    let memories = state.store.memories().list().map_err(ApiError::internal)?;
    Ok(Json(json!({ "memories": memories })))
}

#[derive(Deserialize)]
struct CreateMemoryRequest {
    id: Option<String>,
    content: String,
    category: Option<String>,
    conversation_id: Option<String>,
    metadata: Option<Value>,
}

async fn create_memory(
    State(state): State<AppState>,
    Json(request): Json<CreateMemoryRequest>,
) -> ApiResult<Value> {
    let id = request.id.unwrap_or_else(|| local_id("mem"));
    let new_memory = NewMemory {
        id: id.clone(),
        content: request.content,
        category: request.category,
        conversation_id: request.conversation_id,
        metadata: request.metadata,
    };
    if let Some(existing) = state
        .store
        .memories()
        .get(&id)
        .map_err(ApiError::internal)?
    {
        if memory_matches_new(&existing, &new_memory).map_err(ApiError::internal)? {
            return Ok(Json(json!({ "memory": existing })));
        }
        return Err(ApiError::conflict(
            "memory already exists with different content",
        ));
    }
    let memory = state
        .store
        .memories()
        .create(new_memory)
        .map_err(ApiError::internal)?;
    Ok(Json(json!({ "memory": memory })))
}

async fn get_memory(State(state): State<AppState>, Path(id): Path<String>) -> ApiResult<Value> {
    let memory = state
        .store
        .memories()
        .get(&id)
        .map_err(ApiError::internal)?
        .ok_or_else(|| ApiError::not_found("memory"))?;
    Ok(Json(json!({ "memory": memory })))
}

#[derive(Deserialize)]
struct UpdateMemoryRequest {
    content: Option<String>,
    category: Option<String>,
    conversation_id: Option<String>,
    metadata: Option<Value>,
}

async fn update_memory(
    State(state): State<AppState>,
    Path(id): Path<String>,
    Json(request): Json<UpdateMemoryRequest>,
) -> ApiResult<Value> {
    let memory = state
        .store
        .memories()
        .update(
            &id,
            UpdateMemory {
                content: request.content,
                category: request.category.map(Some),
                conversation_id: request.conversation_id.map(Some),
                metadata: request.metadata,
            },
        )
        .map_err(ApiError::internal)?
        .ok_or_else(|| ApiError::not_found("memory"))?;
    Ok(Json(json!({ "memory": memory })))
}

async fn delete_memory(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Result<StatusCode, ApiError> {
    if state
        .store
        .memories()
        .soft_delete(&id)
        .map_err(ApiError::internal)?
    {
        Ok(StatusCode::NO_CONTENT)
    } else {
        Err(ApiError::not_found("memory"))
    }
}

async fn list_action_items(State(state): State<AppState>) -> ApiResult<Value> {
    let action_items = state
        .store
        .action_items()
        .list()
        .map_err(ApiError::internal)?;
    Ok(Json(json!({ "action_items": action_items })))
}

#[derive(Deserialize)]
struct CreateActionItemRequest {
    id: Option<String>,
    conversation_id: Option<String>,
    title: String,
    description: Option<String>,
    status: Option<String>,
    due_at: Option<DateTime<Utc>>,
    metadata: Option<Value>,
}

async fn create_action_item(
    State(state): State<AppState>,
    Json(request): Json<CreateActionItemRequest>,
) -> ApiResult<Value> {
    let id = request.id.unwrap_or_else(|| local_id("act"));
    let new_action_item = NewActionItem {
        id: id.clone(),
        conversation_id: request.conversation_id,
        title: request.title,
        description: request.description,
        status: request.status,
        due_at: request.due_at,
        metadata: request.metadata,
    };
    if let Some(existing) = state
        .store
        .action_items()
        .get(&id)
        .map_err(ApiError::internal)?
    {
        if action_item_matches_new(&existing, &new_action_item).map_err(ApiError::internal)? {
            return Ok(Json(json!({ "action_item": existing })));
        }
        return Err(ApiError::conflict(
            "action item already exists with different content",
        ));
    }
    let action_item = state
        .store
        .action_items()
        .create(new_action_item)
        .map_err(ApiError::internal)?;
    Ok(Json(json!({ "action_item": action_item })))
}

async fn get_action_item(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> ApiResult<Value> {
    let action_item = state
        .store
        .action_items()
        .get(&id)
        .map_err(ApiError::internal)?
        .ok_or_else(|| ApiError::not_found("action item"))?;
    Ok(Json(json!({ "action_item": action_item })))
}

#[derive(Deserialize)]
struct UpdateActionItemRequest {
    conversation_id: Option<String>,
    title: Option<String>,
    description: Option<String>,
    status: Option<String>,
    due_at: Option<DateTime<Utc>>,
    clear_due_at: Option<bool>,
    metadata: Option<Value>,
}

async fn update_action_item(
    State(state): State<AppState>,
    Path(id): Path<String>,
    Json(request): Json<UpdateActionItemRequest>,
) -> ApiResult<Value> {
    let action_item = state
        .store
        .action_items()
        .update(
            &id,
            UpdateActionItem {
                conversation_id: request.conversation_id.map(Some),
                title: request.title,
                description: request.description,
                status: request.status,
                due_at: if request.clear_due_at.unwrap_or(false) {
                    Some(None)
                } else {
                    request.due_at.map(Some)
                },
                metadata: request.metadata,
            },
        )
        .map_err(ApiError::internal)?
        .ok_or_else(|| ApiError::not_found("action item"))?;
    Ok(Json(json!({ "action_item": action_item })))
}

async fn delete_action_item(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Result<StatusCode, ApiError> {
    if state
        .store
        .action_items()
        .soft_delete(&id)
        .map_err(ApiError::internal)?
    {
        Ok(StatusCode::NO_CONTENT)
    } else {
        Err(ApiError::not_found("action item"))
    }
}

async fn get_profile(State(state): State<AppState>) -> ApiResult<Value> {
    let profile = state
        .store
        .profile()
        .get_or_create_default()
        .map_err(ApiError::internal)?;
    Ok(Json(json!({ "profile": profile })))
}

#[derive(Deserialize)]
struct UpdateProfileRequest {
    display_name: Option<String>,
    timezone: Option<String>,
    locale: Option<String>,
    metadata: Option<Value>,
}

async fn update_profile(
    State(state): State<AppState>,
    Json(request): Json<UpdateProfileRequest>,
) -> ApiResult<Value> {
    let profile = state
        .store
        .profile()
        .upsert(UpdateProfile {
            display_name: request.display_name,
            timezone: request.timezone,
            locale: request.locale,
            metadata: request.metadata,
        })
        .map_err(ApiError::internal)?;
    Ok(Json(json!({ "profile": profile })))
}

async fn list_settings(State(state): State<AppState>) -> ApiResult<Value> {
    let settings = state.store.settings().list().map_err(ApiError::internal)?;
    Ok(Json(json!({ "settings": settings })))
}

async fn update_settings(
    State(state): State<AppState>,
    Json(values): Json<Map<String, Value>>,
) -> ApiResult<Value> {
    let settings = state
        .store
        .settings()
        .upsert_many(values)
        .map_err(ApiError::internal)?;
    Ok(Json(json!({ "settings": settings })))
}

async fn list_processing_jobs(State(state): State<AppState>) -> ApiResult<Value> {
    let jobs = state
        .store
        .processing_jobs()
        .list()
        .map_err(ApiError::internal)?;
    Ok(Json(json!({ "processing_jobs": jobs })))
}

async fn get_processing_job(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> ApiResult<Value> {
    let job = state
        .store
        .processing_jobs()
        .get(&id)
        .map_err(ApiError::internal)?
        .ok_or_else(|| ApiError::not_found("processing job"))?;
    Ok(Json(json!({ "processing_job": job })))
}

async fn process_next_job(State(state): State<AppState>) -> ApiResult<Value> {
    let job = processing::process_next_job(&state.store)
        .await
        .map_err(ApiError::internal)?;
    Ok(Json(json!({ "processing_job": job })))
}

async fn processing_status(State(state): State<AppState>) -> ApiResult<Value> {
    let jobs = state
        .store
        .processing_jobs()
        .list()
        .map_err(ApiError::internal)?;
    let mut queued = 0;
    let mut running = 0;
    let mut completed = 0;
    let mut failed = 0;
    for job in jobs {
        match job.status {
            crate::storage::ProcessingJobStatus::Queued => queued += 1,
            crate::storage::ProcessingJobStatus::Running => running += 1,
            crate::storage::ProcessingJobStatus::Completed => completed += 1,
            crate::storage::ProcessingJobStatus::Failed => failed += 1,
        }
    }
    Ok(Json(json!({
        "queued": queued,
        "running": running,
        "completed": completed,
        "failed": failed
    })))
}

fn limit_or_default(limit: Option<i64>) -> i64 {
    limit.unwrap_or(50).clamp(1, 200)
}

fn local_id(prefix: &str) -> String {
    let now = Utc::now()
        .timestamp_nanos_opt()
        .unwrap_or_else(|| Utc::now().timestamp_micros() * 1000);
    deterministic_id(prefix, &[&now.to_string()])
}

fn conversation_matches_new(
    existing: &crate::storage::Conversation,
    new: &NewConversation,
) -> anyhow::Result<bool> {
    let mutable_fields_match = existing.status != "open"
        || (existing.title == new.title && existing.overview == new.overview);
    Ok(existing.id == new.id
        && existing.session_id == new.session_id
        && mutable_fields_match
        && new
            .started_at
            .map(|started_at| existing.started_at == started_at)
            .unwrap_or(true)
        && json_matches_optional(&existing.metadata_json, &new.metadata)?)
}

fn memory_matches_new(existing: &crate::storage::Memory, new: &NewMemory) -> anyhow::Result<bool> {
    Ok(existing.id == new.id
        && existing.content == new.content
        && existing.category == new.category
        && existing.conversation_id == new.conversation_id
        && json_matches_optional(&existing.metadata_json, &new.metadata)?)
}

fn action_item_matches_new(
    existing: &crate::storage::ActionItem,
    new: &NewActionItem,
) -> anyhow::Result<bool> {
    Ok(existing.id == new.id
        && existing.conversation_id == new.conversation_id
        && existing.title == new.title
        && existing.description == new.description.clone().unwrap_or_default()
        && existing.status == new.status.clone().unwrap_or_else(|| "open".to_string())
        && existing.due_at == new.due_at
        && json_matches_optional(&existing.metadata_json, &new.metadata)?)
}

fn json_matches_optional(existing_json: &str, new: &Option<Value>) -> anyhow::Result<bool> {
    let existing: Value = serde_json::from_str(existing_json)?;
    Ok(existing == new.clone().unwrap_or_else(|| json!({})))
}
