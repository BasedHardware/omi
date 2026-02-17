// Personas routes - AI persona/clone feature
// Endpoints for persona CRUD and prompt generation

use axum::{
    extract::{Query, State},
    http::StatusCode,
    routing::{delete, get, patch, post},
    Json, Router,
};

use crate::auth::AuthUser;
use crate::llm::LlmClient;
use crate::models::{
    CheckUsernameQuery, CreatePersonaRequest, GeneratePromptRequest, GeneratePromptResponse,
    PersonaResponse, PersonaStatusResponse, UpdatePersonaRequest, UsernameAvailableResponse,
};
use crate::AppState;

// ============================================================================
// Persona CRUD Endpoints
// ============================================================================

/// GET /v1/personas - Get user's persona
async fn get_persona(
    State(state): State<AppState>,
    user: AuthUser,
) -> Result<Json<Option<PersonaResponse>>, (StatusCode, String)> {
    tracing::info!("Getting persona for user {}", user.uid);

    match state.firestore.get_user_persona(&user.uid).await {
        Ok(Some(persona)) => {
            // Get public memories count
            let memories_count = state
                .firestore
                .count_public_memories(&user.uid)
                .await
                .unwrap_or(0);

            Ok(Json(Some(persona.to_response(Some(memories_count)))))
        }
        Ok(None) => Ok(Json(None)),
        Err(e) => {
            tracing::error!("Failed to get persona: {}", e);
            Err((
                StatusCode::INTERNAL_SERVER_ERROR,
                format!("Failed to get persona: {}", e),
            ))
        }
    }
}

/// POST /v1/personas - Create a new persona
async fn create_persona(
    State(state): State<AppState>,
    user: AuthUser,
    Json(request): Json<CreatePersonaRequest>,
) -> Result<Json<PersonaResponse>, (StatusCode, String)> {
    tracing::info!("Creating persona for user {} with name: {}", user.uid, request.name);

    // Check if user already has a persona
    if let Ok(Some(_)) = state.firestore.get_user_persona(&user.uid).await {
        return Err((
            StatusCode::CONFLICT,
            "User already has a persona. Delete the existing one first.".to_string(),
        ));
    }

    // Validate username if provided
    if let Some(ref username) = request.username {
        if !is_valid_username(username) {
            return Err((
                StatusCode::BAD_REQUEST,
                "Invalid username. Use 3-30 lowercase letters, numbers, and underscores.".to_string(),
            ));
        }

        // Check availability
        match state.firestore.is_username_available(username).await {
            Ok(false) => {
                return Err((
                    StatusCode::CONFLICT,
                    "Username is already taken.".to_string(),
                ));
            }
            Err(e) => {
                tracing::error!("Failed to check username: {}", e);
                return Err((
                    StatusCode::INTERNAL_SERVER_ERROR,
                    "Failed to check username availability.".to_string(),
                ));
            }
            _ => {}
        }
    }

    // Get public memories for persona generation
    let memories = match state.firestore.get_public_memories(&user.uid, 250).await {
        Ok(m) => m,
        Err(e) => {
            tracing::error!("Failed to get memories: {}", e);
            return Err((
                StatusCode::INTERNAL_SERVER_ERROR,
                format!("Failed to get memories: {}", e),
            ));
        }
    };

    // Generate persona prompt if we have memories
    let (description, persona_prompt) = if !memories.is_empty() {
        if let Some(api_key) = &state.config.gemini_api_key {
            let llm = LlmClient::new(api_key.clone());
            match llm.generate_persona_from_memories(&request.name, &memories).await {
                Ok(result) => (result.description, Some(result.persona_prompt)),
                Err(e) => {
                    tracing::warn!("Failed to generate persona prompt: {}", e);
                    (format!("AI clone of {}", request.name), None)
                }
            }
        } else {
            tracing::warn!("No Gemini API key configured for persona generation");
            (format!("AI clone of {}", request.name), None)
        }
    } else {
        (format!("AI clone of {}. Add public memories to enhance the persona.", request.name), None)
    };

    // Create persona in Firestore
    match state
        .firestore
        .create_persona(
            &user.uid,
            &request.name,
            request.username.as_deref(),
            &description,
            persona_prompt.as_deref(),
            &request.name,  // author = name for now
            None,           // email
        )
        .await
    {
        Ok(persona) => {
            let memories_count = memories.len() as i32;
            Ok(Json(persona.to_response(Some(memories_count))))
        }
        Err(e) => {
            tracing::error!("Failed to create persona: {}", e);
            Err((
                StatusCode::INTERNAL_SERVER_ERROR,
                format!("Failed to create persona: {}", e),
            ))
        }
    }
}

/// PATCH /v1/personas - Update persona
async fn update_persona(
    State(state): State<AppState>,
    user: AuthUser,
    Json(request): Json<UpdatePersonaRequest>,
) -> Result<Json<PersonaResponse>, (StatusCode, String)> {
    tracing::info!("Updating persona for user {}", user.uid);

    // Get existing persona
    let persona = match state.firestore.get_user_persona(&user.uid).await {
        Ok(Some(p)) => p,
        Ok(None) => {
            return Err((StatusCode::NOT_FOUND, "No persona found".to_string()));
        }
        Err(e) => {
            tracing::error!("Failed to get persona: {}", e);
            return Err((
                StatusCode::INTERNAL_SERVER_ERROR,
                format!("Failed to get persona: {}", e),
            ));
        }
    };

    // Update persona
    match state
        .firestore
        .update_persona(
            &persona.id,
            request.name.as_deref(),
            request.description.as_deref(),
            request.persona_prompt.as_deref(),
            request.image.as_deref(),
        )
        .await
    {
        Ok(()) => {
            // Fetch updated persona
            match state.firestore.get_user_persona(&user.uid).await {
                Ok(Some(updated)) => {
                    let memories_count = state
                        .firestore
                        .count_public_memories(&user.uid)
                        .await
                        .unwrap_or(0);
                    Ok(Json(updated.to_response(Some(memories_count))))
                }
                _ => Err((
                    StatusCode::INTERNAL_SERVER_ERROR,
                    "Failed to fetch updated persona".to_string(),
                )),
            }
        }
        Err(e) => {
            tracing::error!("Failed to update persona: {}", e);
            Err((
                StatusCode::INTERNAL_SERVER_ERROR,
                format!("Failed to update persona: {}", e),
            ))
        }
    }
}

/// DELETE /v1/personas - Delete persona
async fn delete_persona(
    State(state): State<AppState>,
    user: AuthUser,
) -> Result<Json<PersonaStatusResponse>, (StatusCode, String)> {
    tracing::info!("Deleting persona for user {}", user.uid);

    // Get existing persona
    let persona = match state.firestore.get_user_persona(&user.uid).await {
        Ok(Some(p)) => p,
        Ok(None) => {
            return Err((StatusCode::NOT_FOUND, "No persona found".to_string()));
        }
        Err(e) => {
            tracing::error!("Failed to get persona: {}", e);
            return Err((
                StatusCode::INTERNAL_SERVER_ERROR,
                format!("Failed to get persona: {}", e),
            ));
        }
    };

    // Delete persona
    match state.firestore.delete_persona(&persona.id).await {
        Ok(()) => Ok(Json(PersonaStatusResponse {
            status: "ok".to_string(),
            message: Some("Persona deleted successfully".to_string()),
        })),
        Err(e) => {
            tracing::error!("Failed to delete persona: {}", e);
            Err((
                StatusCode::INTERNAL_SERVER_ERROR,
                format!("Failed to delete persona: {}", e),
            ))
        }
    }
}

// ============================================================================
// Persona Prompt Generation
// ============================================================================

/// POST /v1/personas/generate-prompt - Regenerate persona prompt from current memories
async fn generate_prompt(
    State(state): State<AppState>,
    user: AuthUser,
    Json(_request): Json<GeneratePromptRequest>,
) -> Result<Json<GeneratePromptResponse>, (StatusCode, String)> {
    tracing::info!("Generating persona prompt for user {}", user.uid);

    // Get existing persona
    let persona = match state.firestore.get_user_persona(&user.uid).await {
        Ok(Some(p)) => p,
        Ok(None) => {
            return Err((StatusCode::NOT_FOUND, "No persona found".to_string()));
        }
        Err(e) => {
            tracing::error!("Failed to get persona: {}", e);
            return Err((
                StatusCode::INTERNAL_SERVER_ERROR,
                format!("Failed to get persona: {}", e),
            ));
        }
    };

    // Get public memories
    let memories = match state.firestore.get_public_memories(&user.uid, 250).await {
        Ok(m) => m,
        Err(e) => {
            tracing::error!("Failed to get memories: {}", e);
            return Err((
                StatusCode::INTERNAL_SERVER_ERROR,
                format!("Failed to get memories: {}", e),
            ));
        }
    };

    if memories.is_empty() {
        return Err((
            StatusCode::BAD_REQUEST,
            "No public memories found. Make some memories public first.".to_string(),
        ));
    }

    // Generate new prompt
    let api_key = state.config.gemini_api_key.as_ref().ok_or((
        StatusCode::INTERNAL_SERVER_ERROR,
        "Gemini API key not configured".to_string(),
    ))?;

    let llm = LlmClient::new(api_key.clone());
    let result = llm
        .generate_persona_from_memories(&persona.name, &memories)
        .await
        .map_err(|e| {
            tracing::error!("Failed to generate persona: {}", e);
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                format!("Failed to generate persona: {}", e),
            )
        })?;

    // Update persona with new prompt and description
    state
        .firestore
        .update_persona(
            &persona.id,
            None,
            Some(&result.description),
            Some(&result.persona_prompt),
            None,
        )
        .await
        .map_err(|e| {
            tracing::error!("Failed to update persona: {}", e);
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                format!("Failed to update persona: {}", e),
            )
        })?;

    Ok(Json(GeneratePromptResponse {
        persona_prompt: result.persona_prompt,
        description: result.description,
        memories_used: result.memories_used,
    }))
}

// ============================================================================
// Username Validation
// ============================================================================

/// GET /v1/personas/check-username - Check if username is available
async fn check_username(
    State(state): State<AppState>,
    _user: AuthUser,
    Query(query): Query<CheckUsernameQuery>,
) -> Result<Json<UsernameAvailableResponse>, (StatusCode, String)> {
    tracing::info!("Checking username availability: {}", query.username);

    // Validate format
    if !is_valid_username(&query.username) {
        return Ok(Json(UsernameAvailableResponse {
            available: false,
            username: query.username,
        }));
    }

    match state.firestore.is_username_available(&query.username).await {
        Ok(available) => Ok(Json(UsernameAvailableResponse {
            available,
            username: query.username,
        })),
        Err(e) => {
            tracing::error!("Failed to check username: {}", e);
            Err((
                StatusCode::INTERNAL_SERVER_ERROR,
                format!("Failed to check username: {}", e),
            ))
        }
    }
}

/// Validate username format
fn is_valid_username(username: &str) -> bool {
    if username.len() < 3 || username.len() > 30 {
        return false;
    }

    username
        .chars()
        .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_')
}

// ============================================================================
// Router
// ============================================================================

pub fn personas_routes() -> Router<AppState> {
    Router::new()
        .route("/v1/personas", get(get_persona))
        .route("/v1/personas", post(create_persona))
        .route("/v1/personas", patch(update_persona))
        .route("/v1/personas", delete(delete_persona))
        .route("/v1/personas/generate-prompt", post(generate_prompt))
        .route("/v1/personas/check-username", get(check_username))
}
