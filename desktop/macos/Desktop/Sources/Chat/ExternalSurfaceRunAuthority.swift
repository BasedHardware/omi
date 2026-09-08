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

/// The single definition of a non-blank external answer.
///
/// The wire guard and the receipt validator disagreed about this: the wire used
/// `!isEmpty` while the kernel trimmed, so a whitespace-only answer was sent,
/// trimmed away kernel-side, reported as not persisted, and then thrown on by a
/// validator that only checked `!= nil`. A run that had terminalized cleanly failed.
/// It lives here, beside the binding and completion types both sides already use,
/// rather than inside either caller.
enum ExternalSurfaceRunAnswer {
  static func normalized(_ text: String?) -> String? {
    guard let text else { return nil }
    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    return trimmed.isEmpty ? nil : trimmed
  }
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
  let finalTextPersisted: Bool
  let journalMaterialized: Bool
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
