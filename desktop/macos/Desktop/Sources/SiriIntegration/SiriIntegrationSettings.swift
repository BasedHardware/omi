import Foundation

/// A local preference. Explicit Shortcuts remain available when indexing is off.
enum SiriIntegrationSettings {
  static let key = "siriAppleIntelligenceEnabled"

  static var isEnabled: Bool {
    get { UserDefaults.standard.object(forKey: key) as? Bool ?? true }
    set {
      UserDefaults.standard.set(newValue, forKey: key)
      NotificationCenter.default.post(name: .siriIndexPreferenceChanged, object: nil)
    }
  }
}

extension Notification.Name {
  static let siriIndexPreferenceChanged = Notification.Name("siriIndexPreferenceChanged")
}

/// Holds a search intent until the Conversations page mounts after navigation.
/// This file is also compiled by the required Xcode 26.6 no-Siri build.
@MainActor
enum SiriPendingConversationSearch {
  private static var pending: (owner: String?, query: String)?

  static func store(_ query: String) {
    pending = (RuntimeOwnerIdentity.currentOwnerId(), query)
  }

  static func take() -> String? {
    defer { pending = nil }
    guard let pending, pending.owner == RuntimeOwnerIdentity.currentOwnerId() else { return nil }
    return pending.query
  }

  static func clear() { pending = nil }
}

#if !compiler(>=6.4)
  import SwiftUI

  /// Xcode 26.6 builds retain store and view call sites without indexing.
  enum SiriIndexHooks {
    static func rebuild() {}
    static func memoryChanged(_ id: String) {}
    static func memoriesChanged(_ ids: [String]) {}
    static func memoryDeleted(_ id: String) async {}
    static func memoriesDeleted(_ ids: [String]) async {}
    static func conversationChanged(_ id: String) {}
    static func conversationsChanged(_ ids: [String]) {}
    static func conversationDeleted(_ id: String) async {}
    static func tasksChanged(_ ids: [String]) {}
    static func taskDeleted(_ id: String) async {}
    static func tasksDeleted(_ ids: [String]) async {}
    static func ownerChanged() {}
  }

  @MainActor
  final class SiriIndexLifecycle {
    static let shared = SiriIndexLifecycle()
    func start(launchMode: String) {}
    static func suspendForOwnerTransition() async {
      await RewindIndexer.shared.suspendForOwnerTransition()
    }
  }

  enum SiriDonations {
    static func conversationOpened(_ id: String) {}
    static func memoryCreated(_ id: String) {}
    static func taskCompleted(_ id: String) {}
    static func wipe() async {}
  }

  extension View {
    func siriConversationIdentifier(_ id: String) -> some View { self }
    func siriMemoryIdentifier(_ id: String) -> some View { self }
    func siriTaskIdentifier(_ id: String) -> some View { self }
  }
#endif
