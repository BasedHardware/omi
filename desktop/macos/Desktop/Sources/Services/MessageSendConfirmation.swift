import Foundation

/// What the Messages history shows for a message Omi just sent.
enum MessageSendOutcomeStatus: String, Sendable {
  /// The outgoing row is marked delivered.
  case delivered
  /// The row is recorded as sent but was not marked delivered within the window.
  case sent
  /// Messages recorded an error on the row.
  case notDelivered = "not_delivered"
  /// No evidence either way: no matching row, an ambiguous match, or the
  /// history could not be read. Never a failure.
  case unconfirmed
}

struct MessageSendConfirmation: Sendable, Equatable {
  let status: MessageSendOutcomeStatus
  /// Why the outcome is unconfirmed; nil for the other three.
  let unconfirmedReason: UnconfirmedReason?
  /// History reads made after the send.
  let checks: Int
  let waitedMilliseconds: Int

  enum UnconfirmedReason: String, Sendable {
    /// No new outgoing row with this text appeared in the chat.
    case noMatchingRow = "no_matching_row"
    /// A matching row appeared but Messages had not marked it sent.
    case notYetSent = "not_yet_sent"
    /// More than one new matching row, and they disagree.
    case ambiguous
    /// The history could not be read (for example, no Full Disk Access).
    case historyUnreadable = "history_unreadable"
    /// The tool call was stopped while checking.
    case checkStopped = "check_stopped"
  }
}

/// Sends a message once and then confirms it from the Messages history.
///
/// The send itself is never repeated: every path below calls `send` exactly
/// once or not at all, whatever the history shows. Messages writes the
/// outgoing row when it accepts the send, flips `is_sent` once the service
/// takes it (usually within a second for iMessage) and `is_delivered` when the
/// recipient's device acknowledges it, typically a second or two later when
/// that device is online. A short poll catches the common case without
/// holding the turn for a recipient who is offline.
enum MessageSendConfirmer {
  /// Rows dated this long before the send started still count. Messages dates
  /// the row from its own clock, and an iMessage row can be re-dated from the
  /// server's; the before-and-after comparison is what keeps an older
  /// identical message from counting.
  static let clockTolerance: TimeInterval = 3
  /// How long to keep reading after the send returns.
  static let window: TimeInterval = 5
  static let pollInterval: TimeInterval = 0.5

  typealias Lookup =
    @Sendable (_ handle: String, _ text: String, _ createdSince: Date) async throws -> [OutgoingMessageState]
  typealias Sleeper = @Sendable (TimeInterval) async throws -> Void

  static let liveLookup: Lookup = { handle, text, since in
    try await MessagesReaderService.shared.outgoingMessageStates(sentTo: handle, text: text, createdSince: since)
  }

  static func sendThenConfirm<Sent: Sendable>(
    handle: String,
    text: String,
    lookup: Lookup = liveLookup,
    now: @Sendable () -> Date = { Date() },
    sleep: Sleeper = { try await Task.sleep(nanoseconds: UInt64($0 * 1_000_000_000)) },
    send: @Sendable () async throws -> Sent
  ) async throws -> (sent: Sent, confirmation: MessageSendConfirmation) {
    let createdSince = now().addingTimeInterval(-clockTolerance)

    // Matching rows that already exist cannot be this send. Without this
    // baseline there is no way to tell a new row from an old identical one, so
    // an unreadable history before the send leaves the outcome unconfirmed.
    let baseline = try? await lookup(handle, text, createdSince).map(\.rowID)

    let sent = try await send()

    let checkStarted = now()
    func finish(_ status: MessageSendOutcomeStatus, _ reason: MessageSendConfirmation.UnconfirmedReason?, checks: Int)
      -> (sent: Sent, confirmation: MessageSendConfirmation)
    {
      let waited = max(0, now().timeIntervalSince(checkStarted))
      return (
        sent,
        MessageSendConfirmation(
          status: status, unconfirmedReason: reason, checks: checks,
          waitedMilliseconds: Int((waited * 1000).rounded()))
      )
    }

    guard let baseline else { return finish(.unconfirmed, .historyUnreadable, checks: 0) }
    let existing = Set(baseline)
    let deadline = checkStarted.addingTimeInterval(window)
    var checks = 0
    var verdict = Verdict.noRow

    while true {
      if Task.isCancelled { return finish(.unconfirmed, .checkStopped, checks: checks) }
      let rows: [OutgoingMessageState]
      do {
        rows = try await lookup(handle, text, createdSince)
      } catch {
        return finish(.unconfirmed, .historyUnreadable, checks: checks + 1)
      }
      checks += 1
      verdict = Verdict(rows.filter { !existing.contains($0.rowID) })
      switch verdict {
      case .delivered: return finish(.delivered, nil, checks: checks)
      case .notDelivered: return finish(.notDelivered, nil, checks: checks)
      case .sent, .notYetSent, .ambiguous, .noRow: break
      }
      if now() >= deadline { break }
      do {
        try await sleep(pollInterval)
      } catch {
        return finish(.unconfirmed, .checkStopped, checks: checks)
      }
    }

    switch verdict {
    case .sent: return finish(.sent, nil, checks: checks)
    case .notYetSent: return finish(.unconfirmed, .notYetSent, checks: checks)
    case .ambiguous: return finish(.unconfirmed, .ambiguous, checks: checks)
    case .noRow, .delivered, .notDelivered: return finish(.unconfirmed, .noMatchingRow, checks: checks)
    }
  }

  /// The weakest claim every new matching row supports. One row is the usual
  /// case; several mean an identical message went to the same person in the
  /// same moment, and Omi cannot tell which one is its own.
  private enum Verdict {
    case noRow, notYetSent, sent, delivered, notDelivered, ambiguous

    init(_ rows: [OutgoingMessageState]) {
      if rows.isEmpty {
        self = .noRow
      } else if rows.allSatisfy({ $0.errorCode != 0 }) {
        self = .notDelivered
      } else if rows.contains(where: { $0.errorCode != 0 }) {
        self = .ambiguous
      } else if rows.allSatisfy(\.isDelivered) {
        self = .delivered
      } else if rows.allSatisfy({ $0.isSent || $0.isDelivered }) {
        self = .sent
      } else {
        self = .notYetSent
      }
    }
  }
}
