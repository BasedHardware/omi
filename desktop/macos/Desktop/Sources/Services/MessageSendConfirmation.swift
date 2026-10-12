import Foundation

/// What the Messages history shows for a message Omi just sent.
enum MessageSendOutcomeStatus: String, Sendable {
  /// The outgoing row is marked delivered.
  case delivered
  /// The row is recorded as sent but was not marked delivered within the window.
  case sent
  /// Every new matching row carries an error.
  case notDelivered = "not_delivered"
  /// No evidence either way: no matching row, an ambiguous match, or the
  /// history could not be read. An unknown outcome, never a failure.
  case unconfirmed
}

struct MessageSendConfirmation: Sendable, Equatable {
  let status: MessageSendOutcomeStatus
  /// Why the outcome is unconfirmed; nil for the other three.
  let unconfirmedReason: UnconfirmedReason?
  /// Messages recorded an error on one attempt before another attempt (such
  /// as the text-message fallback) went through.
  let succeededAfterError: Bool
  /// History reads made after the send.
  let checks: Int
  let waitedMilliseconds: Int

  enum UnconfirmedReason: String, Sendable {
    /// No new outgoing row with this text appeared in the chat.
    case noMatchingRow = "no_matching_row"
    /// A matching row appeared but Messages had not marked it sent.
    case notYetSent = "not_yet_sent"
    /// More than one new matching row without an error, so Omi cannot tell
    /// which one is its own.
    case ambiguous
    /// The history could not be read (for example, no Full Disk Access).
    case historyUnreadable = "history_unreadable"
    /// The tool call was stopped while checking.
    case checkStopped = "check_stopped"
  }
}

/// The two reads the send check makes, so tests can point them at a fixture.
struct MessageSendHistory: Sendable {
  /// The newest message row id before the send.
  let latestRowID: @Sendable () async throws -> Int64
  /// Matching outgoing rows newer than the baseline row id.
  let outgoingStates:
    @Sendable (_ handle: String, _ text: String, _ createdSince: Date, _ afterRowID: Int64) async throws ->
      [OutgoingMessageState]

  /// The real Messages store, matching handles for this Mac's region.
  static var live: MessageSendHistory { store(nil) }

  static func store(_ url: URL?, callingCode: String? = MessagingHandle.currentCallingCode()) -> MessageSendHistory {
    MessageSendHistory(
      latestRowID: { try await MessagesReaderService.shared.latestMessageRowID(storeOverride: url) },
      outgoingStates: { handle, text, since, afterRowID in
        try await MessagesReaderService.shared.outgoingMessageStates(
          sentTo: handle, text: text, createdSince: since, afterRowID: afterRowID, callingCode: callingCode,
          storeOverride: url)
      })
  }
}

/// Sends a message once and then confirms it from the Messages history.
///
/// The send itself is never repeated: every path below calls `send` exactly
/// once or not at all, whatever the history shows. Before sending, the check
/// records the newest message row id; afterwards only rows Messages wrote past
/// it count, so no message that existed before the send can confirm it.
///
/// Messages writes the outgoing row when it accepts the send, flips `is_sent`
/// once the service takes it (usually within a second for iMessage) and
/// `is_delivered` when the recipient's device acknowledges it, typically a
/// second or two later when that device is online. A failed iMessage attempt
/// can be followed by a text-message attempt, and a second identical row would
/// make the match ambiguous, so the check reads for the whole window and
/// decides over every new row at the end.
enum MessageSendConfirmer {
  /// Rows dated more than this before the send started never count. The row id
  /// baseline already excludes every row that existed; this only keeps an old
  /// message that syncs in from another device during the window from counting.
  /// Messages dates the row from this Mac's clock after the send starts, so a
  /// second covers rounding and small clock adjustments.
  static let clockTolerance: TimeInterval = 1
  /// How long to keep reading after the send returns.
  static let window: TimeInterval = 5
  static let pollInterval: TimeInterval = 0.5

  typealias Sleeper = @Sendable (TimeInterval) async throws -> Void

  static func sendThenConfirm<Sent: Sendable>(
    handle: String,
    text: String,
    history: MessageSendHistory = .live,
    now: @Sendable () -> Date = { Date() },
    sleep: Sleeper = { try await Task.sleep(nanoseconds: UInt64($0 * 1_000_000_000)) },
    send: @Sendable () async throws -> Sent
  ) async throws -> (sent: Sent, confirmation: MessageSendConfirmation) {
    let createdSince = now().addingTimeInterval(-clockTolerance)

    // Without a baseline there is no way to tell a new row from an old one, so
    // an unreadable history before the send leaves the outcome unconfirmed.
    let baseline = try? await history.latestRowID()

    // A stop that arrives before Messages is asked to send means nothing is sent.
    try Task.checkCancellation()
    let sent = try await send()

    let checkStarted = now()
    var checks = 0
    func finish(_ verdict: Verdict?, stopped: Bool = false) -> (sent: Sent, confirmation: MessageSendConfirmation) {
      let waited = max(0, now().timeIntervalSince(checkStarted))
      let outcome = stopped ? Outcome(.unconfirmed, .checkStopped) : Outcome(verdict)
      return (
        sent,
        MessageSendConfirmation(
          status: outcome.status, unconfirmedReason: outcome.reason, succeededAfterError: outcome.afterError,
          checks: checks, waitedMilliseconds: Int((waited * 1000).rounded()))
      )
    }

    guard let baseline else { return finish(nil) }
    let deadline = checkStarted.addingTimeInterval(window)
    var latest: Verdict?

    while true {
      if Task.isCancelled { return finish(latest, stopped: true) }
      checks += 1
      do {
        latest = Verdict(try await history.outgoingStates(handle, text, createdSince, baseline))
      } catch is CancellationError {
        return finish(latest, stopped: true)
      } catch {
        // One failed read (a locked store, a checkpoint) is retried on the next
        // tick; the outcome is unreadable only if no read after the send works.
      }
      if now() >= deadline { break }
      do {
        try await sleep(pollInterval)
      } catch {
        return finish(latest, stopped: true)
      }
    }
    return finish(latest)
  }

  /// What the new matching rows support, decided over all of them.
  ///
  /// Rows with an error are failed attempts. One row without an error is Omi's
  /// message, delivered or sent, even when a failed attempt came first (an
  /// iMessage error followed by the text-message fallback). Two or more rows
  /// without an error mean an identical message went to the same person in
  /// the same moment, and Omi cannot tell which one is its own.
  enum Verdict: Equatable {
    case noRow, notYetSent, ambiguous, notDelivered
    case sent(afterError: Bool)
    case delivered(afterError: Bool)

    init(_ rows: [OutgoingMessageState]) {
      let failed = rows.filter { $0.errorCode != 0 }
      let succeeded = rows.filter { $0.errorCode == 0 }
      if rows.isEmpty {
        self = .noRow
      } else if succeeded.count > 1 {
        self = .ambiguous
      } else if let row = succeeded.first {
        if row.isDelivered {
          self = .delivered(afterError: !failed.isEmpty)
        } else if row.isSent {
          self = .sent(afterError: !failed.isEmpty)
        } else {
          self = .notYetSent
        }
      } else {
        self = .notDelivered
      }
    }
  }

  private struct Outcome {
    let status: MessageSendOutcomeStatus
    let reason: MessageSendConfirmation.UnconfirmedReason?
    var afterError = false

    init(_ status: MessageSendOutcomeStatus, _ reason: MessageSendConfirmation.UnconfirmedReason?) {
      self.status = status
      self.reason = reason
    }

    /// No successful read after the send leaves no verdict: the history was unreadable.
    init(_ verdict: Verdict?) {
      switch verdict {
      case .delivered(let afterError):
        self.init(.delivered, nil)
        self.afterError = afterError
      case .sent(let afterError):
        self.init(.sent, nil)
        self.afterError = afterError
      case .notDelivered: self.init(.notDelivered, nil)
      case .notYetSent: self.init(.unconfirmed, .notYetSent)
      case .ambiguous: self.init(.unconfirmed, .ambiguous)
      case .noRow: self.init(.unconfirmed, .noMatchingRow)
      case nil: self.init(.unconfirmed, .historyUnreadable)
      }
    }
  }
}
