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
          await self.enqueueAuthSessionNotification {
            if notification.name == .sessionDidInvalidate {
              await self.stopAgentBridgeAfterSessionInvalidation()
              return
            }
            await self.reloadChatSessionsAfterAuthentication()
          }
        }
      }
  }

  func reloadChatSessionsAfterAuthentication() async {
    guard AuthState.shared.isSignedIn else { return }
    log("ChatProvider: sessionDidAuthenticate — reloading chat sessions")
    let resumeSessionId = currentSession?.id
    if multiChatEnabled {
      await fetchSessions()
      if let resumeSessionId, let session = sessions.first(where: { $0.id == resumeSessionId }) {
        await selectSession(session)
      }
    } else {
      await loadDefaultChatMessages()
    }
    await refreshJournalProjection()
  }
}
