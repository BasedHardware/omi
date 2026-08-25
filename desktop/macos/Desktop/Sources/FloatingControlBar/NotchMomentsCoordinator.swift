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
  private var knownTaskIds = Set<String>()
  /// Open-task ids captured when the current conversation started, so the end card
  /// counts only the follow-ups this conversation produced — not the whole backlog.
  private var sessionBaselineTaskIds = Set<String>()
  /// When the current conversation started. Used as a `createdAt` floor so paginated
  /// or cross-device-synced older tasks (new ids, but old timestamps) can't inflate
  /// the end-card count.
  private var sessionStartedAt: Date?
  /// The task shown in the most recent receipt (so Undo can retract it).
  private var lastReceiptTask: TaskActionItem?
  /// Receipt verification runs asynchronously against the canonical action-items
  /// read path. Keep one request per observed task so cache updates cannot emit
  /// duplicate success receipts while that read is in flight.
  private var pendingReceiptVerificationIDs = Set<String>()

  private init() {}

  func start(appState: AppState) {
    guard !started else { return }
    started = true
    self.appState = appState
    wasTranscribing = appState.isTranscribing
    knownTaskIds = Set(TasksStore.shared.incompleteTasks.map(\.id))
    sessionBaselineTaskIds = knownTaskIds
    // If we begin monitoring mid-conversation, count follow-ups from now on.
    sessionStartedAt = appState.isTranscribing ? Date() : nil

    appState.$isTranscribing
      .receive(on: RunLoop.main)
      .sink { [weak self] transcribing in self?.handleTranscribing(transcribing) }
      .store(in: &cancellables)

    TasksStore.shared.$incompleteTasks
      .receive(on: RunLoop.main)
      .sink { [weak self] tasks in self?.handleTasks(tasks) }
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

  // MARK: live receipts

  private func handleTasks(_ tasks: [TaskActionItem]) {
    let currentIds = Set(tasks.map(\.id))
    defer { knownTaskIds = currentIds }
    // Only surface receipts for tasks that appear WHILE listening — that's the
    // "Omi is writing this down" moment. Backfilled loads shouldn't spam the pill.
    guard appState?.isTranscribing == true else { return }
    let newIds = currentIds.subtracting(knownTaskIds)
    guard !newIds.isEmpty else { return }
    // Only a task that was *just created* is a live receipt. A paginated backfill
    // or a re-opened old task also adds an id, but its createdAt is stale — skip it
    // so the pill only shows "✓ Noted" the instant Omi actually writes something down.
    let freshCutoff = Date().addingTimeInterval(-120)
    guard
      let newTask =
        tasks
        .filter({ newIds.contains($0.id) && $0.createdAt >= freshCutoff })
        .max(by: { $0.createdAt < $1.createdAt })
    else { return }
    verifyAndPostReceipt(for: newTask)
  }

  /// A local cache insert is not a durable-save acknowledgement. Read the task
  /// through the canonical API before claiming it was saved, then make sure it
  /// still remains in the active local projection before presenting the receipt.
  private func verifyAndPostReceipt(for task: TaskActionItem) {
    guard pendingReceiptVerificationIDs.insert(task.id).inserted else { return }
    guard let ownerID = RuntimeOwnerIdentity.currentOwnerId(),
      let authorizationSnapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: ownerID)
    else {
      pendingReceiptVerificationIDs.remove(task.id)
      return
    }

    Task { @MainActor [weak self] in
      defer { self?.pendingReceiptVerificationIDs.remove(task.id) }
      guard let self else { return }
      do {
        let canonicalTask = try await APIClient.shared.getActionItem(
          id: task.id,
          expectedOwnerId: ownerID,
          authorizationSnapshot: authorizationSnapshot)
        guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot),
          self.appState?.isTranscribing == true,
          Self.isReceiptConfirmation(task, canonicalTask),
          TasksStore.shared.incompleteTasks.contains(where: { $0.id == task.id })
        else { return }
        self.lastReceiptTask = canonicalTask
        self.post(
          title: "✓ Saved to Tasks — \(canonicalTask.description)", message: "",
          assistantId: NotchMoment.receiptAssistantId)
      } catch {
        // Deliberately do not claim a save when the canonical task read fails.
        // The next store update can re-attempt with a new task identity once
        // the task has actually made it through the durable read path.
        log("NotchMoments: Suppressed unconfirmed task receipt")
      }
    }
  }

  /// The receipt contract: the canonical read must name the same active task.
  /// Keep this pure so its behavior remains covered without a live API.
  nonisolated static func isReceiptConfirmation(_ observed: TaskActionItem, _ canonical: TaskActionItem) -> Bool {
    observed.id == canonical.id && !canonical.completed && !canonical.isRetired
  }

  // MARK: actions from the cards

  func undoLastReceipt() {
    guard let task = lastReceiptTask else { return }
    lastReceiptTask = nil
    Task { await TasksStore.shared.deleteTask(task) }
  }

  func reviewFollowUps() {
    AppDelegate.openMainWindow?()
    NotificationCenter.default.post(name: .navigateToTasks, object: nil)
  }

  func reviewLastReceipt() {
    AppDelegate.openMainWindow?()
    NotificationCenter.default.post(name: .navigateToTasks, object: nil)
  }

  // MARK: posting

  private func post(title: String, message: String, assistantId: String) {
    guard let ownerID = RuntimeOwnerIdentity.currentOwnerId() else { return }
    _ = FloatingControlBarManager.shared.showNotification(
      ownerID: ownerID,
      title: title,
      message: message,
      assistantId: assistantId,
      sound: .none)
  }
}
