use serde::{Deserialize, Serialize};

/// A single transcription segment with speaker and timing info
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TranscriptSegment {
    pub id: Option<String>,
    pub speaker: i32,
    pub text: String,
    pub start: f64,
    pub end: f64,
    pub is_final: bool,
}

/// Translation of a segment into another language
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SegmentTranslation {
    pub lang: String,
    pub text: String,
}
