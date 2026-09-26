import AppIntents
import Foundation

@MainActor
enum SiriNavigator {
  static func openConversation(_ id: String) {
    ConversationDetailAutomationState.shared.requestOpen(conversationId: id, showTranscript: false)
    NotificationCenter.default.post(name: .desktopAutomationOpenConversationRequested, object: nil)
  }

  static func openMemory(_ id: String) {
    TaskDetailSourceNavigator.open(.memory(id: id))
  }

  static func openTask(_ task: TaskActionItem) {
    TaskNavigationRequestStore.shared.request(task: task)
    NotificationCenter.default.post(name: .navigateToTasks, object: nil)
  }

  static func search(_ query: String) {
    NotificationCenter.default.post(name: .desktopAutomationOpenConversationRequested, object: nil)
    NotificationCenter.default.post(
      name: .desktopAutomationSetConversationsSearchRequested,
      object: nil, userInfo: ["query": query])
  }
}

@available(macOS 27, *)
@AppIntent(schema: .system.open)
struct OmiOpenIntent: OpenIntent {
  static let title: LocalizedStringResource = "Open in Omi"
  var target: ConversationEntity

  @MainActor
  func perform() async throws -> some IntentResult {
    try await SiriIntentTelemetry.perform("open") {
      guard let resolved = try await ConversationEntityQuery().entities(for: [target.id]).first
      else { throw SiriFailure.unsupported }
      if resolved.folder?.id == OmiFolderEntity.memories.id {
        SiriNavigator.openMemory(target.id)
      } else {
        SiriNavigator.openConversation(target.id)
      }
    }
    return .result()
  }
}

@available(macOS 27, *)
@AppIntent(schema: .system.open)
struct OmiOpenMemoryIntent: OpenIntent {
  static let title: LocalizedStringResource = "Open Memory in Omi"
  var target: MemoryEntity

  @MainActor
  func perform() async throws -> some IntentResult {
    try await SiriIntentTelemetry.perform("open") {
      guard try await MemoryEntityQuery().entities(for: [target.id]).first != nil
      else { throw SiriFailure.unsupported }
      SiriNavigator.openMemory(target.id)
    }
    return .result()
  }
}

@available(macOS 27, *)
@AppIntent(schema: .system.open)
struct OmiOpenTaskIntent: OpenIntent {
  static let title: LocalizedStringResource = "Open Task in Omi"
  var target: TaskEntity

  @MainActor
  func perform() async throws -> some IntentResult {
    try await SiriIntentTelemetry.perform("open") {
      guard let owner = RuntimeOwnerIdentity.currentOwnerId(),
        let task = try await ActionItemStorage.shared.getLocalActionItem(byBackendId: target.id),
        RuntimeOwnerIdentity.currentOwnerId() == owner, !task.isRetired
      else {
        throw SiriFailure.unsupported
      }
      SiriNavigator.openTask(task)
    }
    return .result()
  }
}

@available(macOS 27, *)
@AppIntent(schema: .system.open)
struct OmiOpenFolderIntent: OpenIntent {
  static let title: LocalizedStringResource = "Open Omi Folder"
  var target: OmiFolderEntity

  @MainActor
  func perform() async throws -> some IntentResult {
    try await SiriIntentTelemetry.perform("open") {
      if target.id == "conversations" {
        NotificationCenter.default.post(name: .desktopAutomationOpenConversationRequested, object: nil)
      } else if target.id == "memories" {
        NotificationCenter.default.post(
          name: .navigateToSidebarItem, object: nil,
          userInfo: ["rawValue": SidebarNavItem.memories.rawValue])
      } else {
        throw SiriFailure.unsupported
      }
    }
    return .result()
  }
}

@available(macOS 27, *)
@AppIntent(schema: .system.open)
struct OmiOpenListIntent: OpenIntent {
  static let title: LocalizedStringResource = "Open Omi Tasks"
  var target: OmiListEntity

  @MainActor
  func perform() async throws -> some IntentResult {
    try await SiriIntentTelemetry.perform("open") {
      guard target.id == "omi" else { throw SiriFailure.unsupported }
      NotificationCenter.default.post(name: .navigateToTasks, object: nil)
    }
    return .result()
  }
}

@available(macOS 27, *)
@AppIntent(schema: .system.searchInApp)
struct OmiSearchIntent: ShowInAppSearchResultsIntent {
  static let title: LocalizedStringResource = "Search Omi"
  static let searchScopes: [StringSearchScope] = [.general]
  var criteria: StringSearchCriteria

  @MainActor
  func perform() async throws -> some IntentResult {
    try await SiriIntentTelemetry.perform("search") { SiriNavigator.search(criteria.term) }
    return .result()
  }
}
