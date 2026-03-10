// LLM Usage routes - record per-query token usage in Firestore

use axum::{extract::State, http::StatusCode, routing::{get, post}, Json, Router};

use crate::auth::AuthUser;
use crate::models::{RecordLlmUsageRequest, RecordLlmUsageResponse};
use crate::models::llm_usage::GetTotalLlmCostResponse;
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
            &req.account,
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

async fn get_total_llm_cost(
    State(state): State<AppState>,
    user: AuthUser,
) -> Result<Json<GetTotalLlmCostResponse>, StatusCode> {
    match state.firestore.get_total_llm_cost(&user.uid).await {
        Ok(total) => {
            tracing::info!("LLM total cost for {}: ${:.4}", user.uid, total);
            Ok(Json(GetTotalLlmCostResponse { total_cost_usd: total }))
        }
        Err(e) => {
            tracing::error!("LLM total cost fetch failed for {}: {}", user.uid, e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

pub fn llm_usage_routes() -> Router<AppState> {
    Router::new()
        .route("/v1/users/me/llm-usage", post(record_llm_usage))
        .route("/v1/users/me/llm-usage/total", get(get_total_llm_cost))
}
