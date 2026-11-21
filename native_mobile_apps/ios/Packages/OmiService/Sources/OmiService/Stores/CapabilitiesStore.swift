import Foundation
import Observation
import OmiNetwork

/// What Omi can use on the user's behalf (PLAN.md §4.5 "Capabilities"): calendar, mail, health
/// and every task app in one list, instead of split across Settings and the Tasks tab.
@MainActor
@Observable
public final class CapabilitiesStore {
    /// Order shown; ids are the backend keys.
    public static let catalog: [Integration] = [
        Integration(id: "google_calendar", kind: .integration, isConnected: false),
        Integration(id: "gmail", kind: .integration, isConnected: false),
        Integration(id: "todoist", kind: .taskApp, isConnected: false),
        Integration(id: "asana", kind: .taskApp, isConnected: false),
        Integration(id: "clickup", kind: .taskApp, isConnected: false),
        Integration(id: "google_tasks", kind: .taskApp, isConnected: false),
    ]

    /// Why connecting an app did not work, so its row can say so instead of doing nothing.
    public enum ConnectFailure: Equatable, Sendable {
        /// This server has no login set up for the app (the backend lacks its OAuth client).
        case notConfigured
        /// Omi could not be reached.
        case offline
        /// The person closed the login page.
        case cancelled
        /// The login page or the server reported an error.
        case failed
    }

    public private(set) var integrations: [Integration] = CapabilitiesStore.catalog
    public private(set) var isLoading = false
    public private(set) var connecting: String?
    /// The last failed connect per app id; cleared when the app is tried again or connects.
    public private(set) var failures: [String: ConnectFailure] = [:]

    private let api: any APIClientProtocol

    public init(api: any APIClientProtocol) {
        self.api = api
    }

    public var connectedCount: Int {
        integrations.count(where: \.isConnected)
    }

    public func load() async {
        isLoading = true
        defer { isLoading = false }
        let taskApps = await (try? api.connectedTaskApps()) ?? []
        var updated = integrations
        for index in updated.indices {
            switch updated[index].kind {
            case .taskApp: updated[index].isConnected = taskApps.contains(updated[index].id)
            case .integration: updated[index].isConnected = await (try? api.integrationConnected(updated[index].id)) ?? false
            }
        }
        integrations = updated
        for integration in updated where integration.isConnected {
            failures[integration.id] = nil
        }
    }

    /// The URL to open for connecting; the caller presents it (ASWebAuthenticationSession) and
    /// calls `load()` when it returns. `nil` with `failures[id]` set when there is none.
    public func authorizationURL(for integration: Integration) async -> URL? {
        connecting = integration.id
        failures[integration.id] = nil
        defer { connecting = nil }
        do {
            return try await api.integrationOAuthURL(integration)
        } catch {
            failures[integration.id] = Self.failure(error)
            return nil
        }
    }

    /// The login page closed without connecting: `cancelled` when the person closed it.
    public func loginEnded(_ integration: Integration, cancelled: Bool) {
        failures[integration.id] = cancelled ? .cancelled : .failed
    }

    static func failure(_ error: any Error) -> ConnectFailure {
        switch error as? APIError {
        // "Google Calendar not configured - GOOGLE_CLIENT_ID missing", "Todoist not configured".
        case let .http(_, body) where body.localizedCaseInsensitiveContains("not configured"): .notConfigured
        case .transport: .offline
        default: (error as? URLError) == nil ? .failed : .offline
        }
    }

    // MARK: Apps

    public private(set) var installedApps: [OmiApp] = []
    public private(set) var discoveredApps: [OmiApp] = []

    public func loadApps(query: String = "") async {
        installedApps = await (try? api.searchApps(query: "", installedOnly: true, offset: 0)) ?? []
        discoveredApps = await (try? api.searchApps(query: query, installedOnly: false, offset: 0)) ?? []
    }

    /// Optimistic install / uninstall.
    public func setApp(_ app: OmiApp, enabled: Bool) async {
        func apply(_ value: Bool) {
            if let index = discoveredApps.firstIndex(where: { $0.id == app.id }) { discoveredApps[index].isEnabled = value }
            if value {
                if !installedApps.contains(where: { $0.id == app.id }) {
                    var installed = app
                    installed.isEnabled = true
                    installedApps.append(installed)
                }
            } else {
                installedApps.removeAll { $0.id == app.id }
            }
        }
        apply(enabled)
        do { try await api.setApp(app.id, enabled: enabled) } catch { apply(!enabled) }
    }

    public func disconnect(_ integration: Integration) async {
        try? await api.disconnectIntegration(integration)
        await load()
    }
}
