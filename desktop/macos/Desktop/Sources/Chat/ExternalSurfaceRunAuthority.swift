import Foundation

enum ExternalSurfaceRunMode: String, Sendable {
  case ask
  case act
}

enum ExternalSurfaceRunTerminalStatus: String, Sendable {
  case completed
  case failed
  case cancelled
}

struct ExternalSurfaceRunBinding: Sendable, Equatable {
  let ownerID: String
  let sessionID: String
  let turnID: String
  let runID: String
  let attemptID: String
  let duplicate: Bool
}

struct ExternalSurfaceRunCompletion: Sendable, Equatable {
  let runID: String
  let attemptID: String
  let terminalStatus: ExternalSurfaceRunTerminalStatus
  let duplicate: Bool
}

struct ExternalSurfaceAuthorityError: LocalizedError, Sendable, Equatable {
  let code: String

  var errorDescription: String? {
    "The desktop kernel rejected the external surface operation (\(code))."
  }

  static func from(_ payload: [String: Any], fallback: String) -> Self {
    let error = payload["error"] as? [String: Any]
    let code = (error?["code"] as? String)?
      .trimmingCharacters(in: .whitespacesAndNewlines)
    return Self(code: code.flatMap { $0.isEmpty ? nil : $0 } ?? fallback)
  }
}
