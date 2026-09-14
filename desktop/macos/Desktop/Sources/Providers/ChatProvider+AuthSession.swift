import Combine
import Foundation

extension ChatProvider {
  func makeAuthSessionNotificationObserver() -> AnyCancellable {
    let invalidate = NotificationCenter.default.publisher(for: .sessionDidInvalidate)
    let authenticate = NotificationCenter.default.publisher(for: .sessionDidAuthenticate)
    return Publishers.Merge(invalidate, authenticate)
      .sink { [weak self] notification in
        Task { @MainActor in
          guard let self else { return }
          if notification.name == .sessionDidInvalidate {
            log("ChatProvider: sessionDidInvalidate — stopping agent bridge")
            if self.agentBridgeStarted {
              await self.resolvedAgentClient().stop()
              self.agentBridgeStarted = false
            }
            return
          }
          await self.reloadChatSessionsAfterAuthentication()
        }
      }
  }

  func reloadChatSessionsAfterAuthentication() async {
    guard AuthState.shared.isSignedIn else { return }
    log("ChatProvider: sessionDidAuthenticate — reloading chat sessions")
    await initializeVisibleMessages()
    await refreshJournalProjection()
  }
}
