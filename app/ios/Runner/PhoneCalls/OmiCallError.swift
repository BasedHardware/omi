import Foundation

/// Structured error type for phone call failures.
/// Serializable to Flutter EventChannel for rich error reporting to Dart.
enum OmiCallError: LocalizedError {
    case micPermissionDenied
    case tokenGenerationFailed
    case callkitRejected(String)
    case twilioError(code: Int, message: String)
    case audioSessionFailed(String)
    case unknown(String)

    var code: String {
        switch self {
        case .micPermissionDenied: return "MIC_PERMISSION_DENIED"
        case .tokenGenerationFailed: return "TOKEN_GENERATION_FAILED"
        case .callkitRejected: return "CALLKIT_REJECTED"
        case .twilioError: return "TWILIO_ERROR"
        case .audioSessionFailed: return "AUDIO_SESSION_FAILED"
        case .unknown: return "UNKNOWN"
        }
    }

    var message: String {
        switch self {
        case .micPermissionDenied:
            return "Microphone permission is required to make calls"
        case .tokenGenerationFailed:
            return "Unable to authenticate. Please try again."
        case .callkitRejected(let detail):
            return "Call system rejected the request: \(detail)"
        case .twilioError(_, let message):
            return "Call service error: \(message)"
        case .audioSessionFailed(let detail):
            return "Audio configuration failed: \(detail)"
        case .unknown(let detail):
            return detail
        }
    }

    var errorDescription: String? { message }

    /// Serialize for Flutter EventChannel transport.
    func toEventData() -> [String: Any] {
        return [
            "type": "error",
            "code": code,
            "message": message,
        ]
    }
}
