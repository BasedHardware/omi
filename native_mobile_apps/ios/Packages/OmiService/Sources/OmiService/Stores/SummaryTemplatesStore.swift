import Foundation
import Observation
import OmiCore
import OmiNetwork
import OmiPersistence

/// "Summary template" for one conversation (Flutter `summarized_apps_sheet`): the apps Omi
/// suggests, the user's summary apps (default and last used first), summarizing again with one,
/// setting the default, and writing a new template.
@MainActor
@Observable
public final class SummaryTemplatesStore {
    public enum Phase: Equatable, Sendable { case loading, loaded }

    public enum Failure: Equatable, Sendable {
        case install(String)
        case saveDefault
        case create
        case reprocess
    }

    public enum CreationStep: Equatable, Sendable { case describing, creating, installing }

    public private(set) var phase: Phase = .loading
    /// Suggested apps not already among the user's apps.
    public private(set) var suggested: [OmiApp] = []
    /// The user's enabled summary apps: default, last used, then by name.
    public private(set) var apps: [OmiApp] = []
    public private(set) var defaultAppID: String?
    public private(set) var lastUsedAppID: String?
    /// The app being installed or summarizing with.
    public private(set) var working: String?
    public private(set) var creationStep: CreationStep?
    public var failure: Failure?

    let api: any APIClientProtocol
    let preferences: Preferences?

    public init(api: any APIClientProtocol, preferences: Preferences?) {
        self.api = api
        self.preferences = preferences
        defaultAppID = preferences?.string(.preferredSummarizationAppId)
        lastUsedAppID = preferences?.string(.lastUsedSummarizationAppId)
    }

    public func load(conversationID: String) async {
        async let suggestedApps = try? api.suggestedSummaryApps(conversationID: conversationID)
        async let enabledApps = try? api.summaryApps()
        let (suggestions, enabled) = await (suggestedApps ?? [], enabledApps ?? [])
        let mine = Set(enabled.map(\.id))
        suggested = suggestions.filter { !mine.contains($0.id) }
        apps = order(enabled)
        phase = .loaded
    }

    /// Every known app by id (the detail page names the app that wrote the summary).
    public func app(_ id: String?) -> OmiApp? {
        guard let id else { return nil }
        return apps.first { $0.id == id } ?? suggested.first { $0.id == id }
    }

    /// Summarizes the conversation again with `app`, installing it first when it is a suggestion.
    @discardableResult
    public func summarize(_ detail: ConversationDetailStore, with app: OmiApp, in list: ConversationsStore) async -> Bool {
        guard working == nil else { return false }
        working = app.id
        defer { working = nil }
        if !apps.contains(where: { $0.id == app.id }) {
            do {
                try await api.setApp(app.id, enabled: true)
            } catch {
                failure = .install(app.name)
                return false
            }
            var installed = app
            installed.isEnabled = true
            suggested.removeAll { $0.id == app.id }
            apps = order(apps + [installed])
        }
        lastUsedAppID = app.id
        preferences?.set(app.id, for: .lastUsedSummarizationAppId)
        guard await detail.reprocess(in: list, appID: app.id) else {
            failure = .reprocess
            return false
        }
        return true
    }

    /// Future conversations are summarized with `app` (nothing is summarized again now).
    @discardableResult
    public func setDefault(_ app: OmiApp) async -> Bool {
        do {
            try await api.setPreferredSummaryApp(id: app.id)
        } catch {
            failure = .saveDefault
            return false
        }
        defaultAppID = app.id
        preferences?.set(app.id, for: .preferredSummarizationAppId)
        apps = order(apps)
        return true
    }

    /// Writes a summary app from a name and prompt, installs it, and returns it (Flutter
    /// `create_template_bottom_sheet`). `icon` draws the emoji Omi picked as a PNG.
    public func create(_ draft: SummaryTemplateDraft, icon: @MainActor (String) -> Data?) async -> OmiApp? {
        guard draft.problem == nil, creationStep == nil else { return nil }
        defer { creationStep = nil }
        let name = draft.name.trimmingCharacters(in: .whitespacesAndNewlines)
        creationStep = .describing
        let generated = await (try? api.generateAppDescription(name: name, prompt: draft.prompt))
            ?? (description: "A custom app that \(draft.prompt)", emoji: "✨")
        creationStep = .creating
        guard let png = icon(generated.emoji),
              let id = try? await api.createSummaryApp(draft, description: generated.description, icon: png)
        else {
            failure = .create
            return nil
        }
        creationStep = .installing
        do {
            try await api.setApp(id, enabled: true)
        } catch {
            failure = .install(name)
            return nil
        }
        let app = OmiApp(
            id: id, name: name, description: generated.description, author: nil, imageURL: nil, category: "conversation-analysis",
            rating: nil, installs: 0, isEnabled: true, capabilities: ["memories"]
        )
        apps = order(apps.filter { $0.id != id } + [app])
        return app
    }

    /// Default first, then last used, then by name.
    private func order(_ list: [OmiApp]) -> [OmiApp] {
        func rank(_ app: OmiApp) -> Int {
            if app.id == defaultAppID { return 0 }
            if app.id == lastUsedAppID { return 1 }
            return 2
        }
        return list.sorted { lhs, rhs in
            if rank(lhs) != rank(rhs) { return rank(lhs) < rank(rhs) }
            return lhs.name.localizedCaseInsensitiveCompare(rhs.name) == .orderedAscending
        }
    }
}
