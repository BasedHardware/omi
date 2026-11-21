import Foundation
import Observation
import OmiNetwork
import OmiPersistence

/// Settings › Developer (Flutter `pages/settings/developer.dart`): webhooks, API and MCP keys, the
/// MCP config, debug logs and the experimental switches the backend honours.
@MainActor
@Observable
public final class DeveloperStore {
    public struct Webhook: Equatable, Sendable {
        /// What is typed (not saved yet).
        public var url = ""
        /// Audio bytes only: seconds of audio per call.
        public var seconds = DeveloperWebhook.defaultAudioInterval
        public var isEnabled = false
        /// What the backend has, to tell unsaved edits apart.
        public var savedURL = ""
        public var savedSeconds = DeveloperWebhook.defaultAudioInterval

        public init(
            url: String = "", seconds: Int = DeveloperWebhook.defaultAudioInterval, isEnabled: Bool = false,
            savedURL: String = "", savedSeconds: Int = DeveloperWebhook.defaultAudioInterval
        ) {
            self.url = url
            self.seconds = seconds
            self.isEnabled = isEnabled
            self.savedURL = savedURL
            self.savedSeconds = savedSeconds
        }

        public var hasChanges: Bool {
            url.trimmingCharacters(in: .whitespaces) != savedURL || (!url.isEmpty && seconds != savedSeconds)
        }
    }

    public enum Failure: Equatable, Sendable {
        /// Not a public http(s) address (checked here, and by the backend).
        case invalidURL(DeveloperWebhook)
        case couldNotSave
        case couldNotLoad
    }

    public internal(set) var webhooks: [DeveloperWebhook: Webhook] = Dictionary(
        uniqueKeysWithValues: DeveloperWebhook.allCases.map { ($0, Webhook()) }
    )
    public private(set) var apiKeys: [DeveloperKey] = []
    public private(set) var mcpKeys: [DeveloperKey] = []
    /// A key just created: its secret is shown once, then only its prefix.
    public var createdKey: DeveloperKey?
    /// Which list `createdKey` belongs to.
    public private(set) var createdKeyKind: DeveloperKey.Kind?
    public private(set) var isLoading = false
    public private(set) var isSaving = false
    public var failure: Failure?
    /// `https://api…/v1/mcp` (Flutter `mcp_config.dart`).
    public let mcpServerURL: URL

    /// Settings shows the Developer row (switched in Help & Feedback).
    public var isDeveloperMode: Bool {
        didSet { preferences.set(isDeveloperMode, for: .developerMode) }
    }

    /// Conversation developer tools: Copy ID in a conversation's menu (Flutter `devModeEnabled`).
    public var showsConversationTools: Bool {
        didSet { preferences.set(showsConversationTools, for: .devModeEnabled) }
    }

    /// `vad_gate=enabled` on the next recording: the backend sends only speech to transcription.
    public var vadGate: Bool {
        didSet { preferences.set(vadGate, for: .vadGateEnabled) }
    }

    private let api: any APIClientProtocol
    private let preferences: Preferences

    public init(api: any APIClientProtocol, preferences: Preferences, apiBaseURL: URL) {
        self.api = api
        self.preferences = preferences
        var base = apiBaseURL.absoluteString
        while base.hasSuffix("/") {
            base.removeLast()
        }
        mcpServerURL = URL(string: base + "/v1/mcp") ?? apiBaseURL
        isDeveloperMode = preferences.bool(.developerMode, default: false)
        showsConversationTools = preferences.bool(.devModeEnabled, default: false)
        vadGate = preferences.bool(.vadGateEnabled, default: false)
    }

    public func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            let status = try await api.webhookStatus()
            for hook in DeveloperWebhook.allCases {
                let stored = try await api.webhookURL(hook)
                var webhook = Webhook(isEnabled: status[hook] ?? false)
                if hook == .audioBytes {
                    let (url, seconds) = DeveloperWebhook.splitAudio(stored)
                    (webhook.url, webhook.seconds, webhook.savedURL, webhook.savedSeconds) = (url, seconds, url, seconds)
                } else {
                    (webhook.url, webhook.savedURL) = (stored, stored)
                }
                webhooks[hook] = webhook
            }
            apiKeys = try await api.developerKeys(.api)
            mcpKeys = try await api.developerKeys(.mcp)
        } catch {
            failure = .couldNotLoad
        }
    }

    // MARK: Webhooks

    public func edit(_ hook: DeveloperWebhook, url: String? = nil, seconds: Int? = nil) {
        if let url { webhooks[hook]?.url = url }
        if let seconds { webhooks[hook]?.seconds = max(1, seconds) }
    }

    /// Back to what the backend has.
    public func discardWebhookEdits() {
        for hook in DeveloperWebhook.allCases {
            webhooks[hook]?.url = webhooks[hook]?.savedURL ?? ""
            webhooks[hook]?.seconds = webhooks[hook]?.savedSeconds ?? DeveloperWebhook.defaultAudioInterval
        }
    }

    public var hasUnsavedWebhooks: Bool {
        webhooks.values.contains(where: \.hasChanges)
    }

    /// Saves every changed URL. An empty URL turns its webhook off, a new one turns it on (backend).
    @discardableResult
    public func saveWebhooks() async -> Bool {
        failure = nil
        let changed = DeveloperWebhook.allCases.filter { webhooks[$0]?.hasChanges == true }
        if let invalid = changed.first(where: { !Self.isValidWebhook(webhooks[$0]?.url ?? "") }) {
            failure = .invalidURL(invalid)
            return false
        }
        isSaving = true
        defer { isSaving = false }
        for hook in changed {
            guard let webhook = webhooks[hook] else { continue }
            let url = webhook.url.trimmingCharacters(in: .whitespaces)
            let stored = hook == .audioBytes ? DeveloperWebhook.joinAudio(url: url, seconds: webhook.seconds) : url
            do {
                try await api.setWebhookURL(hook, url: stored)
                webhooks[hook] = Webhook(
                    url: url, seconds: webhook.seconds, isEnabled: !url.isEmpty, savedURL: url, savedSeconds: webhook.seconds
                )
            } catch let APIError.http(status, _) where status == 400 || status == 422 {
                failure = .invalidURL(hook)
                return false
            } catch {
                failure = .couldNotSave
                return false
            }
        }
        return true
    }

    /// The switch beside a saved URL; taken back if the backend refuses.
    public func setEnabled(_ hook: DeveloperWebhook, _ enabled: Bool) async {
        guard webhooks[hook]?.isEnabled != enabled else { return }
        webhooks[hook]?.isEnabled = enabled
        do {
            try await api.setWebhook(hook, enabled: enabled)
        } catch {
            webhooks[hook]?.isEnabled = !enabled
            failure = .couldNotSave
        }
    }

    /// Empty (clears it) or an http(s) URL with a host; the backend also refuses private addresses.
    public nonisolated static func isValidWebhook(_ text: String) -> Bool {
        let trimmed = text.trimmingCharacters(in: .whitespaces)
        if trimmed.isEmpty { return true }
        guard let url = URL(string: trimmed), let scheme = url.scheme?.lowercased(), ["http", "https"].contains(scheme),
              let host = url.host(), host.contains(".") || host == "localhost" else { return false }
        return !trimmed.contains(" ")
    }

    // MARK: Keys

    /// Creates a key; the secret lands in `createdKey`. API keys are read-only unless `fullAccess`.
    @discardableResult
    public func createKey(_ kind: DeveloperKey.Kind, name: String, fullAccess: Bool = false) async -> Bool {
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return false }
        failure = nil
        let scopes = kind == .api && fullAccess ? Self.fullAccessScopes : nil
        do {
            let key = try await api.createDeveloperKey(kind, name: trimmed, scopes: scopes)
            createdKey = key
            createdKeyKind = kind
            let listed = DeveloperKey(
                id: key.id, name: key.name, prefix: key.prefix, createdAt: key.createdAt, lastUsedAt: key.lastUsedAt,
                scopes: key.scopes, secret: nil
            )
            if kind == .api { apiKeys.insert(listed, at: 0) } else { mcpKeys.insert(listed, at: 0) }
            return true
        } catch {
            failure = .couldNotSave
            return false
        }
    }

    public func revoke(_ kind: DeveloperKey.Kind, id: String) async {
        let previous = (apiKeys, mcpKeys)
        if kind == .api { apiKeys.removeAll { $0.id == id } } else { mcpKeys.removeAll { $0.id == id } }
        do {
            try await api.revokeDeveloperKey(kind, id: id)
        } catch {
            (apiKeys, mcpKeys) = previous
            failure = .couldNotSave
        }
    }

    /// Every API scope (backend `utils/scopes.py`).
    public static let fullAccessScopes = ["conversations", "memories", "action_items", "goals"].flatMap { ["\($0):read", "\($0):write"] }

    /// The Claude Code / Cursor `mcpServers` entry for `key` (Flutter `mcp_config.dart`).
    public func mcpConfig(key: String) -> String {
        """
        {
          "mcpServers": {
            "omi": {
              "type": "http",
              "url": "\(mcpServerURL.absoluteString)",
              "headers": {
                "Authorization": "Bearer \(key)"
              }
            }
          }
        }
        """
    }
}
