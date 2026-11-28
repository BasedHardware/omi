import Foundation
import OmiNetwork
import OmiPersistence
@testable import OmiService
import OmiTestSupport
import Testing

/// The top of Settings (profile header, the four tiles) and My Omi's status line.
@MainActor
struct SettingsHubTests {
    @Test func initialsComeFromTheNameThenTheEmail() {
        #expect(SettingsHub.initials(name: "Ada Lovelace", email: "ada@example.com") == "AL")
        #expect(SettingsHub.initials(name: "  ada  ", email: nil) == "A")
        #expect(SettingsHub.initials(name: "Jean-Luc Picard", email: nil) == "JL")
        // No name: the email's first letter, never a placeholder word's.
        #expect(SettingsHub.initials(name: nil, email: "ada@example.com") == "A")
        #expect(SettingsHub.initials(name: "", email: "1ada@example.com") == "A")
        #expect(SettingsHub.initials(name: nil, email: nil) == "?")
    }

    @Test func headlineFallsBackToTheEmailsName() {
        #expect(SettingsHub.headline(name: "Ada Lovelace", email: "x@y.z") == "Ada Lovelace")
        #expect(SettingsHub.headline(name: " ", email: "ada@example.com") == "ada")
        #expect(SettingsHub.headline(name: nil, email: nil) == nil)
    }

    @Test func omiStateFollowsTheConnection() {
        #expect(SettingsHub.omiState(isPaired: false, connection: .connected, battery: 50, isMuted: false, isListening: true) == .none)
        let away = SettingsHub.omiState(isPaired: true, connection: .disconnected, battery: 50, isMuted: false, isListening: false)
        #expect(away == .notConnected)
        #expect(away.dot == .off)
        #expect(away.battery == nil)
        let live = SettingsHub.omiState(isPaired: true, connection: .connected, battery: 76, isMuted: false, isListening: true)
        #expect(live == .connected(battery: 76, activity: .listening))
        #expect(live.dot == .live)
        #expect(live.battery == 76)
        // Paused wins over listening: the Omi sends nothing.
        let paused = SettingsHub.omiState(isPaired: true, connection: .connected, battery: 76, isMuted: true, isListening: true)
        #expect(paused == .connected(battery: 76, activity: .paused))
        #expect(paused.dot == .connected)
        let connecting = SettingsHub.omiState(isPaired: true, connection: .connecting, battery: nil, isMuted: false, isListening: false)
        #expect(connecting == .connecting)
    }

    @Test func busiestMeterSkipsUnlimited() {
        let meters = [
            UsageMeter(kind: .listening, used: 100, limit: 1000),
            UsageMeter(kind: .chat, used: 31, limit: 50),
            UsageMeter(kind: .words, used: 9999, limit: nil),
        ]
        #expect(SettingsHub.busiestMeter(meters)?.kind == .chat)
        #expect(SettingsHub.busiestMeter([UsageMeter(kind: .listening, used: 5, limit: nil)]) == nil)
        #expect(SettingsHub.percent(0.62) == 62)
        // Nearly full is not full: 100 % only at the limit.
        #expect(SettingsHub.percent(0.997) == 99)
        #expect(SettingsHub.percent(1) == 100)
        #expect(SettingsHub.percent(0) == 0)
    }

    @Test func connectedAppsCountHealthAndReminders() {
        let integrations = [
            Integration(id: "gmail", kind: .integration, isConnected: true),
            Integration(id: "todoist", kind: .taskApp, isConnected: true),
            Integration(id: "asana", kind: .taskApp, isConnected: false),
        ]
        #expect(SettingsHub.connectedApps(integrations, health: false, reminders: false) == 2)
        #expect(SettingsHub.connectedApps(integrations, health: true, reminders: true) == 4)
        #expect(SettingsHub.connectedApps([], health: false, reminders: false) == 0)
    }

    /// The backend's name wins over the one saved on this iPhone; a rename shows at once.
    @Test func profileNameFromTheBackend() async {
        let api = FakeAPIClient()
        let prefs = freshPreferences()
        prefs.set("Alex", for: .givenName)
        let settings = SettingsStore(api: api, preferences: prefs)
        #expect(settings.displayName == "Alex")
        api.accountData.profile = UserProfile(name: "Ada Lovelace", email: "ada@example.com")
        await settings.loadProfile()
        #expect(settings.displayName == "Ada Lovelace")
        #expect(settings.email == "ada@example.com")
        settings.nameChanged(to: " Ada ")
        #expect(settings.displayName == "Ada")
        // A backend without a name keeps the saved one.
        let empty = SettingsStore(api: FakeAPIClient(), preferences: prefs)
        await empty.loadProfile()
        #expect(empty.displayName == "Alex")
    }
}
