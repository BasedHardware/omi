import Combine
import Foundation

enum NotchMoment {
  static let receiptAssistantId = "notch_receipt"
  static let endAssistantId = "notch_end"
}

/// Drives the Second Brain notch "moments" — live receipts as Omi writes things
/// down, and the conversation-end "N follow-ups ready" card — off REAL app state
/// (transcription lifecycle + TasksStore), routed through the existing hardened
/// notification path. It never touches the notch geometry or the voice/PTT code.
@MainActor
final class NotchMomentsCoordinator {
  static let shared = NotchMomentsCoordinator()

  private var cancellables = Set<AnyCancellable>()
  private var started = false
  private weak var appState: AppState?

  private var wasTranscribing = false
  /// Open-task ids captured when the current conversation started, so the end card
  /// counts only the follow-ups this conversation produced — not the whole backlog.
  private var sessionBaselineTaskIds = Set<String>()
  /// When the current conversation started. Used as a `createdAt` floor so paginated
  /// or cross-device-synced older tasks (new ids, but old timestamps) can't inflate
  /// the end-card count.
  private var sessionStartedAt: Date?
  /// Pending suggestion ids already surfaced, so a store refresh cannot re-announce
  /// the same proposal.
  private var knownSuggestionIDs = Set<String>()

  private init() {}

  func start(appState: AppState) {
    guard !started else { return }
    started = true
    self.appState = appState
    wasTranscribing = appState.isTranscribing
    sessionBaselineTaskIds = Set(TasksStore.shared.incompleteTasks.map(\.id))
    // If we begin monitoring mid-conversation, count follow-ups from now on.
    sessionStartedAt = appState.isTranscribing ? Date() : nil

    appState.$isTranscribing
      .receive(on: RunLoop.main)
      .sink { [weak self] transcribing in self?.handleTranscribing(transcribing) }
      .store(in: &cancellables)

    SuggestedTasksStore.shared.$candidates
      .receive(on: RunLoop.main)
      .sink { [weak self] candidates in self?.handleSuggestedCandidates(candidates) }
      .store(in: &cancellables)
  }

  // MARK: conversation-end

  private func handleTranscribing(_ transcribing: Bool) {
    defer { wasTranscribing = transcribing }
    // On the start edge, snapshot the existing backlog so the end card can count only
    // the follow-ups this conversation actually produced.
    if !wasTranscribing, transcribing {
      sessionBaselineTaskIds = Set(TasksStore.shared.incompleteTasks.map(\.id))
      sessionStartedAt = Date()
      return
    }
    // Fire only on the stop edge (was recording → now stopped).
    guard wasTranscribing, !transcribing else { return }
    let newCount = Self.followUpCount(
      tasks: TasksStore.shared.incompleteTasks,
      baselineIds: sessionBaselineTaskIds,
      since: sessionStartedAt)
    guard newCount > 0 else { return }
    let title = newCount == 1 ? "1 follow-up ready" : "\(newCount) follow-ups ready"
    post(title: title, message: "Conversation ended", assistantId: NotchMoment.endAssistantId)
  }

  /// Follow-ups a conversation actually produced: tasks whose id is new since the
  /// session baseline AND (if a start time is known) created after it. The start-time
  /// floor keeps paginated/synced older tasks — new ids but stale `createdAt` — out of
  /// the count, matching the freshness guard the live-receipt path uses.
  nonisolated static func followUpCount(tasks: [TaskActionItem], baselineIds: Set<String>, since: Date?) -> Int {
    tasks.filter { task in
      guard !baselineIds.contains(task.id) else { return false }
      if let since { return task.createdAt >= since }
      return true
    }.count
  }

  // MARK: live suggestions

  nonisolated static let suggestedMomentFreshness: TimeInterval = 120

  /// Parse a backend `createdAt` timestamp. The backend emits ISO 8601 with or
  /// without fractional seconds depending on the value; `ISO8601DateFormatter`
  /// pins its behavior to the presence of `.withFractionalSeconds`, so try both.
  /// Returns nil on anything unparseable — callers fail closed (not fresh).
  nonisolated static func suggestedCandidateCreatedAt(_ raw: String) -> Date? {
    let fractional = ISO8601DateFormatter()
    fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    let plain = ISO8601DateFormatter()
    plain.formatOptions = [.withInternetDateTime]
    return fractional.date(from: raw) ?? plain.date(from: raw)
  }

  /// The proposal worth surfacing: one not announced before AND created within
  /// the freshness window. The window is what keeps a store load or
  /// cross-device sync (new ids, stale `createdAt`) from announcing an old
  /// suggestion mid-conversation as if Omi had just proposed it.
  nonisolated static func suggestedMomentCandidate(
    candidates: [SuggestedCandidate],
    knownIDs: Set<String>,
    now: Date
  ) -> SuggestedCandidate? {
    let freshCutoff = now.addingTimeInterval(-suggestedMomentFreshness)
    return
      candidates
      .compactMap { candidate -> (SuggestedCandidate, Date)? in
        guard !knownIDs.contains(candidate.id),
          let createdAt = suggestedCandidateCreatedAt(candidate.createdAt),
          createdAt >= freshCutoff
        else { return nil }
        return (candidate, createdAt)
      }
      .max(by: { $0.1 < $1.1 })?.0
  }

  /// Surface a task Omi proposed while listening. INVARIANT I1: this is a
  /// proposal, not a save. The card and its chat row both carry "Add to Tasks";
  /// nothing enters the task list until the user presses it. This replaces the
  /// old "✓ Saved to Tasks" receipt, which acknowledged a write the user never
  /// asked for.
  private func handleSuggestedCandidates(_ candidates: [SuggestedCandidate]) {
    let currentIDs = Set(candidates.map(\.id))
    defer { knownSuggestionIDs = currentIDs }
    // Only while listening: a backfilled load is not a "just now" moment.
    guard appState?.isTranscribing == true else { return }
    guard
      let candidate = Self.suggestedMomentCandidate(
        candidates: candidates, knownIDs: knownSuggestionIDs, now: Date())
    else { return }
    let title = candidate.title.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !title.isEmpty else { return }
    post(
      title: SuggestedTaskChatCard.encode(candidateID: candidate.id, description: title),
      message: "",
      assistantId: NotchMoment.receiptAssistantId)
  }

  // MARK: actions from the cards

  func reviewFollowUps() {
    AppDelegate.openMainWindow?()
    NotificationCenter.default.post(name: .navigateToTasks, object: nil)
  }

  func reviewLastReceipt() {
    AppDelegate.openMainWindow?()
    NotificationCenter.default.post(name: .navigateToTasks, object: nil)
  }

  // MARK: posting

  /// Posts through `NotificationService` rather than straight to the bar.
  ///
  /// These moments are proactive — Omi deciding to surface something off transcription
  /// and task state, with no user request behind them. Calling
  /// `FloatingControlBarManager.showNotification` directly skipped every gate that lives
  /// in `sendNotification`: the master toggle, the frequency throttle, the snooze, and the
  /// presence check. A user who silenced notifications, or who was presenting, still
  /// received "Omi wrote this down" receipts.
  ///
  /// `respectFrequency` is left at its default of `true` because that is exactly what
  /// these are: proactive cards, subject to every control the user has.
  ///
  /// No `kind:` is passed: `sendNotification` derives it as
  /// `ProactiveNotificationKind.from(assistantId:)` — the same expression the old direct
  /// `showNotification` call spelled out — and its category-toggle gate reads that same
  /// value, so stating it twice could only ever drift.
  private func post(title: String, message: String, assistantId: String) {
    guard let ownerID = RuntimeOwnerIdentity.currentOwnerId() else { return }
    NotificationService.shared.sendNotification(
      ownerID: ownerID,
      title: title,
      message: message,
      assistantId: assistantId,
      sound: .none)
  }
}
