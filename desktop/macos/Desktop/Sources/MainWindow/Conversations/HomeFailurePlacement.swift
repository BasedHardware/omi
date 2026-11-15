import Combine
import Foundation

/// Shared Home/Activity admission. Missing fields and failed reads retain the
/// previous list; owner changes fence stale responses without persisting a flag.
@MainActor
final class HomeFailurePlacementStore: ObservableObject {
  static let shared = HomeFailurePlacementStore()
  @Published private(set) var enabled = false
  @Published private var discovered: [String: ServerConversation] = [:]
  private var removed = Set<String>()
  private let load: () async throws -> Bool
  private let owner: () -> String?
  private let onReadFailure: () -> Void
  private var generation = 0
  private var previousOwner: String?

  init(
    load: (() async throws -> Bool)? = nil,
    owner: (() -> String?)? = nil,
    onReadFailure: (() -> Void)? = nil
  ) {
    self.load = load ?? { try await APIClient.shared.getHomeFailurePlacement() }
    self.owner = owner ?? { AuthState.shared.userId }
    self.onReadFailure =
      onReadFailure ?? {
        DesktopDiagnosticsManager.shared.recordFallback(
          area: "other", from: "none", to: "none", reason: "other", outcome: .degraded)
      }
  }

  func reset() {
    generation += 1
    enabled = false
    previousOwner = nil
    discovered = [:]
    removed = []
  }

  func forget(_ id: String) {
    removed.insert(id)
    discovered.removeValue(forKey: id)
  }

  /// Home filters and search can discover failures outside the current page. Preserve their
  /// Activity links without inserting them into the Home repository's list.
  func remember(_ rows: [ServerConversation], for identity: String?) {
    guard identity != nil, identity == owner() else { return }
    for row in rows {
      if ConversationFailurePlacement.isFailed(row) && !removed.contains(row.id) {
        discovered[row.id] = row
      } else {
        discovered.removeValue(forKey: row.id)
      }
    }
  }

  func activity(_ loaded: [ServerConversation]) -> [ServerConversation] {
    var all = discovered
    for row in loaded where !removed.contains(row.id) { all[row.id] = row }
    return ConversationFailurePlacement.activity(Array(all.values), confirmed: enabled)
      .sorted { ($0.startedAt ?? $0.createdAt) > ($1.startedAt ?? $1.createdAt) }
  }

  func refresh() async {
    generation += 1
    let request = generation
    let identity = owner()
    if identity != previousOwner {
      enabled = false
      discovered = [:]
      removed = []
    }
    previousOwner = identity
    guard identity != nil else {
      enabled = false
      return
    }
    let confirmed: Bool
    do { confirmed = try await load() } catch {
      confirmed = false
      onReadFailure()
    }
    guard request == generation else { return }
    guard owner() == identity else {
      enabled = false
      return
    }
    enabled = confirmed
  }
}

enum ConversationFailurePlacement {
  static func isFailed(_ conversation: ServerConversation) -> Bool {
    conversation.homeStep == "failed" || conversation.status == .failed
  }

  static func home(_ conversations: [ServerConversation], confirmed: Bool) -> [ServerConversation] {
    confirmed ? conversations.filter { !isFailed($0) && $0.homeStep != "noise" } : conversations
  }

  static func activity(_ conversations: [ServerConversation], confirmed: Bool) -> [ServerConversation] {
    confirmed ? conversations.filter { !$0.deleted && !$0.discarded && isFailed($0) } : []
  }
}
