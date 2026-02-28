use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Deserialize)]
pub struct RecordLlmUsageRequest {
    pub input_tokens: i64,
    pub output_tokens: i64,
    pub cache_read_tokens: i64,
    pub cache_write_tokens: i64,
    pub total_tokens: i64,
    pub cost_usd: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct RecordLlmUsageResponse {
    pub status: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct GetTotalLlmCostResponse {
    pub total_cost_usd: f64,
}
