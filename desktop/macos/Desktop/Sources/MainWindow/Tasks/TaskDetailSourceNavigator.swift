import AppKit
import Foundation

@MainActor
enum TaskDetailSourceNavigator {
  static func open(_ route: TaskDetailSourceRoute) {
    switch route {
    case .conversation(let id), .capture(let id):
      ConversationDetailAutomationState.shared.requestOpen(conversationId: id, showTranscript: false)
      NotificationCenter.default.post(name: .desktopAutomationOpenConversationRequested, object: nil)
    case .memory(let id):
      // Both shells mount the memory detail owner from the Memories rail item.
      // Persisting the Memory Hub destination first keeps the legacy hub and
      // the typed Chat-first route aligned before the detail request arrives.
      UserDefaults.standard.set(MemoryHubDestination.memories.rawValue, forKey: MemoryHubDestination.storageKey)
      NotificationCenter.default.post(
        name: .navigateToSidebarItem,
        object: nil,
        userInfo: ["rawValue": SidebarNavItem.memories.rawValue]
      )
      DispatchQueue.main.async {
        NotificationCenter.default.post(
          name: .desktopAutomationMemoryDetailOpenRequested,
          object: nil,
          userInfo: ["memory_id": id]
        )
      }
    case .rewind:
      NotificationCenter.default.post(name: .navigateToRewind, object: nil)
    case .external(let url):
      NSWorkspace.shared.open(url)
    }
  }
}
