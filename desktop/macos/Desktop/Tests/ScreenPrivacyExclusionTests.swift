import XCTest
@testable import Omi_Computer

/// Verifies that Rewind privacy exclusions (password managers, keychains) are respected
/// by all proactive assistants — not just the Rewind indexer.
/// See: https://github.com/BasedHardware/omi/issues/7098
final class ScreenPrivacyExclusionTests: XCTestCase {

    // MARK: - Rewind default excluded apps include privacy-sensitive apps

    func testRewindDefaultsIncludePasswordManagers() {
        let defaults = RewindSettings.defaultExcludedApps
        let privacyApps = ["Passwords", "1Password", "1Password 7", "Bitwarden",
                           "LastPass", "Dashlane", "Keeper", "Enpass",
                           "KeePassXC", "Keychain Access"]
        for app in privacyApps {
            XCTAssertTrue(defaults.contains(app), "RewindSettings.defaultExcludedApps must include '\(app)'")
        }
    }

    // MARK: - Each assistant's isAppExcluded respects Rewind exclusions

    @MainActor
    func testMemorySettingsExcludesRewindPrivacyApps() {
        let settings = MemoryAssistantSettings.shared
        XCTAssertTrue(settings.isAppExcluded("1Password"),
                      "MemoryAssistantSettings must exclude Rewind privacy app '1Password'")
        XCTAssertTrue(settings.isAppExcluded("Keychain Access"),
                      "MemoryAssistantSettings must exclude Rewind privacy app 'Keychain Access'")
        XCTAssertTrue(settings.isAppExcluded("Passwords"),
                      "MemoryAssistantSettings must exclude Rewind privacy app 'Passwords'")
    }

    @MainActor
    func testInsightSettingsExcludesRewindPrivacyApps() {
        let settings = InsightAssistantSettings.shared
        XCTAssertTrue(settings.isAppExcluded("1Password"),
                      "InsightAssistantSettings must exclude Rewind privacy app '1Password'")
        XCTAssertTrue(settings.isAppExcluded("Keychain Access"),
                      "InsightAssistantSettings must exclude Rewind privacy app 'Keychain Access'")
        XCTAssertTrue(settings.isAppExcluded("Bitwarden"),
                      "InsightAssistantSettings must exclude Rewind privacy app 'Bitwarden'")
    }

    @MainActor
    func testFocusSettingsExcludesRewindPrivacyApps() {
        let settings = FocusAssistantSettings.shared
        XCTAssertTrue(settings.isAppExcluded("1Password"),
                      "FocusAssistantSettings must exclude Rewind privacy app '1Password'")
        XCTAssertTrue(settings.isAppExcluded("Keychain Access"),
                      "FocusAssistantSettings must exclude Rewind privacy app 'Keychain Access'")
        XCTAssertTrue(settings.isAppExcluded("LastPass"),
                      "FocusAssistantSettings must exclude Rewind privacy app 'LastPass'")
    }

    // MARK: - Built-in excluded apps still work

    @MainActor
    func testBuiltInExclusionsStillWork() {
        // Verify that the original built-in exclusions (system/utility apps) are still respected
        XCTAssertTrue(MemoryAssistantSettings.shared.isAppExcluded("Finder"))
        XCTAssertTrue(InsightAssistantSettings.shared.isAppExcluded("Calculator"))
        XCTAssertTrue(FocusAssistantSettings.shared.isAppExcluded("Activity Monitor"))
    }

    // MARK: - Non-excluded apps are not blocked

    @MainActor
    func testNonExcludedAppsPassThrough() {
        // Regular productivity apps should not be excluded
        XCTAssertFalse(MemoryAssistantSettings.shared.isAppExcluded("Safari"))
        XCTAssertFalse(InsightAssistantSettings.shared.isAppExcluded("Slack"))
        XCTAssertFalse(FocusAssistantSettings.shared.isAppExcluded("Xcode"))
    }

    // MARK: - Custom user-added Rewind exclusions propagate to assistants

    @MainActor
    func testCustomRewindExclusionBlocksAllAssistants() {
        let customApp = "TestCustomPrivateApp_\(UUID().uuidString)"
        // Add a custom exclusion to Rewind
        RewindSettings.shared.excludeApp(customApp)
        defer { RewindSettings.shared.includeApp(customApp) }

        // All assistants must block this custom-excluded app
        XCTAssertTrue(RewindSettings.shared.isAppExcluded(customApp),
                      "RewindSettings must exclude custom app")
        XCTAssertTrue(MemoryAssistantSettings.shared.isAppExcluded(customApp),
                      "MemoryAssistantSettings must block custom Rewind-excluded app")
        XCTAssertTrue(InsightAssistantSettings.shared.isAppExcluded(customApp),
                      "InsightAssistantSettings must block custom Rewind-excluded app")
        XCTAssertTrue(FocusAssistantSettings.shared.isAppExcluded(customApp),
                      "FocusAssistantSettings must block custom Rewind-excluded app")
    }

    // MARK: - RewindSettings.isAppExcluded covers all default privacy apps

    func testRewindSettingsExcludesAllDefaultPrivacyApps() {
        let privacyApps = ["Passwords", "1Password", "1Password 7", "Bitwarden",
                           "LastPass", "Dashlane", "Keeper", "Enpass",
                           "KeePassXC", "Keychain Access"]
        for app in privacyApps {
            XCTAssertTrue(RewindSettings.shared.isAppExcluded(app),
                          "RewindSettings.shared.isAppExcluded must return true for '\(app)'")
        }
    }
}
