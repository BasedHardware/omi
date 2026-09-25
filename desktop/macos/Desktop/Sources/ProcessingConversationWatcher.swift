import Foundation

/// Keeps every visible processing row honest until it reaches a terminal
/// state. The list itself never polls — the only completion signal is the
/// live-listen `memory_created` event, which cloud finalization does not
/// always deliver — so without this a row could sit on "Processing" forever
/// with the UI none the wiser (the 2026-08-30 finalization outage ran six
/// hours that way).
///
/// Polling never gives up while the row is visible; it backs off to the last
/// delay and stays there. The watcher also owns the two telemetry facts the
/// row cannot: how long processing actually took, and when it crossed the
/// stalled threshold.
@MainActor
final class ProcessingConversationWatcher: ObservableObject {
  typealias Fetch = @Sendable (String) async throws -> ServerConversation
  typealias Sleeper = @Sendable (UInt64) async throws -> Void

  /// Backoff in seconds; the final entry repeats indefinitely.
  static let pollDelaysSeconds: [Double] = [3, 5, 10, 15, 30, 60]

  static func pollDelay(attempt: Int) -> Double {
    pollDelaysSeconds[min(max(attempt, 0), pollDelaysSeconds.count - 1)]
  }

  /// Rows that just reached `completed` and whose memories/action items are
  /// still landing server-side. The row shows a quiet hint until the grace
  /// refetch clears it.
  @Published private(set) var settlingDerivedIDs: Set<String> = []

  private let fetch: Fetch
  private let sleeper: Sleeper
  private let now: () -> Date
  private let onResolved: @MainActor (ServerConversation) -> Void
  private let onCompleted: @MainActor (_ conversationID: String, _ elapsedSeconds: Int, _ outcome: String) -> Void
  private let onStalled: @MainActor (_ conversationID: String, _ elapsedSeconds: Int) -> Void

  private var tasks: [String: Task<Void, Never>] = [:]
  private var stalledReported: Set<String> = []

  init(
    fetch: @escaping Fetch,
    sleeper: @escaping Sleeper = { try await Task.sleep(nanoseconds: $0) },
    now: @escaping () -> Date = Date.init,
    onResolved: @escaping @MainActor (ServerConversation) -> Void,
    onCompleted: @escaping @MainActor (String, Int, String) -> Void,
    onStalled: @escaping @MainActor (String, Int) -> Void
  ) {
    self.fetch = fetch
    self.sleeper = sleeper
    self.now = now
    self.onResolved = onResolved
    self.onCompleted = onCompleted
    self.onStalled = onStalled
  }

  /// Detail fetch used by production wiring. Kept as a named function so the
  /// call site can reference it without an actor hop in a default-argument
  /// position.
  static func fetchDetail(id: String) async throws -> ServerConversation {
    try await APIClient.shared.getConversation(id: id)
  }

  /// Production wiring: real clock, real sleeper, PostHog telemetry.
  static func live(
    fetch: @escaping Fetch,
    onResolved: @escaping @MainActor (ServerConversation) -> Void
  ) -> ProcessingConversationWatcher {
    ProcessingConversationWatcher(
      fetch: fetch,
      onResolved: onResolved,
      onCompleted: { id, elapsed, outcome in
        AnalyticsManager.shared.conversationProcessingCompleted(
          conversationId: id, elapsedSeconds: elapsed, outcome: outcome)
      },
      onStalled: { id, elapsed in
        AnalyticsManager.shared.conversationProcessingStalled(conversationId: id, elapsedSeconds: elapsed)
      }
    )
  }

  /// Which rows the watcher should be following.
  static func shouldWatch(_ conversation: ServerConversation) -> Bool {
    conversation.displayState == .processing
  }

  var watchedIDs: Set<String> { Set(tasks.keys) }

  func isSettlingDerived(_ conversationID: String) -> Bool {
    settlingDerivedIDs.contains(conversationID)
  }

  /// Reconcile with the currently visible list: start following new
  /// processing rows, stop following rows that left the list or resolved
  /// through another path (a `memory_created` refresh, a reprocess).
  func sync(with conversations: [ServerConversation]) {
    let wanted = conversations.filter(Self.shouldWatch)
    let wantedIDs = Set(wanted.map(\.id))
    for (id, task) in tasks where !wantedIDs.contains(id) {
      task.cancel()
      tasks.removeValue(forKey: id)
    }
    for conversation in wanted where tasks[conversation.id] == nil {
      tasks[conversation.id] = Task { [weak self] in
        await self?.follow(conversation)
      }
    }
  }

  func stopAll() {
    for task in tasks.values { task.cancel() }
    tasks.removeAll()
    settlingDerivedIDs.removeAll()
  }

  private func follow(_ initial: ServerConversation) async {
    let id = initial.id
    var attempt = 0
    reportStalledIfNeeded(initial)
    while !Task.isCancelled {
      let delay = Self.pollDelay(attempt: attempt)
      attempt += 1
      guard (try? await sleeper(UInt64(delay * 1_000_000_000))) != nil, !Task.isCancelled else { return }
      guard let fetched = try? await fetch(id), !Task.isCancelled else {
        reportStalledIfNeeded(initial)
        continue
      }
      if Self.shouldWatch(fetched) {
        // Still processing. Detail responses carry transcript segments the
        // list omitted, so publishing keeps the provisional title current.
        onResolved(fetched)
        reportStalledIfNeeded(fetched)
        continue
      }
      resolve(fetched)
      return
    }
  }

  private func resolve(_ fetched: ServerConversation) {
    let id = fetched.id
    let elapsed = Int(ConversationProcessingProgress.elapsed(for: fetched, now: now()))
    let outcome = fetched.status == .failed ? "failed" : "completed"
    tasks.removeValue(forKey: id)
    if fetched.status == .completed {
      settlingDerivedIDs.insert(id)
    }
    onResolved(fetched)
    onCompleted(id, elapsed, outcome)
    guard fetched.status == .completed else { return }
    Task { [weak self] in
      guard let self else { return }
      let grace = UInt64(ConversationProcessingProgress.derivedSettleGrace * 1_000_000_000)
      if (try? await self.sleeper(grace)) != nil, let settled = try? await self.fetch(id) {
        self.onResolved(settled)
      }
      self.settlingDerivedIDs.remove(id)
    }
  }

  private func reportStalledIfNeeded(_ conversation: ServerConversation) {
    let elapsed = ConversationProcessingProgress.elapsed(for: conversation, now: now())
    guard ConversationProcessingProgress.phase(elapsed: elapsed) == .stalled,
      stalledReported.insert(conversation.id).inserted
    else { return }
    onStalled(conversation.id, Int(elapsed))
  }
}
