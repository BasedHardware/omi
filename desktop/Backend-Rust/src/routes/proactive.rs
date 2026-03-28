// Proactive assistant endpoints — server-side Gemini Flash calls.
// Replaces client-side Swift GeminiClient usage for these services.
// Issue #6098 L3.
//
// Endpoints:
//   POST /v1/proactive/user-profile         — generate AI user profile
//   POST /v1/proactive/tasks/prioritize     — re-rank staged tasks
//   POST /v1/proactive/tasks/deduplicate    — find duplicate tasks
//   POST /v1/proactive/goals/generate       — suggest a new goal
//   POST /v1/proactive/goals/:id/advice     — get goal advice
//   POST /v1/proactive/goals/:id/extract-progress — extract progress from text

use axum::{
    extract::{Path, State},
    http::StatusCode,
    routing::post,
    Json, Router,
};
use serde::{Deserialize, Serialize};

use serde::de::DeserializeOwned;

use crate::auth::AuthUser;
use crate::llm::LlmClient;
use crate::llm::proactive_prompts;
use crate::routes::rate_limit::RateDecision;
use crate::AppState;

/// Flash model for all proactive endpoints.
const FLASH_MODEL: &str = "gemini-3-flash-preview";

// ============================================================================
// Request/Response types
// ============================================================================

#[derive(Debug, Deserialize)]
pub struct UserProfileRequest {
    /// Previous profile text for consolidation (optional).
    #[serde(default)]
    pub previous_profiles: Vec<String>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct UserProfileResponse {
    pub profile_text: String,
    pub data_sources_used: u32,
}

#[derive(Debug, Deserialize)]
pub struct PrioritizeRequest {
    // No body needed — server fetches all data from Firestore.
}

#[derive(Debug, Serialize, Deserialize)]
pub struct PrioritizeResponse {
    pub reranked_tasks: Vec<RerankedTask>,
    pub reasoning: String,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct RerankedTask {
    pub task_id: String,
    pub new_position: u32,
}

#[derive(Debug, Deserialize)]
pub struct DeduplicateRequest {
    // No body needed — server fetches all data from Firestore.
}

#[derive(Debug, Serialize, Deserialize)]
pub struct DeduplicateResponse {
    pub has_duplicates: bool,
    pub duplicate_groups: Vec<DuplicateGroup>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct DuplicateGroup {
    pub keep_id: String,
    pub delete_ids: Vec<String>,
    pub reason: String,
}

#[derive(Debug, Deserialize)]
pub struct GenerateGoalRequest {
    // No body needed — server fetches all data from Firestore.
}

#[derive(Debug, Serialize, Deserialize)]
pub struct GoalSuggestion {
    pub suggested_title: String,
    #[serde(default)]
    pub suggested_description: Option<String>,
    #[serde(default)]
    pub suggested_type: Option<String>,
    #[serde(default)]
    pub suggested_target: Option<f64>,
    #[serde(default)]
    pub suggested_min: Option<f64>,
    #[serde(default)]
    pub suggested_max: Option<f64>,
    #[serde(default)]
    pub reasoning: Option<String>,
    #[serde(default)]
    pub linked_task_ids: Vec<String>,
}

#[derive(Debug, Deserialize)]
pub struct GoalAdviceRequest {
    // No body needed — server fetches goal and context from Firestore.
}

#[derive(Debug, Serialize, Deserialize)]
pub struct GoalAdviceResponse {
    pub advice: String,
}

#[derive(Debug, Deserialize)]
pub struct ExtractProgressRequest {
    pub text: String,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct ProgressExtraction {
    pub found: bool,
    #[serde(default)]
    pub value: Option<f64>,
    #[serde(default)]
    pub reasoning: Option<String>,
}

// ============================================================================
// Helpers
// ============================================================================

/// Fence user-supplied data to mitigate prompt injection.
/// Wraps content in XML delimiters that help the model distinguish
/// system instructions from user data.
fn fence(tag: &str, content: &str) -> String {
    format!("<{tag}>\n{content}\n</{tag}>")
}

/// Parse JSON with truncation repair. Mirrors parse_or_repair_json in llm/client.rs.
fn parse_json_repairing<T: DeserializeOwned>(response: &str, label: &str) -> Result<T, String> {
    // 1. Try as-is
    if let Ok(result) = serde_json::from_str::<T>(response) {
        return Ok(result);
    }
    // 2. Try balancing braces/brackets
    let trimmed = response.trim();
    if !trimmed.is_empty() {
        let mut in_string = false;
        let mut escape_next = false;
        let mut stack: Vec<char> = Vec::new();
        for ch in trimmed.chars() {
            if escape_next { escape_next = false; continue; }
            if ch == '\\' && in_string { escape_next = true; continue; }
            if ch == '"' { in_string = !in_string; continue; }
            if in_string { continue; }
            match ch {
                '{' => stack.push('}'),
                '[' => stack.push(']'),
                '}' | ']' => { stack.pop(); }
                _ => {}
            }
        }
        let mut suffix = String::new();
        if in_string { suffix.push('"'); }
        for closer in stack.iter().rev() { suffix.push(*closer); }
        if !suffix.is_empty() {
            let repaired = format!("{}{}", trimmed, suffix);
            if let Ok(result) = serde_json::from_str::<T>(&repaired) {
                tracing::info!("Repaired truncated {} JSON (added {:?})", label, suffix);
                return Ok(result);
            }
        }
    }
    Err(format!("Failed to parse {} response: {}", label, &response[..response.len().min(200)]))
}

/// Truncate string to max_len on a valid char boundary (no panics on multi-byte).
fn truncate_chars(s: &str, max_len: usize) -> &str {
    if s.len() <= max_len { return s; }
    // Find the largest char boundary <= max_len
    let mut end = max_len;
    while !s.is_char_boundary(end) && end > 0 { end -= 1; }
    &s[..end]
}

/// Create an LlmClient configured for Flash model, or return 503.
fn flash_client(config: &crate::config::Config) -> Result<LlmClient, (StatusCode, String)> {
    let api_key = config.gemini_api_key.as_ref().ok_or_else(|| {
        (StatusCode::SERVICE_UNAVAILABLE, "Gemini API key not configured".to_string())
    })?;
    Ok(LlmClient::new(api_key.clone()).with_model(FLASH_MODEL))
}

/// Check rate limit and reject if over hard cap.
async fn check_rate_limit(state: &AppState, uid: &str) -> Result<(), (StatusCode, String)> {
    let decision = state
        .gemini_rate_limiter
        .check_and_record(uid, state.redis.as_ref())
        .await;
    if decision == RateDecision::Reject {
        return Err((
            StatusCode::TOO_MANY_REQUESTS,
            "Rate limit exceeded. Please try again later.".to_string(),
        ));
    }
    Ok(())
}

// ============================================================================
// POST /v1/proactive/user-profile
// ============================================================================

async fn generate_user_profile(
    State(state): State<AppState>,
    user: AuthUser,
    Json(request): Json<UserProfileRequest>,
) -> Result<Json<UserProfileResponse>, (StatusCode, String)> {
    check_rate_limit(&state, &user.uid).await?;
    let client = flash_client(&state.config)?;

    // Fetch context data from Firestore in parallel
    let (memories, tasks, goals, conversations, messages) = tokio::join!(
        state.firestore.get_memories(&user.uid, 100),
        state.firestore.get_action_items(&user.uid, 50, 0, None, None, None, None, None, None, None, None),
        state.firestore.get_user_goals(&user.uid, 50),
        state.firestore.get_conversations(&user.uid, 20, 0, false, &[], None, None, None, None),
        state.firestore.get_messages(&user.uid, None, None, 30, 0),
    );

    // Build user data string from available sources
    let mut data_parts: Vec<String> = Vec::new();
    let mut source_count: u32 = 0;

    if let Ok(mems) = &memories {
        if !mems.is_empty() {
            let section: Vec<String> = mems.iter()
                .map(|m| {
                    let cat = format!("[{:?}] ", m.category);
                    format!("{}{}", cat, m.content)
                })
                .collect();
            data_parts.push(format!("MEMORIES:\n{}", section.join("\n")));
            source_count += mems.len() as u32;
        }
    }

    if let Ok(items) = &tasks {
        if !items.is_empty() {
            let section: Vec<String> = items.iter()
                .map(|t| {
                    let status = if t.completed { "done" } else { "pending" };
                    let priority = t.priority.as_deref().unwrap_or("none");
                    format!("[{}/{}] {}", status, priority, t.description)
                })
                .collect();
            data_parts.push(format!("TASKS:\n{}", section.join("\n")));
            source_count += items.len() as u32;
        }
    }

    if let Ok(user_goals) = &goals {
        if !user_goals.is_empty() {
            let section: Vec<String> = user_goals.iter()
                .map(|g| {
                    let pct = if g.target_value > 0.0 {
                        (g.current_value / g.target_value * 100.0) as u32
                    } else {
                        0
                    };
                    format!("{} ({}% complete)", g.title, pct)
                })
                .collect();
            data_parts.push(format!("ACTIVE GOALS:\n{}", section.join("\n")));
            source_count += user_goals.len() as u32;
        }
    }

    if let Ok(convos) = &conversations {
        if !convos.is_empty() {
            let section: Vec<String> = convos.iter()
                .filter_map(|c| {
                    if c.structured.title.is_empty() { return None; }
                    Some(format!("{}: {}", c.structured.title, c.structured.overview))
                })
                .collect();
            if !section.is_empty() {
                data_parts.push(format!("RECENT CONVERSATIONS:\n{}", section.join("\n")));
                source_count += section.len() as u32;
            }
        }
    }

    if let Ok(msgs) = &messages {
        if !msgs.is_empty() {
            let section: Vec<String> = msgs.iter()
                .map(|m| {
                    let sender = &m.sender;
                    format!("[{}] {}", sender, m.text)
                })
                .collect();
            data_parts.push(format!("MESSAGES:\n{}", section.join("\n")));
            source_count += msgs.len() as u32;
        }
    }

    if data_parts.is_empty() {
        return Err((StatusCode::UNPROCESSABLE_ENTITY, "Insufficient data to generate profile".to_string()));
    }

    let user_data = data_parts.join("\n\n");
    let prompt = proactive_prompts::USER_PROFILE_GENERATE.replace("{user_data}", &fence("user_data", &user_data));

    let profile_text = client
        .call_with_schema(&prompt, Some(0.5), Some(2000), None)
        .await
        .map_err(|e| {
            tracing::error!("proactive: user profile generation failed: {}", e);
            (StatusCode::INTERNAL_SERVER_ERROR, format!("Profile generation failed: {}", e))
        })?;

    // Stage 2: Consolidate with history if provided
    let final_profile = if !request.previous_profiles.is_empty() {
        let history = request.previous_profiles.join("\n---\n");
        let consolidate_prompt = proactive_prompts::USER_PROFILE_CONSOLIDATE
            .replace("{new_profile}", &fence("new_profile", &profile_text))
            .replace("{history}", &fence("history", &history));

        check_rate_limit(&state, &user.uid).await?;

        client
            .call_with_schema(&consolidate_prompt, Some(0.5), Some(2000), None)
            .await
            .unwrap_or(profile_text)
    } else {
        profile_text
    };

    // Truncate to 10000 chars (safety limit matching Swift), char-boundary-safe
    let truncated = truncate_chars(&final_profile, 10000).to_string();

    Ok(Json(UserProfileResponse {
        profile_text: truncated,
        data_sources_used: source_count,
    }))
}

// ============================================================================
// POST /v1/proactive/tasks/prioritize
// ============================================================================

async fn prioritize_tasks(
    State(state): State<AppState>,
    user: AuthUser,
    Json(_request): Json<PrioritizeRequest>,
) -> Result<Json<PrioritizeResponse>, (StatusCode, String)> {
    check_rate_limit(&state, &user.uid).await?;
    let client = flash_client(&state.config)?;

    // Fetch staged tasks, user profile context, goals, and persona (matches Swift behavior)
    let (staged_result, goals_result, persona_result) = tokio::join!(
        state.firestore.get_staged_tasks(&user.uid, 10000, 0),
        state.firestore.get_user_goals(&user.uid, 50),
        state.firestore.get_user_persona(&user.uid),
    );

    let staged = staged_result.map_err(|e| {
        tracing::error!("proactive: failed to fetch staged tasks: {}", e);
        (StatusCode::INTERNAL_SERVER_ERROR, "Failed to fetch tasks".to_string())
    })?;

    if staged.len() < 2 {
        return Ok(Json(PrioritizeResponse {
            reranked_tasks: vec![],
            reasoning: "Fewer than 2 tasks — no re-ranking needed.".to_string(),
        }));
    }

    // Build task list string
    let task_list: String = staged.iter().enumerate()
        .map(|(i, t)| {
            let priority = t.priority.as_deref().unwrap_or("none");
            let due = t.due_at.as_ref()
                .map(|d| format!(" [due: {}]", d.format("%Y-%m-%d")))
                .unwrap_or_default();
            format!("{}. [id:{}] {} [{}]{}", i + 1, t.id, t.description, priority, due)
        })
        .collect::<Vec<_>>()
        .join("\n");

    // Build context (persona + goals, matching Swift TaskPrioritizationService)
    let mut context_parts: Vec<String> = Vec::new();
    if let Ok(Some(p)) = &persona_result {
        context_parts.push(format!("USER PROFILE:\n{}: {}", p.name, p.description.as_str()));
    }
    if let Ok(goals) = &goals_result {
        if !goals.is_empty() {
            let goals_str: Vec<String> = goals.iter()
                .map(|g| format!("- {} ({}/{})", g.title, g.current_value, g.target_value))
                .collect();
            context_parts.push(format!("ACTIVE GOALS:\n{}", goals_str.join("\n")));
        }
    }
    let context = if context_parts.is_empty() { "No additional context.".to_string() } else { context_parts.join("\n\n") };

    let prompt = proactive_prompts::TASK_PRIORITIZE
        .replace("{context}", &fence("context", &context))
        .replace("{task_list}", &fence("task_list", &task_list));

    let schema = serde_json::json!({
        "type": "object",
        "properties": {
            "reranked_tasks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string"},
                        "new_position": {"type": "integer"}
                    },
                    "required": ["task_id", "new_position"]
                }
            },
            "reasoning": {"type": "string"}
        },
        "required": ["reranked_tasks", "reasoning"]
    });

    let response = client
        .call_with_schema(&prompt, Some(0.5), Some(2000), Some(schema))
        .await
        .map_err(|e| {
            tracing::error!("proactive: task prioritization failed: {}", e);
            (StatusCode::INTERNAL_SERVER_ERROR, format!("Prioritization failed: {}", e))
        })?;

    let parsed: PrioritizeResponse = parse_json_repairing(&response, "task prioritization").map_err(|e| {
        tracing::error!("proactive: {}", e);
        (StatusCode::INTERNAL_SERVER_ERROR, "Failed to parse AI response".to_string())
    })?;

    // Validate task IDs — only keep IDs that exist in our input set
    let valid_ids: std::collections::HashSet<&str> = staged.iter().map(|t| t.id.as_str()).collect();
    let validated_tasks: Vec<RerankedTask> = parsed.reranked_tasks
        .into_iter()
        .filter(|t| valid_ids.contains(t.task_id.as_str()))
        .collect();

    Ok(Json(PrioritizeResponse {
        reranked_tasks: validated_tasks,
        reasoning: parsed.reasoning,
    }))
}

// ============================================================================
// POST /v1/proactive/tasks/deduplicate
// ============================================================================

async fn deduplicate_tasks(
    State(state): State<AppState>,
    user: AuthUser,
    Json(_request): Json<DeduplicateRequest>,
) -> Result<Json<DeduplicateResponse>, (StatusCode, String)> {
    check_rate_limit(&state, &user.uid).await?;
    let client = flash_client(&state.config)?;

    let staged = state.firestore.get_staged_tasks(&user.uid, 200, 0).await.map_err(|e| {
        tracing::error!("proactive: failed to fetch staged tasks for dedup: {}", e);
        (StatusCode::INTERNAL_SERVER_ERROR, "Failed to fetch tasks".to_string())
    })?;

    if staged.len() < 3 {
        return Ok(Json(DeduplicateResponse {
            has_duplicates: false,
            duplicate_groups: vec![],
        }));
    }

    // Build task list string
    let task_list: String = staged.iter()
        .map(|t| {
            let priority = t.priority.as_deref().unwrap_or("none");
            let source = t.source.as_deref().unwrap_or("unknown");
            let due = t.due_at.as_ref()
                .map(|d| format!("\nDue: {}", d.format("%Y-%m-%d")))
                .unwrap_or_default();
            let created = t.created_at.format("%Y-%m-%dT%H:%M:%S");
            format!("ID: {}\nDescription: {}{}\nPriority: {}\nSource: {}\nCreated: {}\n", t.id, t.description, due, priority, source, created)
        })
        .collect::<Vec<_>>()
        .join("\n");

    let prompt = proactive_prompts::TASK_DEDUPLICATE.replace("{task_list}", &fence("task_list", &task_list));

    let schema = serde_json::json!({
        "type": "object",
        "properties": {
            "has_duplicates": {"type": "boolean"},
            "duplicate_groups": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "keep_id": {"type": "string"},
                        "delete_ids": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "reason": {"type": "string"}
                    },
                    "required": ["keep_id", "delete_ids", "reason"]
                }
            }
        },
        "required": ["has_duplicates", "duplicate_groups"]
    });

    let response = client
        .call_with_schema(&prompt, Some(0.3), Some(2000), Some(schema))
        .await
        .map_err(|e| {
            tracing::error!("proactive: task deduplication failed: {}", e);
            (StatusCode::INTERNAL_SERVER_ERROR, format!("Deduplication failed: {}", e))
        })?;

    let parsed: DeduplicateResponse = parse_json_repairing(&response, "task deduplication").map_err(|e| {
        tracing::error!("proactive: {}", e);
        (StatusCode::INTERNAL_SERVER_ERROR, "Failed to parse AI response".to_string())
    })?;

    // Validate all IDs — only keep groups where all IDs exist in our input
    // and keep_id is not in delete_ids (prevent self-referential deletion)
    let valid_ids: std::collections::HashSet<&str> = staged.iter().map(|t| t.id.as_str()).collect();
    let validated_groups: Vec<DuplicateGroup> = parsed.duplicate_groups
        .into_iter()
        .filter(|g| {
            valid_ids.contains(g.keep_id.as_str())
                && g.delete_ids.iter().all(|id| valid_ids.contains(id.as_str()))
                && !g.delete_ids.contains(&g.keep_id)
        })
        .collect();

    Ok(Json(DeduplicateResponse {
        has_duplicates: !validated_groups.is_empty(),
        duplicate_groups: validated_groups,
    }))
}

// ============================================================================
// POST /v1/proactive/goals/generate
// ============================================================================

async fn generate_goal(
    State(state): State<AppState>,
    user: AuthUser,
    Json(_request): Json<GenerateGoalRequest>,
) -> Result<Json<GoalSuggestion>, (StatusCode, String)> {
    check_rate_limit(&state, &user.uid).await?;
    let client = flash_client(&state.config)?;

    // Fetch rich context
    let (memories, conversations, tasks, persona, goals, completed_goals) = tokio::join!(
        state.firestore.get_memories(&user.uid, 500),
        state.firestore.get_conversations(&user.uid, 100, 0, false, &[], None, None, None, None),
        state.firestore.get_action_items(&user.uid, 100, 0, Some(false), None, None, None, None, None, None, None),
        state.firestore.get_user_persona(&user.uid),
        state.firestore.get_user_goals(&user.uid, 50),
        state.firestore.get_completed_goals(&user.uid, 50),
    );

    let mut context_parts: Vec<String> = Vec::new();

    if let Ok(Some(p)) = &persona {
        context_parts.push(format!("USER PERSONA:\n{}: {}", p.name, p.description.as_str()));
    }

    if let Ok(mems) = &memories {
        if !mems.is_empty() {
            let mem_str: String = mems.iter().map(|m| m.content.as_str()).collect::<Vec<_>>().join("\n");
            context_parts.push(format!("MEMORIES:\n{}", mem_str));
        }
    }

    if let Ok(convos) = &conversations {
        if !convos.is_empty() {
            let convo_str: Vec<String> = convos.iter()
                .map(|c| c.structured.overview.clone())
                .collect();
            if !convo_str.is_empty() {
                context_parts.push(format!("CONVERSATIONS:\n{}", convo_str.join("\n")));
            }
        }
    }

    if let Ok(items) = &tasks {
        let incomplete: Vec<String> = items.iter()
            .filter(|t| !t.completed)
            .map(|t| format!("[{}] {}", t.id, t.description))
            .collect();
        if !incomplete.is_empty() {
            context_parts.push(format!("TASKS:\n{}", incomplete.join("\n")));
        }
    }

    if let Ok(active) = &goals {
        if !active.is_empty() {
            let goals_str: Vec<String> = active.iter()
                .map(|g| format!("- {} ({}/{})", g.title, g.current_value, g.target_value))
                .collect();
            context_parts.push(format!("ACTIVE GOALS:\n{}", goals_str.join("\n")));
        }
    }

    if let Ok(inactive) = &completed_goals {
        // Separate completed (has completed_at) from abandoned (no completed_at)
        let completed_str: Vec<String> = inactive.iter()
            .filter(|g| g.completed_at.is_some())
            .map(|g| format!("- {} (achieved {}/{})", g.title, g.current_value, g.target_value))
            .collect();
        let abandoned_str: Vec<String> = inactive.iter()
            .filter(|g| g.completed_at.is_none())
            .map(|g| format!("- {} (stopped at {}/{})", g.title, g.current_value, g.target_value))
            .collect();
        if !completed_str.is_empty() {
            context_parts.push(format!("COMPLETED GOALS:\n{}", completed_str.join("\n")));
        }
        if !abandoned_str.is_empty() {
            context_parts.push(format!("ABANDONED GOALS:\n{}", abandoned_str.join("\n")));
        }
    }

    if context_parts.is_empty() {
        return Err((StatusCode::UNPROCESSABLE_ENTITY, "Insufficient context to generate goal".to_string()));
    }

    let context = context_parts.join("\n\n");
    let prompt = proactive_prompts::GOAL_GENERATE.replace("{context}", &fence("context", &context));

    let schema = serde_json::json!({
        "type": "object",
        "properties": {
            "suggested_title": {"type": "string"},
            "suggested_description": {"type": "string"},
            "suggested_type": {"type": "string"},
            "suggested_target": {"type": "number"},
            "suggested_min": {"type": "number"},
            "suggested_max": {"type": "number"},
            "reasoning": {"type": "string"},
            "linked_task_ids": {
                "type": "array",
                "items": {"type": "string"}
            }
        },
        "required": ["suggested_title"]
    });

    let response = client
        .call_with_schema(&prompt, Some(0.7), Some(2000), Some(schema))
        .await
        .map_err(|e| {
            tracing::error!("proactive: goal generation failed: {}", e);
            (StatusCode::INTERNAL_SERVER_ERROR, format!("Goal generation failed: {}", e))
        })?;

    let mut suggestion: GoalSuggestion = parse_json_repairing(&response, "goal suggestion").map_err(|e| {
        tracing::error!("proactive: {}", e);
        (StatusCode::INTERNAL_SERVER_ERROR, "Failed to parse AI response".to_string())
    })?;

    // Validate linked task IDs against actual tasks
    if let Ok(items) = &tasks {
        let valid_ids: std::collections::HashSet<&str> = items.iter().map(|t| t.id.as_str()).collect();
        suggestion.linked_task_ids.retain(|id| valid_ids.contains(id.as_str()));
    } else {
        suggestion.linked_task_ids.clear();
    }

    Ok(Json(suggestion))
}

// ============================================================================
// POST /v1/proactive/goals/:id/advice
// ============================================================================

async fn get_goal_advice(
    State(state): State<AppState>,
    user: AuthUser,
    Path(goal_id): Path<String>,
    Json(_request): Json<GoalAdviceRequest>,
) -> Result<Json<GoalAdviceResponse>, (StatusCode, String)> {
    check_rate_limit(&state, &user.uid).await?;
    let client = flash_client(&state.config)?;

    // Fetch goal
    let goal = state.firestore.get_goal(&user.uid, &goal_id).await.map_err(|e| {
        tracing::error!("proactive: failed to fetch goal {}: {}", goal_id, e);
        (StatusCode::INTERNAL_SERVER_ERROR, "Failed to fetch goal".to_string())
    })?;

    let goal = goal.ok_or_else(|| (StatusCode::NOT_FOUND, "Goal not found".to_string()))?;

    // Fetch context
    let (memories, conversations) = tokio::join!(
        state.firestore.get_memories(&user.uid, 15),
        state.firestore.get_conversations(&user.uid, 10, 0, false, &[], None, None, None, None),
    );

    let mut context_parts: Vec<String> = Vec::new();
    if let Ok(mems) = &memories {
        let mem_str: String = mems.iter().map(|m| m.content.as_str()).collect::<Vec<_>>().join("\n");
        if !mem_str.is_empty() {
            context_parts.push(format!("MEMORIES:\n{}", mem_str));
        }
    }
    if let Ok(convos) = &conversations {
        let convo_str: Vec<String> = convos.iter()
            .map(|c| c.structured.overview.clone())
            .collect();
        if !convo_str.is_empty() {
            context_parts.push(format!("CONVERSATIONS:\n{}", convo_str.join("\n")));
        }
    }

    let progress_pct = if goal.target_value > 0.0 {
        (goal.current_value / goal.target_value * 100.0) as u32
    } else {
        0
    };

    let prompt = proactive_prompts::GOAL_ADVICE
        .replace("{goal_title}", &fence("goal_title", &goal.title))
        .replace("{current_value}", &goal.current_value.to_string())
        .replace("{target_value}", &goal.target_value.to_string())
        .replace("{progress_pct}", &progress_pct.to_string())
        .replace("{context}", &fence("context", &context_parts.join("\n\n")));

    let advice = client
        .call_with_schema(&prompt, Some(0.7), Some(500), None)
        .await
        .map_err(|e| {
            tracing::error!("proactive: goal advice failed: {}", e);
            (StatusCode::INTERNAL_SERVER_ERROR, format!("Goal advice failed: {}", e))
        })?;

    // Properly decode JSON string (Gemini returns JSON-encoded text when no schema given)
    let cleaned = serde_json::from_str::<String>(&advice)
        .unwrap_or_else(|_| advice.trim().trim_matches('"').to_string());

    Ok(Json(GoalAdviceResponse { advice: cleaned }))
}

// ============================================================================
// POST /v1/proactive/goals/:id/extract-progress
// ============================================================================

async fn extract_goal_progress(
    State(state): State<AppState>,
    user: AuthUser,
    Path(goal_id): Path<String>,
    Json(request): Json<ExtractProgressRequest>,
) -> Result<Json<ProgressExtraction>, (StatusCode, String)> {
    check_rate_limit(&state, &user.uid).await?;
    let client = flash_client(&state.config)?;

    // Fetch goal
    let goal = state.firestore.get_goal(&user.uid, &goal_id).await.map_err(|e| {
        tracing::error!("proactive: failed to fetch goal {}: {}", goal_id, e);
        (StatusCode::INTERNAL_SERVER_ERROR, "Failed to fetch goal".to_string())
    })?;

    let goal = goal.ok_or_else(|| (StatusCode::NOT_FOUND, "Goal not found".to_string()))?;

    let goal_type = format!("{:?}", goal.goal_type).to_lowercase();
    let prompt = proactive_prompts::GOAL_EXTRACT_PROGRESS
        .replace("{goal_title}", &fence("goal_title", &goal.title))
        .replace("{goal_type}", &goal_type)
        .replace("{current_value}", &goal.current_value.to_string())
        .replace("{target_value}", &goal.target_value.to_string())
        .replace("{text}", &fence("user_message", &request.text));

    let schema = serde_json::json!({
        "type": "object",
        "properties": {
            "found": {"type": "boolean"},
            "value": {"type": "number"},
            "reasoning": {"type": "string"}
        },
        "required": ["found"]
    });

    let response = client
        .call_with_schema(&prompt, Some(0.3), Some(200), Some(schema))
        .await
        .map_err(|e| {
            tracing::error!("proactive: progress extraction failed: {}", e);
            (StatusCode::INTERNAL_SERVER_ERROR, format!("Progress extraction failed: {}", e))
        })?;

    let extraction: ProgressExtraction = parse_json_repairing(&response, "progress extraction").map_err(|e| {
        tracing::error!("proactive: {}", e);
        (StatusCode::INTERNAL_SERVER_ERROR, "Failed to parse AI response".to_string())
    })?;

    Ok(Json(extraction))
}

// ============================================================================
// Router
// ============================================================================

pub fn proactive_routes() -> Router<AppState> {
    Router::new()
        .route("/v1/proactive/user-profile", post(generate_user_profile))
        .route("/v1/proactive/tasks/prioritize", post(prioritize_tasks))
        .route("/v1/proactive/tasks/deduplicate", post(deduplicate_tasks))
        .route("/v1/proactive/goals/generate", post(generate_goal))
        .route("/v1/proactive/goals/:id/advice", post(get_goal_advice))
        .route("/v1/proactive/goals/:id/extract-progress", post(extract_goal_progress))
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    // --- Prompt building ---

    #[test]
    fn user_profile_prompt_replaces_placeholder() {
        let prompt = proactive_prompts::USER_PROFILE_GENERATE.replace("{user_data}", "test data");
        assert!(prompt.contains("test data"));
        assert!(!prompt.contains("{user_data}"));
    }

    #[test]
    fn task_prioritize_prompt_replaces_placeholders() {
        let prompt = proactive_prompts::TASK_PRIORITIZE
            .replace("{context}", "goals here")
            .replace("{task_list}", "1. task one");
        assert!(prompt.contains("goals here"));
        assert!(prompt.contains("1. task one"));
        assert!(!prompt.contains("{context}"));
        assert!(!prompt.contains("{task_list}"));
    }

    #[test]
    fn task_dedup_prompt_replaces_placeholder() {
        let prompt = proactive_prompts::TASK_DEDUPLICATE.replace("{task_list}", "ID: abc\nDescription: test");
        assert!(prompt.contains("ID: abc"));
        assert!(!prompt.contains("{task_list}"));
    }

    #[test]
    fn goal_generate_prompt_replaces_placeholder() {
        let prompt = proactive_prompts::GOAL_GENERATE.replace("{context}", "user context");
        assert!(prompt.contains("user context"));
        assert!(!prompt.contains("{context}"));
    }

    #[test]
    fn goal_advice_prompt_replaces_all_placeholders() {
        let prompt = proactive_prompts::GOAL_ADVICE
            .replace("{goal_title}", "Read 50 books")
            .replace("{current_value}", "12")
            .replace("{target_value}", "50")
            .replace("{progress_pct}", "24")
            .replace("{context}", "memories here");
        assert!(prompt.contains("Read 50 books"));
        assert!(prompt.contains("12 / 50"));
        assert!(prompt.contains("24%"));
        assert!(!prompt.contains("{goal_title}"));
    }

    #[test]
    fn goal_extract_progress_prompt_replaces_all() {
        let prompt = proactive_prompts::GOAL_EXTRACT_PROGRESS
            .replace("{goal_title}", "Run a marathon")
            .replace("{goal_type}", "numeric")
            .replace("{current_value}", "15")
            .replace("{target_value}", "42")
            .replace("{text}", "I ran 20km today");
        assert!(prompt.contains("Run a marathon"));
        assert!(prompt.contains("numeric"));
        assert!(prompt.contains("I ran 20km today"));
        assert!(!prompt.contains("{text}"));
    }

    // --- Response parsing ---

    #[test]
    fn parse_prioritize_response() {
        let json = r#"{"reranked_tasks": [{"task_id": "abc", "new_position": 1}], "reasoning": "Moved urgent task up"}"#;
        let parsed: PrioritizeResponse = serde_json::from_str(json).unwrap();
        assert_eq!(parsed.reranked_tasks.len(), 1);
        assert_eq!(parsed.reranked_tasks[0].task_id, "abc");
        assert_eq!(parsed.reranked_tasks[0].new_position, 1);
        assert_eq!(parsed.reasoning, "Moved urgent task up");
    }

    #[test]
    fn parse_prioritize_empty() {
        let json = r#"{"reranked_tasks": [], "reasoning": "Ranking looks good"}"#;
        let parsed: PrioritizeResponse = serde_json::from_str(json).unwrap();
        assert!(parsed.reranked_tasks.is_empty());
    }

    #[test]
    fn parse_dedup_response() {
        let json = r#"{"has_duplicates": true, "duplicate_groups": [{"keep_id": "a", "delete_ids": ["b", "c"], "reason": "Same task"}]}"#;
        let parsed: DeduplicateResponse = serde_json::from_str(json).unwrap();
        assert!(parsed.has_duplicates);
        assert_eq!(parsed.duplicate_groups.len(), 1);
        assert_eq!(parsed.duplicate_groups[0].delete_ids, vec!["b", "c"]);
    }

    #[test]
    fn parse_dedup_no_duplicates() {
        let json = r#"{"has_duplicates": false, "duplicate_groups": []}"#;
        let parsed: DeduplicateResponse = serde_json::from_str(json).unwrap();
        assert!(!parsed.has_duplicates);
        assert!(parsed.duplicate_groups.is_empty());
    }

    #[test]
    fn parse_goal_suggestion() {
        let json = r#"{"suggested_title": "Read 50 books", "suggested_type": "numeric", "suggested_target": 50, "linked_task_ids": ["t1", "t2"]}"#;
        let parsed: GoalSuggestion = serde_json::from_str(json).unwrap();
        assert_eq!(parsed.suggested_title, "Read 50 books");
        assert_eq!(parsed.suggested_target, Some(50.0));
        assert_eq!(parsed.linked_task_ids, vec!["t1", "t2"]);
    }

    #[test]
    fn parse_goal_suggestion_minimal() {
        let json = r#"{"suggested_title": "Exercise more"}"#;
        let parsed: GoalSuggestion = serde_json::from_str(json).unwrap();
        assert_eq!(parsed.suggested_title, "Exercise more");
        assert!(parsed.linked_task_ids.is_empty());
        assert!(parsed.suggested_target.is_none());
    }

    #[test]
    fn parse_progress_extraction_found() {
        let json = r#"{"found": true, "value": 25, "reasoning": "User mentioned reading 25 books"}"#;
        let parsed: ProgressExtraction = serde_json::from_str(json).unwrap();
        assert!(parsed.found);
        assert_eq!(parsed.value, Some(25.0));
    }

    #[test]
    fn parse_progress_extraction_not_found() {
        let json = r#"{"found": false}"#;
        let parsed: ProgressExtraction = serde_json::from_str(json).unwrap();
        assert!(!parsed.found);
        assert!(parsed.value.is_none());
    }

    #[test]
    fn parse_user_profile_response() {
        let json = r#"{"profile_text": "- Software engineer\n- Works at Omi", "data_sources_used": 42}"#;
        let parsed: UserProfileResponse = serde_json::from_str(json).unwrap();
        assert!(parsed.profile_text.contains("Software engineer"));
        assert_eq!(parsed.data_sources_used, 42);
    }

    // --- ID validation ---

    #[test]
    fn filter_invalid_task_ids() {
        let valid_ids: std::collections::HashSet<&str> = ["a", "b", "c"].iter().copied().collect();
        let tasks = vec![
            RerankedTask { task_id: "a".to_string(), new_position: 1 },
            RerankedTask { task_id: "x".to_string(), new_position: 2 }, // invalid
            RerankedTask { task_id: "b".to_string(), new_position: 3 },
        ];
        let filtered: Vec<RerankedTask> = tasks
            .into_iter()
            .filter(|t| valid_ids.contains(t.task_id.as_str()))
            .collect();
        assert_eq!(filtered.len(), 2);
        assert_eq!(filtered[0].task_id, "a");
        assert_eq!(filtered[1].task_id, "b");
    }

    #[test]
    fn filter_invalid_dedup_groups() {
        let valid_ids: std::collections::HashSet<&str> = ["a", "b", "c"].iter().copied().collect();
        let groups = vec![
            DuplicateGroup { keep_id: "a".to_string(), delete_ids: vec!["b".to_string()], reason: "ok".to_string() },
            DuplicateGroup { keep_id: "a".to_string(), delete_ids: vec!["x".to_string()], reason: "bad".to_string() }, // invalid delete_id
            DuplicateGroup { keep_id: "z".to_string(), delete_ids: vec!["a".to_string()], reason: "bad".to_string() }, // invalid keep_id
        ];
        let filtered: Vec<DuplicateGroup> = groups
            .into_iter()
            .filter(|g| valid_ids.contains(g.keep_id.as_str()) && g.delete_ids.iter().all(|id| valid_ids.contains(id.as_str())))
            .collect();
        assert_eq!(filtered.len(), 1);
        assert_eq!(filtered[0].keep_id, "a");
    }

    #[test]
    fn reject_self_referential_dedup_group() {
        let valid_ids: std::collections::HashSet<&str> = ["a", "b", "c"].iter().copied().collect();
        let groups = vec![
            DuplicateGroup { keep_id: "a".to_string(), delete_ids: vec!["a".to_string()], reason: "self-ref".to_string() },
            DuplicateGroup { keep_id: "b".to_string(), delete_ids: vec!["a".to_string(), "b".to_string()], reason: "mixed self-ref".to_string() },
            DuplicateGroup { keep_id: "a".to_string(), delete_ids: vec!["b".to_string()], reason: "ok".to_string() },
        ];
        let filtered: Vec<DuplicateGroup> = groups
            .into_iter()
            .filter(|g| {
                valid_ids.contains(g.keep_id.as_str())
                    && g.delete_ids.iter().all(|id| valid_ids.contains(id.as_str()))
                    && !g.delete_ids.contains(&g.keep_id)
            })
            .collect();
        assert_eq!(filtered.len(), 1);
        assert_eq!(filtered[0].reason, "ok");
    }

    // --- Fencing ---

    #[test]
    fn fence_wraps_data_with_xml_tags() {
        let fenced = fence("user_data", "some content\nwith lines");
        assert_eq!(fenced, "<user_data>\nsome content\nwith lines\n</user_data>");
    }

    #[test]
    fn fence_handles_empty_content() {
        let fenced = fence("tag", "");
        assert_eq!(fenced, "<tag>\n\n</tag>");
    }

    // --- Truncation safety ---

    #[test]
    fn truncate_chars_ascii() {
        let s = "hello world";
        assert_eq!(truncate_chars(s, 5), "hello");
        assert_eq!(truncate_chars(s, 100), "hello world");
    }

    #[test]
    fn truncate_chars_multibyte_no_panic() {
        // U+00E9 (é) is 2 bytes in UTF-8
        let s = "caf\u{00e9} latte";
        // "café" = 5 bytes (c=1, a=1, f=1, é=2). Truncating at byte 4 is mid-char.
        let result = truncate_chars(s, 4);
        assert_eq!(result, "caf"); // should back up to byte 3
        assert!(result.is_char_boundary(result.len()));
    }

    #[test]
    fn truncate_chars_emoji_no_panic() {
        // U+1F600 (😀) is 4 bytes
        let s = "hi\u{1F600}there";
        // "hi" = 2 bytes, emoji = 4 bytes (starts at 2, ends at 6)
        let result = truncate_chars(s, 3); // mid-emoji
        assert_eq!(result, "hi");
    }

    // --- JSON repair ---

    #[test]
    fn parse_json_repair_truncated_object() {
        let truncated = r#"{"reranked_tasks": [{"task_id": "a", "new_position": 1}], "reasoning": "test"#;
        let parsed: PrioritizeResponse = parse_json_repairing(truncated, "test").unwrap();
        assert_eq!(parsed.reranked_tasks.len(), 1);
        assert_eq!(parsed.reasoning, "test");
    }

    #[test]
    fn parse_json_repair_valid_passes_through() {
        let valid = r#"{"found": true, "value": 10.0}"#;
        let parsed: ProgressExtraction = parse_json_repairing(valid, "test").unwrap();
        assert!(parsed.found);
        assert_eq!(parsed.value, Some(10.0));
    }

    #[test]
    fn parse_json_repair_returns_error_on_garbage() {
        let garbage = "this is not json at all";
        let result: Result<ProgressExtraction, _> = parse_json_repairing(garbage, "test");
        assert!(result.is_err());
    }

    // --- JSON string decoding for advice ---

    #[test]
    fn advice_json_string_decoding() {
        let json_string = r#""Focus on reading 30 minutes before bed each night.""#;
        let decoded = serde_json::from_str::<String>(json_string)
            .unwrap_or_else(|_| json_string.trim().trim_matches('"').to_string());
        assert_eq!(decoded, "Focus on reading 30 minutes before bed each night.");
    }

    #[test]
    fn advice_plain_text_fallback() {
        let plain = "Focus on reading more";
        let decoded = serde_json::from_str::<String>(plain)
            .unwrap_or_else(|_| plain.trim().trim_matches('"').to_string());
        assert_eq!(decoded, "Focus on reading more");
    }

    // --- Boundary tests ---

    #[test]
    fn truncate_at_exact_profile_limit() {
        let s: String = "a".repeat(10000);
        assert_eq!(truncate_chars(&s, 10000).len(), 10000);

        let over: String = "a".repeat(10001);
        assert_eq!(truncate_chars(&over, 10000).len(), 10000);

        let under: String = "a".repeat(9999);
        assert_eq!(truncate_chars(&under, 10000).len(), 9999);
    }

    #[test]
    fn truncate_multibyte_at_profile_limit() {
        // Build a string with multi-byte chars that crosses the 10000-byte boundary
        let base: String = "a".repeat(9999) + "\u{00e9}"; // 10001 bytes
        let result = truncate_chars(&base, 10000);
        assert_eq!(result.len(), 9999); // backed up past the 2-byte char
        assert!(result.is_char_boundary(result.len()));
    }

    // --- Consolidation prompt ---

    #[test]
    fn consolidation_prompt_replaces_both_placeholders() {
        let prompt = proactive_prompts::USER_PROFILE_CONSOLIDATE
            .replace("{new_profile}", &fence("new_profile", "new data"))
            .replace("{history}", &fence("history", "old data"));
        assert!(prompt.contains("<new_profile>"));
        assert!(prompt.contains("new data"));
        assert!(prompt.contains("<history>"));
        assert!(prompt.contains("old data"));
        assert!(!prompt.contains("{new_profile}"));
        assert!(!prompt.contains("{history}"));
    }

    // --- Fencing in prompt assembly ---

    #[test]
    fn fenced_user_profile_prompt_has_xml_tags() {
        let user_data = "MEMORIES:\nsome content";
        let prompt = proactive_prompts::USER_PROFILE_GENERATE
            .replace("{user_data}", &fence("user_data", user_data));
        assert!(prompt.contains("<user_data>"));
        assert!(prompt.contains("</user_data>"));
        assert!(prompt.contains("some content"));
    }

    #[test]
    fn fenced_goal_extract_prompt_wraps_user_text() {
        let prompt = proactive_prompts::GOAL_EXTRACT_PROGRESS
            .replace("{goal_title}", &fence("goal_title", "Run marathon"))
            .replace("{goal_type}", "numeric")
            .replace("{current_value}", "15")
            .replace("{target_value}", "42")
            .replace("{text}", &fence("user_message", "I ran 20km today"));
        assert!(prompt.contains("<user_message>"));
        assert!(prompt.contains("I ran 20km today"));
        assert!(prompt.contains("</user_message>"));
        assert!(prompt.contains("<goal_title>"));
    }

    // --- JSON repair edge cases ---

    #[test]
    fn parse_json_repair_truncated_array() {
        let truncated = r#"{"has_duplicates": true, "duplicate_groups": [{"keep_id": "a", "delete_ids": ["b"], "reason": "same"#;
        let parsed: DeduplicateResponse = parse_json_repairing(truncated, "test").unwrap();
        assert!(parsed.has_duplicates);
        assert_eq!(parsed.duplicate_groups.len(), 1);
    }

    #[test]
    fn parse_json_repair_truncated_inside_string() {
        // Truncated mid-string value
        let truncated = r#"{"found": true, "reasoning": "The user mentioned rea"#;
        let parsed: ProgressExtraction = parse_json_repairing(truncated, "test").unwrap();
        assert!(parsed.found);
        assert!(parsed.reasoning.unwrap().starts_with("The user"));
    }

    // --- Empty/minimal input ---

    #[test]
    fn parse_empty_progress_text() {
        // Empty text is valid — model should return found=false
        let json = r#"{"found": false, "reasoning": "No progress mentioned"}"#;
        let parsed: ProgressExtraction = parse_json_repairing(json, "test").unwrap();
        assert!(!parsed.found);
    }
}
