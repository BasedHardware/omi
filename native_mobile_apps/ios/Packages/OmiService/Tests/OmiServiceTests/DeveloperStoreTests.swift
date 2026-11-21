import Foundation
import OmiNetwork
@testable import OmiService
import OmiTestSupport
import Testing

@MainActor
struct DeveloperStoreTests {
    let api = FakeAPIClient()

    func make() -> DeveloperStore {
        DeveloperStore(api: api, preferences: freshPreferences(), apiBaseURL: URL(string: "https://api.omi.me/")!)
    }

    @Test func loadsWebhooksAndSplitsTheAudioInterval() async {
        api.devApps.webhookURLs = [.audioBytes: "https://hooks.example.com/audio,12", .daySummary: "https://hooks.example.com/day"]
        api.devApps.webhookEnabled = [.audioBytes: true]
        let store = make()
        await store.load()
        #expect(store.webhooks[.audioBytes]?.url == "https://hooks.example.com/audio")
        #expect(store.webhooks[.audioBytes]?.seconds == 12)
        #expect(store.webhooks[.audioBytes]?.isEnabled == true)
        #expect(store.webhooks[.daySummary]?.isEnabled == false)
        #expect(!store.hasUnsavedWebhooks)
    }

    @Test func savesOnlyChangedWebhooksWithTheInterval() async {
        let store = make()
        await store.load()
        store.edit(.audioBytes, url: "https://hooks.example.com/a", seconds: 7)
        #expect(store.hasUnsavedWebhooks)
        #expect(await store.saveWebhooks())
        #expect(api.devApps.log == ["url:audio_bytes:https://hooks.example.com/a,7"])
        #expect(store.webhooks[.audioBytes]?.isEnabled == true)
        #expect(!store.hasUnsavedWebhooks)
        // Clearing the URL turns the webhook off (the backend does the same).
        store.edit(.audioBytes, url: "")
        #expect(await store.saveWebhooks())
        #expect(api.devApps.log.last == "url:audio_bytes:")
        #expect(store.webhooks[.audioBytes]?.isEnabled == false)
    }

    @Test func refusesAnInvalidAddressBeforeSending() async {
        let store = make()
        store.edit(.conversationCreated, url: "not a url")
        #expect(await !store.saveWebhooks())
        #expect(store.failure == .invalidURL(.conversationCreated))
        #expect(api.devApps.log.isEmpty)
        #expect(DeveloperStore.isValidWebhook("https://example.com/hook?x=1"))
        #expect(!DeveloperStore.isValidWebhook("ftp://example.com"))
    }

    @Test func aRefusedSwitchGoesBack() async {
        let store = make()
        api.devApps.nextWriteError = .http(status: 500, body: "")
        await store.setEnabled(.realtimeTranscript, true)
        #expect(store.webhooks[.realtimeTranscript]?.isEnabled == false)
        #expect(store.failure == .couldNotSave)
    }

    @Test func aNewKeyShowsItsSecretOnceAndRevokes() async {
        let store = make()
        #expect(await store.createKey(.api, name: " Zapier ", fullAccess: true))
        #expect(store.createdKey?.secret == "omi_dev_secret_dev-1")
        #expect(store.apiKeys.map(\.name) == ["Zapier"])
        #expect(store.apiKeys.first?.secret == nil)
        #expect(api.devApps.log.first?.hasSuffix(DeveloperStore.fullAccessScopes.joined(separator: ",")) == true)
        #expect(await store.createKey(.mcp, name: "Claude"))
        #expect(api.devApps.log.last == "create:mcp:Claude:-")
        await store.revoke(.api, id: "dev-1")
        #expect(store.apiKeys.isEmpty)
        #expect(api.devApps.keys[.api]?.isEmpty == true)
        #expect(await !store.createKey(.api, name: "   "))
    }

    @Test func mcpConfigNamesTheServerAndKey() {
        let config = make().mcpConfig(key: "omi_mcp_abc")
        #expect(config.contains("\"url\": \"https://api.omi.me/v1/mcp\""))
        #expect(config.contains("Bearer omi_mcp_abc"))
        let object = try? JSONSerialization.jsonObject(with: Data(config.utf8)) as? [String: Any]
        #expect(object?["mcpServers"] != nil)
    }

    @Test func switchesPersist() {
        let prefs = freshPreferences()
        let store = DeveloperStore(api: api, preferences: prefs, apiBaseURL: URL(string: "https://api.omi.me")!)
        store.isDeveloperMode = true
        store.vadGate = true
        let again = DeveloperStore(api: api, preferences: prefs, apiBaseURL: URL(string: "https://api.omi.me")!)
        #expect(again.isDeveloperMode && again.vadGate && !again.showsConversationTools)
    }

    @Test func logKeepsTheNewestEntriesAndFormatsThem() {
        let directory = FileManager.default.temporaryDirectory.appending(path: "log-\(UUID().uuidString)")
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let prefs = freshPreferences()
        let log = DebugLog(preferences: prefs, directory: directory, capacity: 3)
        log.writesToFile = true
        for index in 1 ... 5 {
            log.add(.info, index.isMultiple(of: 2) ? "stt" : "sync", "event \(index)")
        }
        #expect(log.entries.map(\.message) == ["event 3", "event 4", "event 5"])
        #expect(log.entries(from: "stt").map(\.message) == ["event 4"])
        #expect(DebugLog.text(log.entries(from: "stt")).contains("[INFO]"))
        #expect(log.files.count == 1)
        #expect(prefs.bool(.devLogsToFileEnabled))
        log.clear()
        #expect(log.files.isEmpty && log.entries.isEmpty)
    }
}
