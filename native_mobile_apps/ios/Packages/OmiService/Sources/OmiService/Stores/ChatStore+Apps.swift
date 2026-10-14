import Foundation
import OmiCore
import OmiNetwork
import OmiPersistence

/// Chat apps and personas (Flutter `chat_apps_drawer.dart`): the chat talks to Omi or to one enabled
/// app that can chat. Each app has its own history in its own backend session (created with the
/// app's id, so the backend answers as that app); the main chat and agent runs are never touched.
public extension ChatStore {
    /// The user's enabled apps with the `chat` or `persona` capability.
    func loadChatApps() async {
        guard let apps = try? await api.searchApps(query: "", installedOnly: true, offset: 0) else { return }
        chatApps = apps.filter(\.worksWithChat)
        // The chosen app was turned off elsewhere: back to Omi.
        if let chatApp, !chatApps.contains(where: { $0.id == chatApp.id }) { await talk(to: nil) }
    }

    /// Switches the chat to `app` (nil: Omi). Not while an answer is streaming.
    func talk(to app: OmiApp?) async {
        guard app?.id != chatApp?.id, !isStreaming else { return }
        chatApp = app
        preferences.set(app?.id, for: .selectedChatAppID)
        resetForScope()
        await loadHistory()
    }

    /// The app chosen last time, restored once its details are known.
    internal func restoreChatApp() async {
        guard chatApp == nil, let id = preferences.string(.selectedChatAppID) else { return }
        await loadChatApps()
        guard chatApp == nil, let app = chatApps.first(where: { $0.id == id }) else {
            if !chatApps.isEmpty { preferences.set(nil, for: .selectedChatAppID) }
            return
        }
        chatApp = app
    }

    /// The session the current chat reads and writes: the main chat's pinned one, or the app's
    /// newest (opened on first use).
    internal func resolveSession() async -> String? {
        await restoreChatApp()
        guard let app = chatApp else { return await resolveMainSession() }
        if let sessions = try? await api.chatSessions(appID: app.id), let newest = sessions.first { return newest.id }
        return try? await api.createChatSession(title: app.name, appID: app.id)
    }
}
