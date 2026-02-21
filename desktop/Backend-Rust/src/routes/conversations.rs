// Conversations routes - Port from Python backend
// Endpoints: GET /v1/conversations, POST /v1/conversations/from-segments, POST /v1/conversations/:id/reprocess

use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    routing::{get, patch, post},
    Json, Router,
};

use serde::{Deserialize, Serialize};

use crate::auth::AuthUser;
use crate::llm::LlmClient;
use crate::models::{
    Conversation, ConversationSource, ConversationStatus, CreateConversationRequest,
    CreateConversationResponse, Structured, TranscriptSegment,
};
use crate::AppState;

#[derive(Deserialize)]
pub struct GetConversationsQuery {
    #[serde(default = "default_limit")]
    pub limit: usize,
    #[serde(default)]
    pub offset: usize,
    #[serde(default = "default_include_discarded")]
    pub include_discarded: bool,
    #[serde(default = "default_statuses")]
    pub statuses: String,
    /// Filter by starred status (true = only starred, false/null = all)
    pub starred: Option<bool>,
    /// Filter by folder ID
    pub folder_id: Option<String>,
    /// Filter by start date (ISO 8601 format)
    pub start_date: Option<String>,
    /// Filter by end date (ISO 8601 format)
    pub end_date: Option<String>,
}

fn default_limit() -> usize {
    100 // Match Python default
}

fn default_include_discarded() -> bool {
    true // Match Python router default
}

fn default_statuses() -> String {
    "processing,completed".to_string() // Match Python default
}

/// GET /v1/conversations - Fetch user conversations
async fn get_conversations(
    State(state): State<AppState>,
    user: AuthUser,
    Query(query): Query<GetConversationsQuery>,
) -> Result<Json<Vec<Conversation>>, (StatusCode, String)> {
    // Parse statuses from comma-separated string (match Python behavior)
    let statuses: Vec<String> = if query.statuses.is_empty() {
        vec![]
    } else {
        query.statuses.split(',').map(|s| s.trim().to_string()).collect()
    };

    tracing::info!(
        "Getting conversations for user {} with limit={}, offset={}, include_discarded={}, statuses={:?}, starred={:?}, folder_id={:?}, start_date={:?}, end_date={:?}",
        user.uid,
        query.limit,
        query.offset,
        query.include_discarded,
        statuses,
        query.starred,
        query.folder_id,
        query.start_date,
        query.end_date
    );

    match state
        .firestore
        .get_conversations(
            &user.uid,
            query.limit,
            query.offset,
            query.include_discarded,
            &statuses,
            query.starred,
            query.folder_id.as_deref(),
            query.start_date.as_deref(),
            query.end_date.as_deref(),
        )
        .await
    {
        Ok(conversations) => {
            // Debug: log any conversations with empty titles
            for conv in &conversations {
                if conv.structured.title.is_empty() {
                    tracing::warn!(
                        "DEBUG: Conversation {} has empty title! structured={:?}",
                        conv.id,
                        conv.structured
                    );
                }
            }
            Ok(Json(conversations))
        }
        Err(e) => {
            tracing::error!("Failed to get conversations: {}", e);
            Err((StatusCode::INTERNAL_SERVER_ERROR, format!("Failed to get conversations: {}", e)))
        }
    }
}

#[derive(Deserialize)]
pub struct GetConversationsCountQuery {
    #[serde(default = "default_include_discarded")]
    pub include_discarded: bool,
    #[serde(default = "default_statuses")]
    pub statuses: String,
}

#[derive(Serialize)]
pub struct ConversationsCountResponse {
    pub count: i64,
}

/// GET /v1/conversations/count - Get count of user conversations
async fn get_conversations_count(
    State(state): State<AppState>,
    user: AuthUser,
    Query(query): Query<GetConversationsCountQuery>,
) -> Result<Json<ConversationsCountResponse>, (StatusCode, String)> {
    let statuses: Vec<String> = if query.statuses.is_empty() {
        vec![]
    } else {
        query.statuses.split(',').map(|s| s.trim().to_string()).collect()
    };

    tracing::info!(
        "Getting conversations count for user {} with include_discarded={}, statuses={:?}",
        user.uid,
        query.include_discarded,
        statuses
    );

    match state
        .firestore
        .get_conversations_count(&user.uid, query.include_discarded, &statuses)
        .await
    {
        Ok(count) => Ok(Json(ConversationsCountResponse { count })),
        Err(e) => {
            tracing::error!("Failed to get conversations count: {}", e);
            Err((StatusCode::INTERNAL_SERVER_ERROR, format!("Failed to get conversations count: {}", e)))
        }
    }
}

/// POST /v1/conversations/from-segments - Create conversation from transcript
/// Copied from Python create_conversation_from_segments
async fn create_conversation_from_segments(
    State(state): State<AppState>,
    user: AuthUser,
    Json(request): Json<CreateConversationRequest>,
) -> Result<Json<CreateConversationResponse>, (StatusCode, String)> {
    tracing::info!(
        "Creating conversation for user {} from {} segments",
        user.uid,
        request.transcript_segments.len()
    );

    // Only process desktop-originated conversations with LLM.
    // Non-desktop sources (omi, bee, etc.) are fully handled by the Python backend.
    let is_desktop = request.source == ConversationSource::Desktop;

    let processed = if is_desktop {
        // Get LLM client (Gemini)
        let llm_client = if let Some(api_key) = &state.config.gemini_api_key {
            LlmClient::new(api_key.clone())
        } else {
            return Err((
                StatusCode::INTERNAL_SERVER_ERROR,
                "GEMINI_API_KEY not configured".to_string(),
            ));
        };

        // Get existing data for deduplication
        let existing_memories = state
            .firestore
            .get_memories(&user.uid, 500)
            .await
            .unwrap_or_default();

        // Fetch recent action items + staged tasks for dedup context
        let two_days_ago = (chrono::Utc::now() - chrono::Duration::days(2)).to_rfc3339();
        let mut existing_action_items: Vec<crate::models::ActionItem> = state
            .firestore
            .get_action_items(&user.uid, 50, 0, None, None, Some(&two_days_ago), None, None, None, None, None)
            .await
            .unwrap_or_default()
            .into_iter()
            .map(|db_item| crate::models::ActionItem {
                description: db_item.description,
                completed: db_item.completed,
                due_at: db_item.due_at,
                confidence: None,
                priority: db_item.priority,
            })
            .collect();

        // Also include staged tasks (recent extractions not yet promoted)
        if let Ok(staged) = state.firestore.get_staged_tasks(&user.uid, 50, 0).await {
            existing_action_items.extend(staged.into_iter().map(|s| crate::models::ActionItem {
                description: s.description,
                completed: false,
                due_at: s.due_at,
                confidence: None,
                priority: s.priority,
            }));
        }

        // Format timestamps
        let started_at = request.started_at.to_rfc3339();
        let user_name = user.name.as_deref().unwrap_or("User");

        llm_client
            .process_conversation(
                &request.transcript_segments,
                &started_at,
                &request.timezone,
                &request.language,
                user_name,
                &existing_action_items,
                &existing_memories,
            )
            .await
            .map_err(|e| {
                tracing::error!("Failed to process conversation: {}", e);
                (StatusCode::INTERNAL_SERVER_ERROR, e.to_string())
            })?
    } else {
        // Non-desktop: skip all LLM extraction (Python backend handles it)
        tracing::info!("Skipping LLM extraction for non-desktop source {:?}", request.source);
        LlmClient::skip_extraction()
    };

    // Generate conversation ID
    let conversation_id = uuid::Uuid::new_v4().to_string();

    if processed.discarded {
        return Ok(Json(CreateConversationResponse {
            id: conversation_id,
            status: "completed".to_string(),
            discarded: true,
        }));
    }

    // Create conversation object
    let conversation = Conversation {
        id: conversation_id.clone(),
        created_at: request.started_at,
        started_at: request.started_at,
        finished_at: request.finished_at,
        source: request.source.clone(),
        language: request.language.clone(),
        status: ConversationStatus::Completed,
        discarded: false,
        deleted: false,
        starred: false,
        is_locked: false,
        structured: processed.structured,
        transcript_segments: request.transcript_segments.clone(),
        apps_results: vec![],
        folder_id: None,
        geolocation: None,
        photos: vec![],
        input_device_name: request.input_device_name.clone(),
    };

    // Save conversation
    if let Err(e) = state.firestore.save_conversation(&user.uid, &conversation).await {
        tracing::error!("Failed to save conversation: {}", e);
        return Err((StatusCode::INTERNAL_SERVER_ERROR, e.to_string()));
    }

    // Save action items as staged tasks (go through ranking/promotion pipeline)
    if !processed.action_items.is_empty() {
        let source_str = format!("transcription:{:?}", request.source).to_lowercase();
        for item in &processed.action_items {
            if let Err(e) = state
                .firestore
                .create_staged_task(
                    &user.uid,
                    &item.description,
                    item.due_at,
                    Some(&source_str),
                    item.priority.as_deref(),
                    None, // metadata
                    None, // category
                    None, // relevance_score - will be ranked by prioritization service
                )
                .await
            {
                tracing::error!("Failed to save staged task: {}", e);
            }
        }
        tracing::info!(
            "Saved {} action items as staged tasks for conversation {}",
            processed.action_items.len(),
            conversation_id
        );
    }

    // Save memories
    if !processed.memories.is_empty() {
        if let Err(e) = state
            .firestore
            .save_memories(&user.uid, &conversation_id, &processed.memories)
            .await
        {
            tracing::error!("Failed to save memories: {}", e);
        }
    }

    // Trigger external integrations (async, don't block response)
    let integrations = state.integrations.clone();
    let firestore = state.firestore.clone();
    let uid = user.uid.clone();
    let conv_for_trigger = conversation.clone();

    tokio::spawn(async move {
        // Get user's enabled apps with full details
        match firestore.get_enabled_apps_full(&uid).await {
            Ok(enabled_apps) => {
                let results = integrations
                    .trigger_conversation_created(&uid, &conv_for_trigger, &enabled_apps)
                    .await;

                if !results.is_empty() {
                    let successful = results.iter().filter(|r| r.success).count();
                    let failed = results.len() - successful;
                    tracing::info!(
                        "Integration triggers completed: {} successful, {} failed",
                        successful,
                        failed
                    );
                }
            }
            Err(e) => {
                tracing::error!("Failed to get enabled apps for integration triggers: {}", e);
            }
        }
    });

    Ok(Json(CreateConversationResponse {
        id: conversation_id,
        status: "completed".to_string(),
        discarded: false,
    }))
}

#[derive(Deserialize)]
pub struct ReprocessRequest {
    app_id: String,
}

#[derive(Serialize)]
pub struct ReprocessResponse {
    success: bool,
    message: String,
    content: Option<String>,
}

/// POST /v1/conversations/:id/reprocess - Reprocess conversation with a specific app
async fn reprocess_conversation(
    State(state): State<AppState>,
    user: AuthUser,
    Path(conversation_id): Path<String>,
    Json(request): Json<ReprocessRequest>,
) -> Result<Json<ReprocessResponse>, (StatusCode, String)> {
    tracing::info!(
        "Reprocessing conversation {} with app {} for user {}",
        conversation_id,
        request.app_id,
        user.uid
    );

    // Fetch the conversation
    let conversation = state
        .firestore
        .get_conversation(&user.uid, &conversation_id)
        .await
        .map_err(|e| {
            tracing::error!("Failed to get conversation: {}", e);
            (StatusCode::NOT_FOUND, format!("Conversation not found: {}", e))
        })?
        .ok_or_else(|| {
            (StatusCode::NOT_FOUND, "Conversation not found".to_string())
        })?;

    // Fetch the app
    let app = state
        .firestore
        .get_app(&user.uid, &request.app_id)
        .await
        .map_err(|e| {
            tracing::error!("Failed to get app: {}", e);
            (StatusCode::NOT_FOUND, format!("App not found: {}", e))
        })?
        .ok_or_else(|| {
            (StatusCode::NOT_FOUND, "App not found".to_string())
        })?;

    // Check if app has memories capability
    if !app.capabilities.contains(&"memories".to_string()) {
        return Err((
            StatusCode::BAD_REQUEST,
            "App does not have memories capability".to_string(),
        ));
    }

    // Get the app's memory prompt
    let memory_prompt = app.memory_prompt.unwrap_or_else(|| {
        "Analyze this conversation and provide insights.".to_string()
    });

    // Get LLM client (Gemini)
    let llm_client = if let Some(api_key) = &state.config.gemini_api_key {
        LlmClient::new(api_key.clone())
    } else {
        return Err((
            StatusCode::INTERNAL_SERVER_ERROR,
            "GEMINI_API_KEY not configured".to_string(),
        ));
    };

    // Build transcript text
    let transcript_text: String = conversation
        .transcript_segments
        .iter()
        .map(|s| {
            let speaker = if s.is_user { user.name.clone().unwrap_or_else(|| "User".to_string()) } else { format!("Speaker {}", s.speaker_id) };
            format!("{}: {}", speaker, s.text)
        })
        .collect::<Vec<_>>()
        .join("\n");

    // Run the app's memory prompt against the conversation
    let result = llm_client
        .run_memory_prompt(&memory_prompt, &transcript_text, &conversation.structured)
        .await
        .map_err(|e| {
            tracing::error!("Failed to run memory prompt: {}", e);
            (StatusCode::INTERNAL_SERVER_ERROR, format!("Failed to process: {}", e))
        })?;

    // Save the app result to the conversation
    if let Err(e) = state
        .firestore
        .add_app_result(&user.uid, &conversation_id, &request.app_id, &result)
        .await
    {
        tracing::error!("Failed to save app result: {}", e);
        // Continue anyway, just log the error
    }

    Ok(Json(ReprocessResponse {
        success: true,
        message: format!("Conversation reprocessed with {}", app.name),
        content: Some(result),
    }))
}

// Search request/response models
#[derive(Deserialize)]
pub struct SearchConversationsRequest {
    pub query: String,
    #[serde(default = "default_page")]
    pub page: usize,
    #[serde(default = "default_per_page")]
    pub per_page: usize,
    #[serde(default)]
    pub include_discarded: bool,
}

fn default_page() -> usize {
    1
}

fn default_per_page() -> usize {
    10
}

#[derive(Serialize)]
pub struct SearchConversationsResponse {
    pub items: Vec<Conversation>,
    pub total_pages: usize,
    pub current_page: usize,
    pub per_page: usize,
}

/// POST /v1/conversations/search - Search conversations by title and overview
async fn search_conversations(
    State(state): State<AppState>,
    user: AuthUser,
    Json(request): Json<SearchConversationsRequest>,
) -> Result<Json<SearchConversationsResponse>, (StatusCode, String)> {
    tracing::info!(
        "Searching conversations for user {} with query '{}', page={}, per_page={}",
        user.uid,
        request.query,
        request.page,
        request.per_page
    );

    // Fetch all conversations (we'll filter in memory since Firestore doesn't support full-text search)
    let all_conversations = match state
        .firestore
        .get_conversations(&user.uid, 500, 0, request.include_discarded, &["completed".to_string()], None, None, None, None)
        .await
    {
        Ok(convs) => convs,
        Err(e) => {
            tracing::error!("Failed to get conversations for search: {}", e);
            return Err((StatusCode::INTERNAL_SERVER_ERROR, format!("Failed to search: {}", e)));
        }
    };

    // Filter by query (case-insensitive search in title and overview)
    let query_lower = request.query.to_lowercase();
    let filtered: Vec<Conversation> = all_conversations
        .into_iter()
        .filter(|conv| {
            let title_match = conv.structured.title.to_lowercase().contains(&query_lower);
            let overview_match = conv.structured.overview.to_lowercase().contains(&query_lower);
            title_match || overview_match
        })
        .collect();

    // Paginate results
    let total_count = filtered.len();
    let total_pages = (total_count + request.per_page - 1) / request.per_page.max(1);
    let start_idx = (request.page.saturating_sub(1)) * request.per_page;
    let items: Vec<Conversation> = filtered
        .into_iter()
        .skip(start_idx)
        .take(request.per_page)
        .collect();

    tracing::info!("Search found {} total matches, returning {} items", total_count, items.len());

    Ok(Json(SearchConversationsResponse {
        items,
        total_pages,
        current_page: request.page,
        per_page: request.per_page,
    }))
}

#[derive(Deserialize)]
pub struct StarredParams {
    starred: bool,
}

#[derive(Serialize)]
pub struct StatusResponse {
    status: String,
}

/// PATCH /v1/conversations/:id/starred - Set conversation starred status
async fn set_conversation_starred(
    State(state): State<AppState>,
    user: AuthUser,
    Path(conversation_id): Path<String>,
    Query(params): Query<StarredParams>,
) -> Result<Json<StatusResponse>, StatusCode> {
    tracing::info!(
        "Setting conversation {} starred={} for user {}",
        conversation_id,
        params.starred,
        user.uid
    );

    match state
        .firestore
        .set_conversation_starred(&user.uid, &conversation_id, params.starred)
        .await
    {
        Ok(()) => Ok(Json(StatusResponse {
            status: "ok".to_string(),
        })),
        Err(e) => {
            tracing::error!("Failed to set starred: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

#[derive(Deserialize)]
pub struct UpdateConversationRequest {
    title: Option<String>,
}

/// GET /v1/conversations/:id - Get a single conversation by ID
async fn get_conversation_by_id(
    State(state): State<AppState>,
    user: AuthUser,
    Path(conversation_id): Path<String>,
) -> Result<Json<Conversation>, (StatusCode, String)> {
    tracing::info!(
        "Getting conversation {} for user {}",
        conversation_id,
        user.uid
    );

    match state
        .firestore
        .get_conversation(&user.uid, &conversation_id)
        .await
    {
        Ok(Some(conversation)) => Ok(Json(conversation)),
        Ok(None) => Err((StatusCode::NOT_FOUND, "Conversation not found".to_string())),
        Err(e) => {
            tracing::error!("Failed to get conversation: {}", e);
            Err((StatusCode::INTERNAL_SERVER_ERROR, format!("Failed to get conversation: {}", e)))
        }
    }
}

/// DELETE /v1/conversations/:id - Delete a conversation
async fn delete_conversation(
    State(state): State<AppState>,
    user: AuthUser,
    Path(conversation_id): Path<String>,
) -> Result<StatusCode, StatusCode> {
    tracing::info!(
        "Deleting conversation {} for user {}",
        conversation_id,
        user.uid
    );

    match state
        .firestore
        .delete_conversation(&user.uid, &conversation_id)
        .await
    {
        Ok(()) => Ok(StatusCode::NO_CONTENT),
        Err(e) => {
            tracing::error!("Failed to delete conversation: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

/// PATCH /v1/conversations/:id - Update a conversation (title, etc.)
async fn update_conversation(
    State(state): State<AppState>,
    user: AuthUser,
    Path(conversation_id): Path<String>,
    Json(request): Json<UpdateConversationRequest>,
) -> Result<Json<StatusResponse>, StatusCode> {
    tracing::info!(
        "Updating conversation {} for user {}",
        conversation_id,
        user.uid
    );

    // Update title if provided
    if let Some(title) = &request.title {
        match state
            .firestore
            .update_conversation_title(&user.uid, &conversation_id, title)
            .await
        {
            Ok(()) => {},
            Err(e) => {
                tracing::error!("Failed to update conversation title: {}", e);
                return Err(StatusCode::INTERNAL_SERVER_ERROR);
            }
        }
    }

    Ok(Json(StatusResponse {
        status: "ok".to_string(),
    }))
}

// ============================================================================
// MERGE CONVERSATIONS
// ============================================================================

#[derive(Debug, Deserialize)]
pub struct MergeConversationsRequest {
    /// IDs of conversations to merge (minimum 2)
    conversation_ids: Vec<String>,
    /// Whether to regenerate summary from merged transcript
    #[serde(default = "default_reprocess")]
    reprocess: bool,
}

fn default_reprocess() -> bool {
    true
}

#[derive(Debug, Serialize)]
pub struct MergeConversationsResponse {
    status: String,
    message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    warning: Option<String>,
    conversation_ids: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    new_conversation_id: Option<String>,
}

/// POST /v1/conversations/merge - Merge multiple conversations into one
async fn merge_conversations(
    State(state): State<AppState>,
    user: AuthUser,
    Json(request): Json<MergeConversationsRequest>,
) -> Result<Json<MergeConversationsResponse>, (StatusCode, String)> {
    tracing::info!(
        "Merging {} conversations for user {}",
        request.conversation_ids.len(),
        user.uid
    );

    // Validate minimum number of conversations
    if request.conversation_ids.len() < 2 {
        return Err((
            StatusCode::BAD_REQUEST,
            "At least 2 conversations required to merge".to_string(),
        ));
    }

    // Fetch all conversations
    let mut conversations = Vec::new();
    for conv_id in &request.conversation_ids {
        match state.firestore.get_conversation(&user.uid, conv_id).await {
            Ok(Some(conv)) => conversations.push(conv),
            Ok(None) => {
                return Err((
                    StatusCode::NOT_FOUND,
                    format!("Conversation {} not found", conv_id),
                ));
            }
            Err(e) => {
                return Err((
                    StatusCode::INTERNAL_SERVER_ERROR,
                    format!("Failed to fetch conversation {}: {}", conv_id, e),
                ));
            }
        }
    }

    // Validate all are completed
    for conv in &conversations {
        if conv.status != ConversationStatus::Completed {
            return Err((
                StatusCode::BAD_REQUEST,
                format!(
                    "Conversation {} is not ready (status: {:?}). Wait for it to complete.",
                    conv.id, conv.status
                ),
            ));
        }
    }

    // Sort by started_at
    conversations.sort_by(|a, b| a.started_at.cmp(&b.started_at));

    // Check for large time gaps (warn but don't reject)
    let mut warnings = Vec::new();
    for i in 1..conversations.len() {
        let prev_finished = conversations[i - 1].finished_at;
        let curr_started = conversations[i].started_at;
        let gap_hours = (curr_started - prev_finished).num_seconds() as f64 / 3600.0;
        if gap_hours > 1.0 {
            warnings.push(format!("{:.1}h gap detected", gap_hours));
        }
    }
    let warning_msg = if warnings.is_empty() {
        None
    } else {
        Some(warnings.join("; "))
    };

    // Merge transcript segments with adjusted timestamps
    let merged_segments = merge_transcript_segments(&conversations);

    // Generate new conversation ID
    let new_conversation_id = uuid::Uuid::new_v4().to_string();

    // Use earliest conversation's dates and properties
    let first = &conversations[0];
    let last = conversations.last().unwrap();

    // Create merged conversation
    let mut merged_conversation = Conversation {
        id: new_conversation_id.clone(),
        created_at: first.created_at,
        started_at: first.started_at,
        finished_at: last.finished_at,
        source: first.source.clone(),
        language: first.language.clone(),
        status: ConversationStatus::Processing,
        discarded: false,
        deleted: false,
        starred: false,
        is_locked: false,
        structured: Structured {
            title: format!("Merged: {} conversations", conversations.len()),
            overview: "Processing merged conversation...".to_string(),
            emoji: "🔗".to_string(),
            category: first.structured.category.clone(),
            action_items: vec![],
            events: vec![],
        },
        transcript_segments: merged_segments,
        apps_results: vec![],
        folder_id: first.folder_id.clone(),
        geolocation: first.geolocation.clone(),
        photos: vec![],
        input_device_name: first.input_device_name.clone(),
    };

    // If reprocessing is requested and we have an LLM client, process the merged conversation
    if request.reprocess {
        if let Some(api_key) = &state.config.gemini_api_key {
            let llm = LlmClient::new(api_key.clone());

            // Get existing data for deduplication
            let existing_memories = state
                .firestore
                .get_memories(&user.uid, 500)
                .await
                .unwrap_or_default();

            let started_at_str = merged_conversation.started_at.to_rfc3339();

            // Process with LLM
            match llm
                .process_conversation(
                    &merged_conversation.transcript_segments,
                    &started_at_str,
                    "UTC",
                    &merged_conversation.language,
                    user.name.as_deref().unwrap_or("User"),
                    &[],
                    &existing_memories,
                )
                .await
            {
                Ok(processed) => {
                    merged_conversation.structured = processed.structured;
                    // Append "(merged)" to title to indicate this is a merged conversation
                    merged_conversation.structured.title = format!("{} (merged)", merged_conversation.structured.title);
                    merged_conversation.status = ConversationStatus::Completed;

                    // Save action items as staged tasks
                    if !processed.action_items.is_empty() {
                        let source_str = format!("transcription:{:?}", merged_conversation.source).to_lowercase();
                        for item in &processed.action_items {
                            let _ = state
                                .firestore
                                .create_staged_task(
                                    &user.uid,
                                    &item.description,
                                    item.due_at,
                                    Some(&source_str),
                                    item.priority.as_deref(),
                                    None,
                                    None,
                                    None,
                                )
                                .await;
                        }
                    }

                    // Save memories if any
                    if !processed.memories.is_empty() {
                        let _ = state
                            .firestore
                            .save_memories(&user.uid, &new_conversation_id, &processed.memories)
                            .await;
                    }
                }
                Err(e) => {
                    tracing::error!("Failed to process merged conversation: {}", e);
                    // Mark as completed anyway
                    merged_conversation.status = ConversationStatus::Completed;
                }
            }
        } else {
            // No LLM key, just mark as completed
            merged_conversation.status = ConversationStatus::Completed;
        }
    } else {
        merged_conversation.status = ConversationStatus::Completed;
    }

    // Save the merged conversation
    if let Err(e) = state
        .firestore
        .save_conversation(&user.uid, &merged_conversation)
        .await
    {
        tracing::error!("Failed to save merged conversation: {}", e);
        return Err((
            StatusCode::INTERNAL_SERVER_ERROR,
            format!("Failed to save merged conversation: {}", e),
        ));
    }

    // Delete source conversations
    for conv_id in &request.conversation_ids {
        if let Err(e) = state.firestore.delete_conversation(&user.uid, conv_id).await {
            tracing::warn!("Failed to delete source conversation {}: {}", conv_id, e);
            // Continue anyway - merged conversation is already saved
        }
    }

    tracing::info!(
        "Merge completed: {} conversations -> {}",
        request.conversation_ids.len(),
        new_conversation_id
    );

    Ok(Json(MergeConversationsResponse {
        status: "completed".to_string(),
        message: format!(
            "Successfully merged {} conversations",
            request.conversation_ids.len()
        ),
        warning: warning_msg,
        conversation_ids: request.conversation_ids,
        new_conversation_id: Some(new_conversation_id),
    }))
}

/// Merge transcript segments from multiple conversations with adjusted timestamps
fn merge_transcript_segments(conversations: &[Conversation]) -> Vec<TranscriptSegment> {
    let mut merged = Vec::new();
    let mut cumulative_offset = 0.0;

    for (i, conv) in conversations.iter().enumerate() {
        if i == 0 {
            // First conversation - use segments as-is
            merged.extend(conv.transcript_segments.iter().cloned());
            if !conv.transcript_segments.is_empty() {
                cumulative_offset = conv
                    .transcript_segments
                    .iter()
                    .map(|s| s.end)
                    .fold(0.0f64, |a, b| a.max(b));
            } else {
                cumulative_offset = (conv.finished_at - conv.started_at).num_seconds() as f64;
            }
        } else {
            // Calculate gap from previous conversation
            let prev = &conversations[i - 1];
            let gap = (conv.started_at - prev.finished_at).num_seconds() as f64;
            let offset = cumulative_offset + gap.max(0.0);

            // Adjust timestamps for this conversation's segments
            for seg in &conv.transcript_segments {
                let mut seg_copy = seg.clone();
                seg_copy.start += offset;
                seg_copy.end += offset;
                merged.push(seg_copy);
            }

            // Update cumulative offset
            if !conv.transcript_segments.is_empty() {
                cumulative_offset = offset
                    + conv
                        .transcript_segments
                        .iter()
                        .map(|s| s.end)
                        .fold(0.0f64, |a, b| a.max(b));
            } else {
                let duration = (conv.finished_at - conv.started_at).num_seconds() as f64;
                cumulative_offset = offset + duration;
            }
        }
    }

    merged
}

// ============================================================================
// CONVERSATION VISIBILITY / SHARING
// ============================================================================

#[derive(Deserialize)]
pub struct VisibilityParams {
    /// Visibility value: "shared", "public", or "private"
    value: String,
    /// Alternative parameter name (Flutter app sends both)
    #[serde(default)]
    visibility: Option<String>,
}

/// PATCH /v1/conversations/:id/visibility - Set conversation visibility for sharing
/// When set to "shared" or "public", the conversation becomes accessible via /shared endpoint
async fn set_conversation_visibility(
    State(state): State<AppState>,
    user: AuthUser,
    Path(conversation_id): Path<String>,
    Query(params): Query<VisibilityParams>,
) -> Result<Json<StatusResponse>, (StatusCode, String)> {
    // Use value parameter, or fall back to visibility parameter
    let visibility = params.visibility.unwrap_or(params.value);

    tracing::info!(
        "Setting conversation {} visibility to '{}' for user {}",
        conversation_id,
        visibility,
        user.uid
    );

    // Verify conversation exists and belongs to user
    let _conversation = state
        .firestore
        .get_conversation(&user.uid, &conversation_id)
        .await
        .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?
        .ok_or_else(|| (StatusCode::NOT_FOUND, "Conversation not found".to_string()))?;

    // Update visibility in Firestore
    if let Err(e) = state
        .firestore
        .set_conversation_visibility(&user.uid, &conversation_id, &visibility)
        .await
    {
        tracing::error!("Failed to set visibility in Firestore: {}", e);
        return Err((StatusCode::INTERNAL_SERVER_ERROR, e.to_string()));
    }

    // Update Redis for fast lookup
    if let Some(redis) = &state.redis {
        let is_public = visibility == "shared" || visibility == "public";

        if is_public {
            // Store the uid mapping and add to public set
            if let Err(e) = redis.store_conversation_to_uid(&conversation_id, &user.uid).await {
                tracing::error!("Failed to store conversation visibility in Redis: {}", e);
                // Continue anyway - Firestore has the source of truth
            }
            if let Err(e) = redis.add_public_conversation(&conversation_id).await {
                tracing::error!("Failed to add to public conversations in Redis: {}", e);
            }
        } else {
            // Remove from Redis
            if let Err(e) = redis.remove_conversation_to_uid(&conversation_id).await {
                tracing::error!("Failed to remove conversation visibility from Redis: {}", e);
            }
            if let Err(e) = redis.remove_public_conversation(&conversation_id).await {
                tracing::error!("Failed to remove from public conversations in Redis: {}", e);
            }
        }
    } else {
        tracing::warn!("Redis not configured - conversation sharing may not work with web viewer");
    }

    tracing::info!(
        "Conversation {} visibility set to '{}' successfully",
        conversation_id,
        visibility
    );

    Ok(Json(StatusResponse {
        status: "Ok".to_string(),
    }))
}

/// GET /v1/conversations/:id/shared - Get a shared/public conversation (no authentication required)
/// This endpoint is used by the web viewer at h.omi.me/memories/{id}
async fn get_shared_conversation(
    State(state): State<AppState>,
    Path(conversation_id): Path<String>,
) -> Result<Json<Conversation>, (StatusCode, String)> {
    tracing::info!("Getting shared conversation {}", conversation_id);

    // First, try to get the owner uid from Redis
    let uid = if let Some(redis) = &state.redis {
        match redis.get_conversation_uid(&conversation_id).await {
            Ok(Some(uid)) => uid,
            Ok(None) => {
                tracing::info!("Conversation {} not found in Redis (not shared)", conversation_id);
                return Err((StatusCode::NOT_FOUND, "Conversation is private".to_string()));
            }
            Err(e) => {
                tracing::error!("Redis error looking up conversation: {}", e);
                return Err((StatusCode::INTERNAL_SERVER_ERROR, "Failed to lookup conversation".to_string()));
            }
        }
    } else {
        // No Redis - can't serve shared conversations
        tracing::error!("Redis not configured - cannot serve shared conversations");
        return Err((StatusCode::SERVICE_UNAVAILABLE, "Sharing service unavailable".to_string()));
    };

    // Fetch the conversation from Firestore
    let conversation = state
        .firestore
        .get_conversation(&uid, &conversation_id)
        .await
        .map_err(|e| {
            tracing::error!("Failed to get conversation from Firestore: {}", e);
            (StatusCode::INTERNAL_SERVER_ERROR, e.to_string())
        })?
        .ok_or_else(|| {
            tracing::info!("Conversation {} not found in Firestore", conversation_id);
            (StatusCode::NOT_FOUND, "Conversation not found".to_string())
        })?;

    // Verify the conversation is actually public/shared
    // The visibility field should be checked if it exists
    // For now, we trust Redis - if it's in Redis, it was explicitly shared

    // Return the conversation (without sensitive data like geolocation)
    let mut response = conversation;
    response.geolocation = None;

    Ok(Json(response))
}

pub fn conversations_routes() -> Router<AppState> {
    Router::new()
        .route("/v1/conversations", get(get_conversations))
        .route("/v1/conversations/count", get(get_conversations_count))
        .route("/v1/conversations/search", post(search_conversations))
        .route("/v1/conversations/merge", post(merge_conversations))
        .route(
            "/v1/conversations/from-segments",
            post(create_conversation_from_segments),
        )
        .route(
            "/v1/conversations/:id/reprocess",
            post(reprocess_conversation),
        )
        .route(
            "/v1/conversations/:id/starred",
            patch(set_conversation_starred),
        )
        .route(
            "/v1/conversations/:id/visibility",
            patch(set_conversation_visibility),
        )
        .route(
            "/v1/conversations/:id/shared",
            get(get_shared_conversation),
        )
        .route(
            "/v1/conversations/:id",
            get(get_conversation_by_id).patch(update_conversation).delete(delete_conversation),
        )
}
