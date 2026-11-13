import Foundation
@testable import OmiPersistence
import Testing

struct PreferencesTests {
    func makeDefaults() -> UserDefaults {
        let name = "omi.tests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: name)!
        defaults.removePersistentDomain(forName: name)
        return defaults
    }

    /// Exactly what the Flutter build left on disk in the P1 migration test.
    @Test func readsFlutterWrittenState() {
        let defaults = makeDefaults()
        defaults.set("local-dev-user", forKey: "flutter.uid")
        defaults.set("local-dev-user@local.test", forKey: "flutter.email")
        defaults.set("Ada", forKey: "flutter.givenName")
        defaults.set("", forKey: "flutter.familyName")
        defaults.set("en", forKey: "flutter.app_locale")
        defaults.set(true, forKey: "flutter.hasSetPrimaryLanguage")

        let prefs = Preferences(defaults: defaults)
        #expect(prefs.hasLegacyFlutterState)
        #expect(prefs.string(.uid) == "local-dev-user")
        #expect(prefs.string(.appLocale) == "en")
        #expect(prefs.string(.familyName) == nil)
        #expect(prefs.displayName == "Ada")
        #expect(prefs.bool(.onboardingCompleted) == false)
    }

    @Test func writesUnderFlutterKeys() {
        let defaults = makeDefaults()
        let prefs = Preferences(defaults: defaults)
        prefs.set(true, for: .onboardingCompleted)
        #expect(defaults.bool(forKey: "flutter.onboardingCompleted"))
    }

    @Test func signOutKeepsExactlyTheFlutterKeepList() {
        let defaults = makeDefaults()
        let prefs = Preferences(defaults: defaults)
        prefs.set("u1", for: .uid)
        prefs.set(true, for: .aiConsentGiven)
        prefs.set(#"{"id":"x","name":"Omi"}"#, for: .btDevice)
        defaults.set("dark", forKey: "flutter.appearanceMode")
        defaults.set("something", forKey: "flutter.cachedConversations")
        prefs.clearUser()
        #expect(prefs.string(.uid) == nil)
        #expect(!prefs.bool(.aiConsentGiven))
        #expect(defaults.string(forKey: "flutter.cachedConversations") == nil)
        #expect(prefs.string(.btDevice) != nil)
        #expect(defaults.string(forKey: "flutter.appearanceMode") == "dark")
    }
}
