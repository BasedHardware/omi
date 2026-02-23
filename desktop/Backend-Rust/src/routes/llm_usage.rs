// LLM Usage routes - record per-query token usage in Firestore

use axum::{extract::State, http::StatusCode, routing::post, Json, Router};

use crate::auth::AuthUser;
use crate::models::{RecordLlmUsageRequest, RecordLlmUsageResponse};
use crate::AppState;

async fn record_llm_usage(
    State(state): State<AppState>,
    user: AuthUser,
    Json(req): Json<RecordLlmUsageRequest>,
) -> Result<Json<RecordLlmUsageResponse>, StatusCode> {
    match state
        .firestore
        .record_llm_usage(
            &user.uid,
            req.input_tokens,
            req.output_tokens,
            req.cache_read_tokens,
            req.cache_write_tokens,
            req.total_tokens,
            req.cost_usd,
        )
        .await
    {
        Ok(()) => Ok(Json(RecordLlmUsageResponse {
            status: "ok".to_string(),
        })),
        Err(e) => {
            tracing::error!("LLM usage write failed for {}: {}", user.uid, e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

pub fn llm_usage_routes() -> Router<AppState> {
    Router::new().route("/v1/users/me/llm-usage", post(record_llm_usage))
}
