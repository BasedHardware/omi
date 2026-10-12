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
  /// `message.service` of the row that confirmed the send ("iMessage", "SMS"),
  /// or nil when nothing confirmed it.
  var confirmedService: String?
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
    /// The recipient matched two different stored numbers, so Omi cannot tell
    /// which conversation is the one it sent to.
    case ambiguousRecipient = "ambiguous_recipient"
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
  /// Matching outgoing rows newer than the baseline row id, plus the rows
  /// already matched by an earlier read, whatever their date.
  let outgoingStates:
    @Sendable (_ handle: String, _ text: String, _ createdSince: Date, _ afterRowID: Int64, _ tracked: Set<Int64>)
      async throws -> OutgoingMessageRead

  /// The real Messages store, matching handles for this Mac's region.
  static var live: MessageSendHistory { store(nil) }

  static func store(_ url: URL?, region: String? = MessagingHandle.currentRegion()) -> MessageSendHistory {
    MessageSendHistory(
      latestRowID: { try await MessagesReaderService.shared.latestMessageRowID(storeOverride: url) },
      outgoingStates: { handle, text, since, afterRowID, tracked in
        try await MessagesReaderService.shared.outgoingMessageStates(
          sentTo: handle, text: text, createdSince: since, afterRowID: afterRowID, trackedRowIDs: tracked,
          region: region, storeOverride: url)
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
/// make the match ambiguous, so the check decides over every new row at the
/// end of the window. The one exception: when the reads have shown the same
/// single delivered row, and no error row, for at least `settledDelivery`,
/// nothing that can still arrive would change a clean delivery except a
/// coincidence, so the check stops there.
enum MessageSendConfirmer {
  /// Rows first seen dated more than this before the send started never
  /// count. The row id baseline already excludes every row that existed before
  /// the send; this only keeps an old message that syncs in from another device
  /// during the window from counting. A row that matched once is tracked by row
  /// id from then on, so a later change to its date cannot drop it. The
  /// residual: an identical message sent to the same person from another of
  /// the person's devices within this second of the send can confirm it.
  static let clockTolerance: TimeInterval = 1
  /// How long a single clean delivered row must stay that way before the
  /// check stops early. Two reads that far apart agree.
  static let settledDelivery: TimeInterval = 1
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
          confirmedService: outcome.service, checks: checks, waitedMilliseconds: Int((waited * 1000).rounded()))
      )
    }

    guard let baseline else { return finish(nil) }
    let deadline = checkStarted.addingTimeInterval(window)
    var latest: Verdict?
    var tracked: Set<Int64> = []
    var cleanDelivery: (rowID: Int64, since: Date)?

    while true {
      if Task.isCancelled { return finish(latest, stopped: true) }
      checks += 1
      do {
        let read = try await history.outgoingStates(handle, text, createdSince, baseline, tracked)
        tracked.formUnion(read.rows.map(\.rowID))
        latest = Verdict(read)
        if case .delivered(afterError: false, _) = latest, read.rows.count == 1 {
          let rowID = read.rows[0].rowID
          if cleanDelivery?.rowID != rowID { cleanDelivery = (rowID, now()) }
        } else {
          cleanDelivery = nil
        }
      } catch is CancellationError {
        return finish(latest, stopped: true)
      } catch {
        // One failed read (a locked store, a checkpoint) is retried on the next
        // tick; the outcome is unreadable only if no read after the send works.
        // It also breaks a run of agreeing reads.
        cleanDelivery = nil
      }
      if let cleanDelivery, now().timeIntervalSince(cleanDelivery.since) >= settledDelivery { break }
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
    case noRow, notYetSent, ambiguous, ambiguousRecipient, notDelivered
    case sent(afterError: Bool, service: String)
    case delivered(afterError: Bool, service: String)

    init(_ read: OutgoingMessageRead) {
      if read.recipientIsAmbiguous {
        self = .ambiguousRecipient
        return
      }
      let rows = read.rows
      let failed = rows.filter { $0.errorCode != 0 }
      let succeeded = rows.filter { $0.errorCode == 0 }
      if rows.isEmpty {
        self = .noRow
      } else if succeeded.count > 1 {
        self = .ambiguous
      } else if let row = succeeded.first {
        if row.isDelivered {
          self = .delivered(afterError: !failed.isEmpty, service: row.service)
        } else if row.isSent {
          self = .sent(afterError: !failed.isEmpty, service: row.service)
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
    var service: String?

    init(_ status: MessageSendOutcomeStatus, _ reason: MessageSendConfirmation.UnconfirmedReason?) {
      self.status = status
      self.reason = reason
    }

    /// No successful read after the send leaves no verdict: the history was unreadable.
    init(_ verdict: Verdict?) {
      switch verdict {
      case .delivered(let afterError, let service):
        self.init(.delivered, nil)
        self.afterError = afterError
        self.service = service
      case .sent(let afterError, let service):
        self.init(.sent, nil)
        self.afterError = afterError
        self.service = service
      case .notDelivered: self.init(.notDelivered, nil)
      case .notYetSent: self.init(.unconfirmed, .notYetSent)
      case .ambiguous: self.init(.unconfirmed, .ambiguous)
      case .ambiguousRecipient: self.init(.unconfirmed, .ambiguousRecipient)
      case .noRow: self.init(.unconfirmed, .noMatchingRow)
      case nil: self.init(.unconfirmed, .historyUnreadable)
      }
    }
  }
}
