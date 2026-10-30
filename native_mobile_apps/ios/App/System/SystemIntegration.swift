import AppIntents
import CoreSpotlight
import Foundation
import Observation
import OmiCore
import OmiDesign
import OmiService
import os
import UIKit

/// Keeps what iOS shows of Omi in step with the stores: Spotlight items for conversations, tasks
/// and memories, and the Home Screen quick actions. It only observes; nothing in the stores knows
/// about it (like `ExtrasBridge`).
@MainActor
final class SystemIntegration {
    nonisolated private static let log = Logger(subsystem: "omi", category: "system")
    private let environment: AppEnvironment
    private let index = CSSearchableIndex.default()
    /// What Spotlight has, so a change only sends the difference.
    private var indexed: [String: SpotlightRecord] = [:]
    private var pending: Task<Void, Never>?
    private var quickActionsShown = false

    init(environment: AppEnvironment) {
        self.environment = environment
        observe { $0.update() }
    }

    private func observe(_ apply: @escaping @MainActor (SystemIntegration) -> Void) {
        withObservationTracking {
            apply(self)
        } onChange: { [weak self] in
            Task { @MainActor in self?.observe(apply) }
        }
    }

    private func update() {
        let signedIn = if case .ready = environment.session.phase { true } else { false }
        showQuickActions(signedIn)
        guard signedIn else {
            // Signed out (or someone else signing in next): nothing of this account stays searchable.
            if environment.session.phase == .signedOut { clearIndex() }
            return
        }
        guard environment.conversations.phase == .loaded || environment.tasks.phase == .loaded
            || environment.memories.phase == .loaded else { return }
        let records = SpotlightRecord.records(
            conversations: environment.conversations.conversations,
            tasks: environment.tasks.phase == .loaded ? environment.tasks.tasks : [],
            memories: environment.memories.phase == .loaded ? environment.memories.memories : []
        )
        let loadedKinds = Set<SpotlightRecord.Kind>([
            environment.conversations.phase == .loaded ? .conversation : nil,
            environment.tasks.phase == .loaded ? .task : nil,
            environment.memories.phase == .loaded ? .memory : nil,
        ].compactMap(\.self))
        // Store changes come in bursts (a load, then edits); index once they settle.
        pending?.cancel()
        pending = Task { [weak self] in
            try? await Task.sleep(for: .seconds(2))
            guard !Task.isCancelled else { return }
            await self?.reindex(records, kinds: loadedKinds)
        }
    }

    /// Adds or updates what changed and removes what is gone, for the kinds that have loaded.
    private func reindex(_ records: [SpotlightRecord], kinds: Set<SpotlightRecord.Kind>) async {
        let current = Dictionary(records.map { ($0.identifier, $0) }, uniquingKeysWith: { first, _ in first })
        let removed = indexed.values.filter { kinds.contains($0.kind) && current[$0.identifier] == nil }.map(\.identifier)
        let changed = current.values.filter { indexed[$0.identifier] != $0 }
        guard !removed.isEmpty || !changed.isEmpty else { return }
        do {
            if !removed.isEmpty { try await index.deleteSearchableItems(withIdentifiers: removed) }
            if !changed.isEmpty { try await index.indexSearchableItems(changed.map(Self.item)) }
            removed.forEach { indexed[$0] = nil }
            changed.forEach { indexed[$0.identifier] = $0 }
        } catch {
            Self.log.error("Spotlight update failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    /// The item's identifier is its `omi://` link (a tap continues with it, `OmiApp`); the attached
    /// entity lets Siri and Apple Intelligence act on it too.
    private static func item(_ record: SpotlightRecord) -> CSSearchableItem {
        let attributes = CSSearchableItemAttributeSet(contentType: .text)
        attributes.title = record.title
        attributes.contentDescription = record.text.isEmpty ? nil : record.text
        attributes.contentCreationDate = record.date
        let item = CSSearchableItem(uniqueIdentifier: record.identifier, domainIdentifier: record.kind.rawValue, attributeSet: attributes)
        associate(record, with: item)
        return item
    }

    private static func associate(_ record: SpotlightRecord, with item: CSSearchableItem) {
        guard let environment = AppIntentsBridge.environment else { return }
        switch record.kind {
        case .conversation:
            if let match = environment.conversations.conversations.first(where: { $0.id == record.id }) {
                item.associateAppEntity(ConversationEntity(match), priority: 0)
            }
        case .task:
            if let match = environment.tasks.tasks.first(where: { $0.id == record.id }) {
                item.associateAppEntity(TaskEntity(match), priority: 0)
            }
        case .memory:
            if let match = environment.memories.memories.first(where: { $0.id == record.id }) {
                item.associateAppEntity(MemoryEntity(match), priority: 0)
            }
        }
    }

    private func clearIndex() {
        pending?.cancel()
        guard !indexed.isEmpty else { return }
        indexed = [:]
        index.deleteAllSearchableItems { error in
            if let error { Self.log.error("Spotlight clear failed: \(error.localizedDescription, privacy: .public)") }
        }
    }

    // MARK: Quick actions

    private func showQuickActions(_ signedIn: Bool) {
        guard signedIn != quickActionsShown else { return }
        quickActionsShown = signedIn
        UIApplication.shared.shortcutItems = signedIn ? QuickAction.menuOrder.map(Self.shortcutItem) : []
    }

    private static func shortcutItem(_ action: QuickAction) -> UIApplicationShortcutItem {
        let title = switch action {
        case .askOmi: L("quickActionAskOmi")
        case .addTask: L("addTask")
        case .startRecording: L("startRecording")
        case .myOmi: L("nativeQuickActionMyOmi")
        }
        return UIApplicationShortcutItem(
            type: action.rawValue, localizedTitle: title, localizedSubtitle: nil,
            icon: UIApplicationShortcutIcon(systemImageName: action.systemImage)
        )
    }
}

/// Receives quick actions: at launch in the scene's connection options, later from the window scene.
/// SwiftUI keeps owning the window; this delegate only forwards the shortcut to the router.
final class QuickActionSceneDelegate: NSObject, UIWindowSceneDelegate {
    func scene(_: UIScene, willConnectTo _: UISceneSession, options connectionOptions: UIScene.ConnectionOptions) {
        if let item = connectionOptions.shortcutItem { Self.perform(item) }
    }

    func windowScene(_: UIWindowScene, performActionFor shortcutItem: UIApplicationShortcutItem) async -> Bool {
        Self.perform(shortcutItem)
    }

    @discardableResult
    private static func perform(_ item: UIApplicationShortcutItem) -> Bool {
        guard let action = QuickAction(shortcutType: item.type) else { return false }
        AppIntentsBridge.open(action.link)
        return true
    }
}

extension AppDelegate {
    func application(
        _: UIApplication, configurationForConnecting connectingSceneSession: UISceneSession, options _: UIScene.ConnectionOptions
    ) -> UISceneConfiguration {
        let configuration = UISceneConfiguration(name: nil, sessionRole: connectingSceneSession.role)
        configuration.delegateClass = QuickActionSceneDelegate.self
        return configuration
    }
}
