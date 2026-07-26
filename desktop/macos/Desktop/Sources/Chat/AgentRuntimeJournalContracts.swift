import Foundation

/// Sendable carrier for `[String: Any]` JSON payloads that must cross actor or
/// isolation boundaries. The dictionary is parsed once and treated as immutable
/// thereafter, so unchecked Sendable conformance is safe.
struct RuntimeJSONPayloadBox: @unchecked Sendable {
  let value: [String: Any]
  init(_ value: [String: Any]) { self.value = value }
}

/// Journal writes use SQLite `BEGIN IMMEDIATE`, whose configured busy window is
/// five seconds. Keep the client deadline strictly beyond that database window
/// so a successful commit still has time to traverse the JSONL IPC boundary.
struct AgentRuntimeJournalTimeoutPolicy {
  static let sqliteBusyWindowNanoseconds: UInt64 = 5_000_000_000
  static let ipcSlackNanoseconds: UInt64 = 5_000_000_000
  static let deadlineNanoseconds = sqliteBusyWindowNanoseconds + ipcSlackNanoseconds

  static func allowsCorrelatedResult(elapsedNanoseconds: UInt64) -> Bool {
    elapsedNanoseconds < deadlineNanoseconds
  }
}
