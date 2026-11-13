import Foundation
import Observation
import OmiCore
import OmiNetwork
import OmiService

/// The one inbox for links (notification taps, `omi://` URLs, `-omiDeepLink`). A link waits here
/// until `MainTabView` is on screen (cold start, sign-in, onboarding), which then opens it.
@MainActor
@Observable
final class DeepLinkRouter {
    private(set) var pending: DeepLink?

    func open(_ link: DeepLink?) {
        // A tap without a destination still brings the app forward; nothing to route.
        if let link { pending = link }
    }

    func take() -> DeepLink? {
        defer { pending = nil }
        return pending
    }

    /// What the shell shows for a link, with the target loaded first when it is not in a store yet.
    enum Destination {
        case route(MainTabView.Route)
        case tab(MainTabView.Tab)
        case handOver(ActionItem)
        /// A task Omi has not worked on: its detail over Home.
        case task(ActionItem)
        case chat
        case device
        // Siri, quick actions and h.omi.me links.
        case chatDraft(String)
        case newTask
        case record
        case account
        /// One app's page (`h.omi.me/apps/<id>`).
        case app(String)
    }

    static func destination(for link: DeepLink, in environment: AppEnvironment) async -> Destination {
        switch link {
        case let .conversation(id):
            if let known = environment.conversations.conversations.first(where: { $0.id == id }) {
                return .route(.conversation(known))
            }
            guard let detail = try? await environment.api.conversationDetail(id: id) else { return .tab(.home) }
            return .route(.conversation(detail.conversation))
        case let .task(id):
            if !environment.tasks.tasks.contains(where: { $0.id == id }) { await environment.tasks.load() }
            guard let task = environment.tasks.tasks.first(where: { $0.id == id }) else { return .route(.allTasks) }
            // Omi worked on it: open the run (progress or the finished result).
            let hasRun = environment.agent.runs[id] != nil || task.workstreamID != nil
            return hasRun ? .handOver(task) : .task(task)
        case let .recap(key):
            return await recap(key, in: environment.conversations).map { .route(.recap($0)) } ?? .tab(.home)
        case .tasks: return .route(.allTasks)
        case let .sharedTasks(token):
            // Tasks shows the accept sheet (or says the link expired).
            await environment.tasks.openShare(token: token)
            return .route(.allTasks)
        case .memories: return .tab(.memory)
        case .home: return .tab(.home)
        case .chat: return .chat
        case .device: return .device
        case .memory: return .tab(.memory)
        case let .folder(id):
            await environment.conversations.setFilter(.folder(id))
            return .tab(.home)
        case let .chatDraft(text): return .chatDraft(text)
        case .newTask: return .newTask
        case .record: return .record
        case .account: return .account
        case let .app(id): return .app(id)
        }
    }

    /// By summary id (pushes) or local date (`omi://recap/2026-10-07`, generated if missing).
    private static func recap(_ key: String, in store: ConversationsStore) async -> DailySummary? {
        let match = { store.recaps.first { $0.id == key || $0.date == key } }
        if let found = match() { return found }
        await store.loadRecaps()
        if let found = match() { return found }
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.dateFormat = "yyyy-MM-dd"
        guard let day = formatter.date(from: key) else { return nil }
        await store.createRecap(for: day)
        return match()
    }
}

/// An app page opened by a link, as a sheet item.
struct LinkedApp: Identifiable, Hashable {
    let id: String
}
