import Foundation
import OmiCore
import OmiNetwork
import OmiPersistence
@testable import OmiService
import OmiTestSupport
import Testing

@MainActor
struct OnboardingStoreTests {
    @Test func walksTheStepsAndPersists() async {
        let api = FakeAPIClient()
        let prefs = freshPreferences(onboarded: false)
        var displayName: String?
        let onboarding = OnboardingStore(api: api, preferences: prefs, updateDisplayName: { displayName = $0 })
        onboarding.givenName = "Ada Lovelace"
        await onboarding.saveName()
        #expect(prefs.string(.givenName) == "Ada")
        #expect(prefs.string(.familyName) == "Lovelace")
        #expect(displayName == "Ada Lovelace")
        #expect(onboarding.step == .language)
        // Nothing is preselected.
        #expect(onboarding.spokenLanguages.isEmpty)
        onboarding.toggleLanguage("de")
        await onboarding.saveLanguage()
        #expect(prefs.string(.userPrimaryLanguage) == "de")
        onboarding.saveSource("Podcast")
        try? await Task.sleep(for: .milliseconds(20))
        #expect(api.accountLog.contains("language:de"))
        #expect(api.accountLog.contains("onboarding:-:Podcast"))
        #expect(onboarding.step == .hasOmi)
    }

    /// The order of the taps is the order of importance; a second tap takes a language out and
    /// the ones after it move up.
    @Test func tapOrderIsPriority() async {
        let onboarding = OnboardingStore(api: FakeAPIClient(), preferences: freshPreferences(onboarded: false), updateDisplayName: { _ in })
        await onboarding.loadLanguages()
        #expect(onboarding.spokenLanguages.isEmpty)
        onboarding.toggleLanguage("es")
        onboarding.toggleLanguage("en")
        onboarding.toggleLanguage("de")
        #expect(onboarding.language == "es")
        #expect(onboarding.rank(of: "de") == 3)
        onboarding.toggleLanguage("es")
        #expect(onboarding.spokenLanguages == ["en", "de"])
        #expect(onboarding.language == "en")
        #expect(onboarding.rank(of: "en") == 1)
        #expect(onboarding.rank(of: "es") == nil)
    }

    /// The short list shows the common languages; a language found by searching stays visible
    /// once picked, and an unknown saved code too.
    @Test func searchedPicksStayInTheList() async {
        let onboarding = OnboardingStore(api: FakeAPIClient(), preferences: freshPreferences(onboarded: false), updateDisplayName: { _ in })
        await onboarding.loadLanguages()
        let common = onboarding.commonLanguages.map(\.code)
        #expect(Set(common) == ["en", "de", "es"])
        #expect(onboarding.languageRows().map(\.code) == common)
        #expect(onboarding.languageRows(matching: "germ").map(\.code) == ["de"])
        #expect(onboarding.languageRows(matching: "ES").map(\.code) == ["es"])
        onboarding.toggleLanguage("xx")
        #expect(onboarding.languageRows().map(\.code) == ["xx"] + common)
    }
}

@MainActor
struct CapabilitiesStoreTests {
    @Test func loadsConnectionState() async {
        let api = FakeAPIClient()
        api.connectedIntegrations = ["google_calendar", "todoist"]
        let store = CapabilitiesStore(api: api)
        await store.load()
        #expect(store.connectedCount == 2)
        await store.disconnect(store.integrations[0])
        #expect(store.connectedCount == 1)
    }

    @Test func connectFailuresAreNamedNotSwallowed() async {
        let api = FakeAPIClient()
        let store = CapabilitiesStore(api: api)
        let calendar = store.integrations[0]
        api.oauthURLError = .http(status: 500, body: #"{"detail":"Google Calendar not configured - GOOGLE_CLIENT_ID missing"}"#)
        #expect(await store.authorizationURL(for: calendar) == nil)
        #expect(store.failures[calendar.id] == .notConfigured)
        api.oauthURLError = .transport("offline")
        #expect(await store.authorizationURL(for: calendar) == nil)
        #expect(store.failures[calendar.id] == .offline)
        api.oauthURLError = .http(status: 500, body: "boom")
        #expect(await store.authorizationURL(for: calendar) == nil)
        #expect(store.failures[calendar.id] == .failed)
        // Trying again clears it; a closed login page says why.
        api.oauthURLError = nil
        #expect(await store.authorizationURL(for: calendar) != nil)
        #expect(store.failures[calendar.id] == nil)
        store.loginEnded(calendar, cancelled: true)
        #expect(store.failures[calendar.id] == .cancelled)
        store.loginEnded(calendar, cancelled: false)
        #expect(store.failures[calendar.id] == .failed)
        // Connecting after all clears the message.
        api.connectedIntegrations.insert(calendar.id)
        await store.load()
        #expect(store.failures[calendar.id] == nil)
    }
}

@MainActor
struct SettingsStoreTests {
    @Test func settingsRoundTrip() async {
        let api = FakeAPIClient()
        let settings = SettingsStore(api: api, preferences: freshPreferences())
        await settings.loadSubscription()
        #expect(settings.subscription?.secondsLimit == 18000)
        await settings.setDailySummary(enabled: false, hour: 20)
        await settings.selectVoice("Puck")
        await settings.addWord("Omi")
        await settings.addWord("Anthropic")
        await settings.addPerson("Anna")
        await settings.removeWords(at: [0])
        #expect(settings.people.map(\.name) == ["Anna"])
        #expect(settings.vocabulary == ["Anthropic"])
        #expect(api.settingsLog == ["daily:false:20", "voice:Puck", "vocabulary:Omi", "vocabulary:Omi,Anthropic", "vocabulary:Anthropic"])
    }

    @Test func failedToggleRollsBack() async {
        let api = FakeAPIClient()
        let settings = SettingsStore(api: api, preferences: freshPreferences())
        api.fail(with: .http(status: 500, body: ""))
        await settings.setStoresRecordings(true)
        #expect(!settings.storesRecordings)
        #expect(settings.lastError != nil)
    }
}

@MainActor
struct AppsTests {
    @Test func installAndUninstall() async {
        let api = FakeAPIClient()
        let store = CapabilitiesStore(api: api)
        await store.loadApps()
        #expect(store.installedApps.map(\.id) == ["a1"])
        await store.setApp(store.discoveredApps[1], enabled: true)
        #expect(store.installedApps.map(\.id) == ["a1", "a2"])
        api.fail(with: .http(status: 500, body: ""))
        await store.setApp(store.discoveredApps[0], enabled: false)
        #expect(store.installedApps.contains { $0.id == "a1" })
    }
}
