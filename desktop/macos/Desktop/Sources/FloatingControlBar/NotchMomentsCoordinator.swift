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
  /// The task shown in the most recent receipt (so Undo can retract it).
  private var lastReceiptTask: TaskActionItem?

  private init() {}

  func start(appState: AppState) {
    guard !started else { return }
    started = true
    self.appState = appState
    wasTranscribing = appState.isTranscribing
    knownTaskIds = Set(TasksStore.shared.incompleteTasks.map(\.id))

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
    // Fire only on the stop edge (was recording → now stopped).
    guard wasTranscribing, !transcribing else { return }
    let open = TasksStore.shared.incompleteTasks.count
    guard open > 0 else { return }
    let title = open == 1 ? "1 follow-up ready" : "\(open) follow-ups ready"
    post(title: title, message: "Conversation ended", assistantId: NotchMoment.endAssistantId)
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
      let newTask = tasks
        .filter({ newIds.contains($0.id) && $0.createdAt >= freshCutoff })
        .max(by: { $0.createdAt < $1.createdAt })
    else { return }
    lastReceiptTask = newTask
    post(
      title: "✓ Noted — \(newTask.description)", message: "",
      assistantId: NotchMoment.receiptAssistantId)
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
