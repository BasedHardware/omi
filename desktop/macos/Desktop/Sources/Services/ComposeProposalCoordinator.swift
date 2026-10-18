import CryptoKit
import Foundation

/// Holds one outcome and hands it to whoever waits, whichever arrives first.
private final class ComposeOutcomeResolver: @unchecked Sendable {
  private let lock = NSLock()
  private var outcome: ComposeProposalOutcome?
  private var waiter: CheckedContinuation<ComposeProposalOutcome, Never>?

  func resolve(_ value: ComposeProposalOutcome) {
    let resumed: CheckedContinuation<ComposeProposalOutcome, Never>? = lock.withLock {
      guard outcome == nil else { return nil }
      outcome = value
      defer { waiter = nil }
      return waiter
    }
    resumed?.resume(returning: value)
  }

  func value() async -> ComposeProposalOutcome {
    await withCheckedContinuation { continuation in
      let ready: ComposeProposalOutcome? = lock.withLock {
        if let outcome { return outcome }
        waiter = continuation
        return nil
      }
      if let ready { continuation.resume(returning: ready) }
    }
  }
}

/// Hands one draft at a time to a compose window and reports what it ended as.
///
/// On current macOS, `.composeMessage` places the draft in the Messages app's
/// own composer and reports a handoff at once, the way Mail and other email
/// apps do; it reports a send or cancel only if the system shows a sheet
/// instead. So for both channels Omi normally cannot see whether the draft
/// was sent or discarded.
///
/// Limits, all per signed-in owner:
/// - one draft per channel per request (run): one email and one message, so
///   "email Sam and text him" works but a looping or injected model cannot
///   open a stack of windows inside one answer; and at most three a minute;
/// - the same draft (channel, recipients and text) is not handed off twice
///   within two minutes, so "send it" after a draft never stacks copies;
/// - if the system shows a Messages sheet and it is still open, no other
///   draft opens;
/// - no draft is handed off while the person is typing. Return sends from the
///   Messages composer, so a keystroke that lands there can send the draft;
///   this guard is what prevents it. The last idle check runs with no
///   suspension before the handoff.
@MainActor
final class ComposeProposalCoordinator {
  typealias Sleeper = @Sendable (Duration) async -> Void

  static let shared: ComposeProposalCoordinator = {
    let coordinator = ComposeProposalCoordinator(
      surface: SystemComposeSurface(),
      secondsSinceLastKeyPress: { UserInputPresence.secondsSinceLastKeyPress() })
    // Sign-out is an owner change: drop the slot and the limits with it.
    NotificationCenter.default.addObserver(forName: .userDidSignOut, object: nil, queue: nil) { _ in
      Task { @MainActor in
        ComposeProposalCoordinator.shared.releaseForOwnerChange()
        ComposeRecipientGrounding.shared.releaseAll()
      }
    }
    return coordinator
  }()

  /// How long one call waits for the window to report. Messages and email
  /// apps report as soon as they take the draft; only a system sheet would
  /// report when the person sends or cancels. With the typing wait this stays
  /// under the 30 s tool timeout, so a person still in a sheet reads as
  /// `open`, never as a failed call.
  static let defaultOutcomeWait: Duration = .seconds(15)

  /// No key press for this long counts as "not typing".
  static let typingQuietSeconds: TimeInterval = 3
  /// The longest a call waits for the person to stop typing.
  static let maxTypingWait: Duration = .seconds(8)
  static let typingPollInterval: Duration = .milliseconds(250)

  /// A Messages sheet that never reported stops blocking new drafts after this long.
  static let defaultStaleAfter: TimeInterval = 300
  static let maxProposalsPerMinute = 3
  /// An identical draft is refused for this long after it was handed off.
  static let duplicateWindow: TimeInterval = 120
  /// After a message draft is handed off, `send_message` to the same person is
  /// refused for this long: the draft is waiting in Messages for them to send.
  static let openDraftSendWindow: TimeInterval = 600
  /// How long handed-off drafts are remembered, for every limit above.
  static let presentedRetention: TimeInterval = 600

  private struct Pending {
    let id: UUID
    let ownerID: String?
    let startedAt: Date
    let resolver: ComposeOutcomeResolver
  }

  private struct Presented {
    let id: UUID
    let ownerID: String?
    let runID: String?
    let channel: ComposeProposalChannel
    /// A digest of the channel, recipients and text; the draft itself is not
    /// kept. Cleared when the window reports a cancel or failure, so the
    /// person can ask for the same draft again.
    var draftDigest: String?
    /// Normalised recipient keys, so `send_message` can see a waiting draft.
    let recipientKeys: [String]
    let at: Date
  }

  private let surface: ComposeSurface
  private let outcomeWait: Duration
  private let staleAfter: TimeInterval
  private let sleep: Sleeper
  private let now: () -> Date
  private let secondsSinceLastKeyPress: () -> TimeInterval?
  private var pending: Pending?
  private var presented: [Presented] = []

  init(
    surface: ComposeSurface,
    secondsSinceLastKeyPress: @escaping () -> TimeInterval?,
    outcomeWait: Duration = ComposeProposalCoordinator.defaultOutcomeWait,
    staleAfter: TimeInterval = ComposeProposalCoordinator.defaultStaleAfter,
    sleep: @escaping Sleeper = { try? await Task.sleep(for: $0) },
    now: @escaping () -> Date = Date.init
  ) {
    self.surface = surface
    self.secondsSinceLastKeyPress = secondsSinceLastKeyPress
    self.outcomeWait = outcomeWait
    self.staleAfter = staleAfter
    self.sleep = sleep
    self.now = now
  }

  func propose(_ proposal: ComposeProposal, context: ComposeProposalContext) async -> ComposeProposalOutcome {
    guard !Task.isCancelled else { return .notOpened(.stopped) }
    releaseIfOwnerChanged(to: context.ownerID)
    // A second draft on top of one the person is still reading invites
    // sending the wrong one.
    if let pending, now().timeIntervalSince(pending.startedAt) < staleAfter {
      return .alreadyOpen
    }
    let digest = Self.draftDigest(proposal)
    if isDuplicate(digest, ownerID: context.ownerID) { return .duplicateDraft }
    if limitReached(for: context, channel: proposal.channel) { return .limitReached }
    guard surface.canPresent(proposal) else { return .unavailable }

    // Claimed before the first suspension, so a concurrent call sees it.
    let id = UUID()
    let resolver = ComposeOutcomeResolver()
    pending = Pending(id: id, ownerID: context.ownerID, startedAt: now(), resolver: resolver)

    if let reason = await waitForKeyboardQuiet() {
      releasePending(id)
      return .notOpened(reason)
    }
    // An owner change while waiting released the slot; this call is stale.
    guard pending?.id == id else { return .notOpened(.stopped) }

    // Recorded before the handoff, so a report that arrives inside
    // `present` can still clear the duplicate digest.
    presented.append(
      Presented(
        id: id, ownerID: context.ownerID, runID: context.runID, channel: proposal.channel, draftDigest: digest,
        recipientKeys: proposal.recipients.compactMap(ComposeRecipientGrounding.recipientKey),
        at: now()))
    let started = surface.present(proposal) { [weak self] event in
      self?.receive(event, for: id)
    }
    guard started else {
      presented.removeAll { $0.id == id }
      releasePending(id)
      return .unavailable
    }

    let waitBound = outcomeWait
    let sleep = sleep
    let timer = Task {
      await sleep(waitBound)
      guard !Task.isCancelled else { return }
      resolver.resolve(.open)
    }
    let outcome = await withTaskCancellationHandler {
      await resolver.value()
    } onCancel: {
      // The turn was stopped, but the window is the person's now; it stays.
      resolver.resolve(.open)
    }
    timer.cancel()
    return outcome
  }

  /// Drops the slot and every limit, for a sign-out or owner switch.
  func releaseForOwnerChange() {
    pending = nil
    presented.removeAll()
  }

  private func releaseIfOwnerChanged(to ownerID: String?) {
    if let pending, pending.ownerID != ownerID {
      self.pending = nil
    }
    presented.removeAll { $0.ownerID != ownerID }
  }

  private func releasePending(_ id: UUID) {
    if pending?.id == id { pending = nil }
  }

  /// The recipients of a message draft this owner handed to Messages in the
  /// last ten minutes that `recipient` matches (same normalisation as the
  /// grounding check), or nil. A cancelled or failed draft does not count.
  func waitingMessageDraft(to recipient: String, ownerID: String?) -> [String]? {
    guard let key = ComposeRecipientGrounding.recipientKey(recipient) else { return nil }
    let current = now()
    return presented.last { draft in
      draft.ownerID == ownerID && draft.channel == .message && draft.draftDigest != nil
        && current.timeIntervalSince(draft.at) < Self.openDraftSendWindow
        && draft.recipientKeys.contains { ComposeRecipientGrounding.keysMatch(key, $0) }
    }?.recipientKeys
  }

  private func isDuplicate(_ digest: String, ownerID: String?) -> Bool {
    let current = now()
    return presented.contains {
      $0.ownerID == ownerID && $0.draftDigest == digest && current.timeIntervalSince($0.at) < Self.duplicateWindow
    }
  }

  /// Same channel, same recipients in any order and spelling, same text.
  nonisolated static func draftDigest(_ proposal: ComposeProposal) -> String {
    let recipients = proposal.recipients
      .map { ComposeRecipientGrounding.recipientKey($0) ?? $0.lowercased() }
      .sorted()
      .joined(separator: "\u{1}")
    let text = proposal.body.trimmingCharacters(in: .whitespacesAndNewlines)
    let material = [proposal.channel.rawValue, recipients, proposal.subject ?? "", text].joined(separator: "\u{0}")
    return SHA256.hash(data: Data(material.utf8)).map { String(format: "%02x", $0) }.joined()
  }

  private func limitReached(for context: ComposeProposalContext, channel: ComposeProposalChannel) -> Bool {
    let current = now()
    presented.removeAll { current.timeIntervalSince($0.at) >= Self.presentedRetention }
    let lastMinute = presented.filter { current.timeIntervalSince($0.at) < 60 }
    if let runID = context.runID {
      let sameRun = presented.contains {
        $0.runID == runID && $0.channel == channel && current.timeIntervalSince($0.at) < staleAfter
      }
      if sameRun { return true }
    } else if !lastMinute.isEmpty {
      // Without a run to tell requests apart, one draft a minute.
      return true
    }
    return lastMinute.count >= Self.maxProposalsPerMinute
  }

  /// Nil once the keyboard has been quiet long enough, or why no window opens.
  private func waitForKeyboardQuiet() async -> ComposeNotOpenedReason? {
    var waited: Duration = .zero
    while let idle = secondsSinceLastKeyPress(), idle < Self.typingQuietSeconds {
      guard waited < Self.maxTypingWait else { return .personTyping }
      await sleep(Self.typingPollInterval)
      waited += Self.typingPollInterval
      if Task.isCancelled { return .stopped }
    }
    return Task.isCancelled ? .stopped : nil
  }

  /// A late report still frees the slot even after the call returned `open`.
  private func receive(_ event: ComposeSurfaceEvent, for id: UUID) {
    if event != .shared, let index = presented.firstIndex(where: { $0.id == id }) {
      presented[index].draftDigest = nil
    }
    guard let pending, pending.id == id else { return }
    self.pending = nil
    switch event {
    case .shared: pending.resolver.resolve(.handedOff)
    case .cancelled: pending.resolver.resolve(.cancelled)
    case .notConfigured: pending.resolver.resolve(.unavailable)
    case .failed(let code): pending.resolver.resolve(.failed(code: code))
    }
  }
}
