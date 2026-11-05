import Foundation
import Observation
import OmiNetwork
import OmiPersistence

/// Per task app settings (Flutter `asana_settings_page`, `clickup_settings_page`, `todoist_…`,
/// `google_tasks_…`): which app new tasks go to, and for Asana (workspace, project) and ClickUp
/// (team, space, list) where in it. The backend does not return the saved place, so it is also
/// remembered here.
@MainActor
@Observable
public final class TaskAppSettingsStore {
    public private(set) var defaultApp: String?
    public private(set) var options: [TaskAppLevel: [TaskAppOption]] = [:]
    public private(set) var selection: [String: [TaskAppLevel: TaskAppOption]] = [:]
    public private(set) var loading: Set<TaskAppLevel> = []
    public private(set) var failed = false

    private let api: any APIClientProtocol
    private let preferences: Preferences

    public init(api: any APIClientProtocol, preferences: Preferences) {
        self.api = api
        self.preferences = preferences
        selection = Self.decode(preferences.string(.taskAppSelections))
    }

    /// The default app and the first level's choices (the next levels follow the saved place).
    public func load(_ app: String) async {
        failed = false
        defaultApp = try? await api.defaultTaskApp()
        var parent: String?
        for level in TaskAppLevel.levels(for: app) {
            guard level == TaskAppLevel.levels(for: app).first || parent != nil else { break }
            await loadOptions(level, parent: parent)
            parent = selection[app]?[level]?.id
        }
    }

    /// Picks `option` on `level`; the levels below it are cleared (on the backend too) and their
    /// choices loaded. Taken back if the backend refuses.
    public func select(_ app: String, level: TaskAppLevel, option: TaskAppOption?) async {
        let levels = TaskAppLevel.levels(for: app)
        guard let index = levels.firstIndex(of: level) else { return }
        let previous = selection[app] ?? [:]
        var updated = previous
        updated[level] = option
        var change: [TaskAppLevel: TaskAppOption?] = [level: option]
        for below in levels.dropFirst(index + 1) {
            updated[below] = nil
            change[below] = .some(nil)
            options[below] = nil
        }
        selection[app] = updated
        do {
            try await api.saveTaskAppSelection(app, selection: change)
            save()
        } catch {
            selection[app] = previous
            failed = true
            return
        }
        if let option, index + 1 < levels.count { await loadOptions(levels[index + 1], parent: option.id) }
    }

    /// New tasks from conversations go to this app.
    public func makeDefault(_ app: String) async {
        let previous = defaultApp
        defaultApp = app
        do {
            try await api.setDefaultTaskApp(app)
        } catch {
            defaultApp = previous
            failed = true
        }
    }

    /// After a disconnect: the saved place no longer applies.
    public func forget(_ app: String) {
        selection[app] = nil
        if defaultApp == app { defaultApp = nil }
        save()
    }

    private func loadOptions(_ level: TaskAppLevel, parent: String?) async {
        loading.insert(level)
        defer { loading.remove(level) }
        do {
            options[level] = try await api.taskAppOptions(level, parent: parent)
        } catch {
            failed = true
        }
    }

    private func save() {
        let plain = selection.mapValues { levels in
            Dictionary(uniqueKeysWithValues: levels.map { ($0.key.rawValue, $0.value) })
        }
        let data = try? JSONEncoder().encode(plain)
        preferences.set(data.flatMap { String(data: $0, encoding: .utf8) }, for: .taskAppSelections)
    }

    static func decode(_ json: String?) -> [String: [TaskAppLevel: TaskAppOption]] {
        guard let data = json?.data(using: .utf8),
              let plain = try? JSONDecoder().decode([String: [String: TaskAppOption]].self, from: data) else { return [:] }
        return plain.mapValues { levels in
            Dictionary(uniqueKeysWithValues: levels.compactMap { key, value in TaskAppLevel(rawValue: key).map { ($0, value) } })
        }
    }
}
