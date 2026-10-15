import CryptoKit
import Foundation

/// Local navigation projection, never a second wire contract.
enum ProactivityNotificationTarget: Equatable {
  case conversation(String)
  case actionItem(String)

  init?(_ target: OmiAPI.ProactivityTarget) {
    guard !target.id.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
    switch target.kind {
    case "conversation": self = .conversation(target.id)
    case "action_item": self = .actionItem(target.id)
    default: return nil
    }
  }
}

/// The feed consumer owns polling, expiry, and durable presentation receipts.
/// It supplies the generated item, its captured owner, and receipt callbacks;
/// suppressed/queued cards never create a shown receipt. Event IDs are stable
/// across refresh, push, retries and relaunch for server-side idempotency.
@MainActor
enum ProactivityNotificationAdapter {
  static func target(for item: OmiAPI.ProactivityFeedItem) -> ProactivityNotificationTarget? {
    guard !item.dismissed, !item.acted,
      !item.id.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
      !item.title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
      !item.body.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    else { return nil }
    return ProactivityNotificationTarget(item.target)
  }

  static func identity(ownerID: String, itemID: String, event: String = "presentation") -> UUID {
    let bytes = Array(SHA256.hash(data: Data("proactivity-v2:\(ownerID):\(itemID):\(event)".utf8)))
    return UUID(
      uuid: (
        bytes[0], bytes[1], bytes[2], bytes[3], bytes[4], bytes[5], bytes[6], bytes[7],
        bytes[8], bytes[9], bytes[10], bytes[11], bytes[12], bytes[13], bytes[14], bytes[15]
      ))
  }

  static func open(_ target: ProactivityNotificationTarget, onOpened: @escaping () -> Void = {}) {
    switch target {
    case .conversation(let id): MeetingSummaryShareActions.openSummary(conversationID: id)
    case .actionItem(let id): ChatFirstShellNavigation.shared.open(focus: .task(id: id))
    }
    let snapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot()
    Task { @MainActor in
      for _ in 0..<100 {
        guard let snapshot, RuntimeOwnerIdentity.isAuthorizationCurrent(snapshot) else { return }
        let opened: Bool
        switch target {
        case .conversation(let id): opened = ConversationDetailAutomationState.shared.openConversationId == id
        case .actionItem(let id):
          let navigation = ChatFirstShellNavigation.shared
          opened =
            navigation.visibleRoute == .tasks && navigation.focusedEntityID == id
            && navigation.isFocusedEntityAcknowledged
        }
        if opened {
          onOpened()
          return
        }
        try? await Task.sleep(for: .milliseconds(100))
      }
    }
  }

  static func present(
    _ item: OmiAPI.ProactivityFeedItem,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot,
    hasBeenPresented: (_ itemID: String) -> Bool,
    channel: String = "feed",
    expiresAt: Date? = nil,
    onDropped: @escaping () -> Void = {},
    onOutcome: @escaping (_ itemID: String, _ request: OmiAPI.ProactivityOutcomeRequest) -> Void
  ) {
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot),
      let target = target(for: item), !hasBeenPresented(item.id)
    else {
      onDropped()
      return
    }
    var emitted = Set<String>()
    func emit(_ action: String) {
      guard action != "timeout", RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot),
        emitted.insert(action).inserted
      else { return }
      onOutcome(
        item.id,
        .init(
          action: action, channel: channel,
          eventId: identity(ownerID: authorizationSnapshot.ownerID, itemID: item.id, event: action).uuidString
            .lowercased(),
          surface: "macos"))
    }
    NotificationService.shared.sendNotification(
      ownerID: authorizationSnapshot.ownerID,
      title: item.title,
      message: item.body,
      assistantId: "proactivity_v2",
      context: FloatingBarNotificationContext(
        sourceTitle: item.title, assistantId: "proactivity_v2", provenanceRef: item.id),
      action: .openProactivityItem(target),
      authorizationSnapshot: authorizationSnapshot,
      onPresented: { emit("shown") },
      notificationID: identity(ownerID: authorizationSnapshot.ownerID, itemID: item.id),
      onInteraction: { emit($0.rawValue) }, expiresAt: expiresAt, onDropped: onDropped)
  }
}
