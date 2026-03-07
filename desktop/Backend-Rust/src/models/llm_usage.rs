use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Deserialize)]
pub struct RecordLlmUsageRequest {
    pub input_tokens: i64,
    pub output_tokens: i64,
    pub cache_read_tokens: i64,
    pub cache_write_tokens: i64,
    pub total_tokens: i64,
    pub cost_usd: f64,
    #[serde(default = "default_account")]
    pub account: String,
}

fn default_account() -> String {
    "omi".to_string()
}

#[derive(Debug, Clone, Serialize)]
pub struct RecordLlmUsageResponse {
    pub status: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct GetTotalLlmCostResponse {
    pub total_cost_usd: f64,
}
