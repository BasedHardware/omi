import Foundation

// MARK: - AutoRouter task types
//
// Maps to the 5 task types supported by the backend `/v1/auto-router/pick` endpoint
// (see `backend/utils/auto_router/task_registry.py`). Each case's `rawValue`
// is the snake_case task name sent as the `task` query parameter.

enum AutoRouterTask: String, CaseIterable, Codable, Sendable {
    /// Real-time voice responses via the realtime hub. Latency-critical.
    case pttResponse = "ptt_response"
    /// Vision-language analysis of screen captures. Quality-critical.
    case screenshotUnderstanding = "screenshot_understanding"
    /// Embedding pipeline for screen captures and retrieval. Cost-critical.
    case screenshotEmbedding = "screenshot_embedding"
    /// General chat assistant replies. Balanced quality/latency/cost.
    case generalAssistant = "general_assistant"
    /// Speech-to-text transcription (STT). Latency-critical.
    case transcription = "transcription"

    /// Human-readable label for logs and UI.
    var displayName: String {
        switch self {
        case .pttResponse: return "Push-to-talk response"
        case .screenshotUnderstanding: return "Screenshot understanding"
        case .screenshotEmbedding: return "Screenshot embedding"
        case .generalAssistant: return "General assistant"
        case .transcription: return "Transcription"
        }
    }
}
