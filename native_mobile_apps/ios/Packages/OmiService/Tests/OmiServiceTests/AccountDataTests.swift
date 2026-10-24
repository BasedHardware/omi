import Foundation
import OmiCore
import OmiNetwork
import OmiPersistence
@testable import OmiService
import OmiTestSupport
import Testing

@MainActor
struct AccountDataTests {
    func defaults() -> UserDefaults {
        let suite = "omi.test.\(UUID().uuidString)"
        return UserDefaults(suiteName: suite)!
    }

    @Test func usageLoadsEachPeriodAndFairUse() async {
        let api = FakeAPIClient()
        let store = UsageStore(api: api, timeZone: "Europe/Berlin")
        await store.load()
        #expect(store.current?.totals.words == 2400)
        await store.load(.allTime)
        #expect(store.stats[.allTime]?.totals.isEmpty == true)
        await store.loadFairUse()
        #expect(store.fairUse?.stage == "none")
        #expect(api.accountData.log == ["usage:monthly", "usage:all_time", "fair-use"])

        api.accountData.failing = ["usage"]
        await store.load(.today)
        #expect(store.failedPeriods == [.today])
    }

    @Test func exportsToAFileAndCleansUpAfterSharing() async throws {
        let api = FakeAPIClient()
        let store = ProfileStore(api: api, defaults: defaults())
        store.export()
        #expect(store.exportPhase == .exporting)
        while store.exportPhase == .exporting {
            try await Task.sleep(for: .milliseconds(5))
        }
        guard case let .ready(url) = store.exportPhase else {
            Issue.record("export did not finish")
            return
        }
        #expect(url.lastPathComponent == "omi-export.json")
        #expect(FileManager.default.fileExists(atPath: url.path))
        store.finishExport()
        #expect(!FileManager.default.fileExists(atPath: url.path))
        #expect(store.exportPhase == .idle)
    }

    @Test func exportFailureIsShown() async throws {
        let api = FakeAPIClient()
        api.accountData.failing = ["export"]
        let store = ProfileStore(api: api, defaults: defaults())
        store.export()
        while store.exportPhase == .exporting {
            try await Task.sleep(for: .milliseconds(5))
        }
        #expect(store.exportPhase == .failed)
    }

    @Test func referralAppsAudioToggleAndCancel() async {
        let api = FakeAPIClient()
        let defaults = defaults()
        let store = ProfileStore(api: api, defaults: defaults)
        await store.loadReferral()
        #expect(store.referralURL?.absoluteString == "https://omi.me/r/ref-test")
        await store.loadAppsWithAccess()
        #expect(store.appsWithAccess?.map(\.name) == ["Zapier"])

        #expect(!store.storesAudioOnPhone)
        store.storesAudioOnPhone = true
        #expect(defaults.bool(forKey: "flutter.unlimitedLocalStorageEnabled"))
        #expect(ProfileStore(api: api, defaults: defaults).storesAudioOnPhone)

        #expect(await store.cancelSubscription(reason: "too_expensive", details: "  "))
        api.accountData.failing = ["cancel"]
        #expect(!(await store.cancelSubscription(reason: nil, details: nil)))
        #expect(store.lastError != nil)
        #expect(api.accountData.log.suffix(2) == ["cancel:too_expensive", "cancel:-"])
    }

    @Test func importUploadsAZipAndPollsUntilTheJobFinishes() async throws {
        let api = FakeAPIClient()
        let store = ImportStore(api: api, pollInterval: .milliseconds(20))
        await store.load()
        #expect(store.phase == .loaded)
        let zip = FileManager.default.temporaryDirectory.appending(path: "limitless-\(UUID().uuidString).zip")
        try Data("PK".utf8).write(to: zip)
        defer { try? FileManager.default.removeItem(at: zip) }

        #expect(await store.importZip(at: zip, language: "en"))
        #expect(store.jobs.first?.status == .pending)
        #expect(store.hasRunningJob)
        api.accountData.importJobs = [ImportJob(id: "job-1", status: .completed, totalFiles: 10, processedFiles: 10, created: 4)]
        while store.hasRunningJob {
            try await Task.sleep(for: .milliseconds(10))
        }
        #expect(store.jobs.first?.created == 4)
        await store.delete("job-1")
        #expect(store.jobs.isEmpty)
        store.stopPolling()
    }

    @Test func importRefusesWhatIsNotAZip() async throws {
        let store = ImportStore(api: FakeAPIClient())
        let text = FileManager.default.temporaryDirectory.appending(path: "notes-\(UUID().uuidString).txt")
        try Data("x".utf8).write(to: text)
        defer { try? FileManager.default.removeItem(at: text) }
        #expect(!(await store.importZip(at: text, language: "en")))
        #expect(store.lastError == "unreadable")
    }

    @Test func changeNameSplitsGivenAndFamily() async {
        let auth = NameRecordingAuth()
        let preferences = Preferences(defaults: defaults())
        let session = SessionStore(
            auth: auth, api: FakeAPIClient(),
            configuration: AppConfiguration(
                profile: .localDev, apiBaseURL: URL(string: "http://127.0.0.1:8000/")!,
                authEmulator: ("127.0.0.1", 9099), appVersion: "2.0.0", appBuild: "1"
            ),
            preferences: preferences
        )
        await session.changeName("  Ada  King Lovelace ")
        #expect(preferences.string(.givenName) == "Ada")
        #expect(preferences.string(.familyName) == "King Lovelace")
        #expect(auth.names == ["Ada  King Lovelace"])
    }
}

@MainActor
final class NameRecordingAuth: AuthServicing {
    var names: [String] = []
    var currentUserID: String? { "u1" }

    func signIn(customToken _: String) async throws -> AuthenticatedUser {
        AuthenticatedUser(uid: "u1", email: nil, displayName: nil)
    }

    func signIn(with _: ProviderCredential) async throws -> AuthenticatedUser {
        AuthenticatedUser(uid: "u1", email: nil, displayName: nil)
    }

    func updateDisplayName(_ name: String) async throws {
        names.append(name)
    }

    func signOut() throws {}
}
