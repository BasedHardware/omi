import Foundation

/// Where the app remembers "open this exact task next".
///
/// This file used to hold `DashboardIntelligenceStore` and the whole client
/// protocol it fetched through. Nothing rendered that store once `DashboardPage`
/// was deleted (#12598) — its recommendations had no surface — so it went with
/// the page. This handoff stayed: `QueryShellHome` and the chat-first task card
/// both hand the Tasks page an exact record rather than a tab index.
@MainActor
final class TaskNavigationRequestStore {
  static let shared = TaskNavigationRequestStore()
  enum Target: Equatable {
    case task(String)
    case candidate(String)
  }

  private(set) var pendingTarget: Target?
  private(set) var pendingTask: TaskActionItem?
  private(set) var pendingCandidate: OmiAPI.CandidateRecord?
  private var runtimeOwnerObserver: NSObjectProtocol?

  init() {
    runtimeOwnerObserver = NotificationCenter.default.addObserver(
      forName: .runtimeOwnerDidChange,
      object: nil,
      queue: .main
    ) { [weak self] _ in
      Task { @MainActor [weak self] in self?.clear() }
    }
  }

  func request(task: TaskActionItem) {
    pendingTarget = .task(task.id)
    pendingTask = task
    pendingCandidate = nil
  }

  func request(candidate: OmiAPI.CandidateRecord) {
    pendingTarget = .candidate(candidate.candidateId)
    pendingTask = nil
    pendingCandidate = candidate
  }

  func peek() -> Target? {
    pendingTarget
  }

  func consumeIfAvailable(taskIDs: Set<String>, candidateIDs: Set<String>) -> Target? {
    guard let target = pendingTarget else { return nil }
    let isAvailable: Bool
    switch target {
    case .task(let id): isAvailable = taskIDs.contains(id)
    case .candidate(let id): isAvailable = candidateIDs.contains(id)
    }
    guard isAvailable else { return nil }
    clear()
    return target
  }

  private func clear() {
    pendingTarget = nil
    pendingTask = nil
    pendingCandidate = nil
  }
}
