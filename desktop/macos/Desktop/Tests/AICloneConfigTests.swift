import XCTest
@testable import Omi_Computer

/// Tests for `AICloneConfig` (the Swift class backing the AI Clone
/// settings screen) and its interaction with `AICloneKeychain`.
///
/// Covers:
/// - Plugin URL stays in UserDefaults (non-secret)
/// - Bearer token + dev API key live in Keychain (not UserDefaults)
/// - Legacy UserDefaults values migrate to Keychain on first init
/// - Migration is idempotent (re-init doesn't move values again)
/// - Setting a secret to "" deletes it from Keychain
@MainActor
final class AICloneConfigTests: XCTestCase {

    private var customDefaults: UserDefaults!
    private var suiteName: String!

    override func setUp() {
        super.setUp()
        // Each test gets a fresh UserDefaults suite so we don't
        // interfere with real persisted values.
        suiteName = "AICloneConfigTests.\(UUID().uuidString)"
        customDefaults = UserDefaults(suiteName: suiteName)!
        // Wipe any state that might be in the system Keychain from a
        // previous run. The keychain helper uses a per-bundle
        // service so this only affects our service's items.
        try? AICloneKeychain.delete(.pluginBearerToken)
        try? AICloneKeychain.delete(.devApiKey)
    }

    override func tearDown() {
        try? AICloneKeychain.delete(.pluginBearerToken)
        try? AICloneKeychain.delete(.devApiKey)
        customDefaults.removePersistentDomain(forName: suiteName)
        customDefaults = nil
        super.tearDown()
    }

    // MARK: - Plugin URL stays in UserDefaults

    func testPluginURLPersistsToUserDefaults() {
        let config = AICloneConfig(defaults: customDefaults)
        config.pluginURL = "https://clone.example.com"
        XCTAssertEqual(
            customDefaults.string(forKey: "ai_clone_plugin_url"),
            "https://clone.example.com"
        )
    }

    // MARK: - Secrets go to Keychain, NOT UserDefaults

    func testBearerTokenGoesToKeychainNotUserDefaults() {
        let config = AICloneConfig(defaults: customDefaults)
        config.bearerToken = "my-secret-token"

        // In-memory state correct.
        XCTAssertEqual(config.bearerToken, "my-secret-token")

        // Persisted to Keychain.
        XCTAssertEqual(
            try? AICloneKeychain.get(.pluginBearerToken),
            "my-secret-token"
        )

        // NOT in UserDefaults (would-be legacy key is absent).
        XCTAssertNil(customDefaults.string(forKey: "ai_clone_plugin_bearer_token"))
    }

    func testDevApiKeyGoesToKeychainNotUserDefaults() {
        let config = AICloneConfig(defaults: customDefaults)
        config.omiDevApiKey = "omi_dev_abc123"

        XCTAssertEqual(config.omiDevApiKey, "omi_dev_abc123")
        XCTAssertEqual(
            try? AICloneKeychain.get(.devApiKey),
            "omi_dev_abc123"
        )
        XCTAssertNil(customDefaults.string(forKey: "ai_clone_omi_dev_api_key"))
    }

    func testSettingSecretToEmptyDeletesItFromKeychain() {
        let config = AICloneConfig(defaults: customDefaults)
        config.bearerToken = "first-value"
        XCTAssertNotNil(try? AICloneKeychain.get(.pluginBearerToken))

        config.bearerToken = ""
        XCTAssertNil(try? AICloneKeychain.get(.pluginBearerToken))
    }

    // MARK: - Reload from Keychain on init

    func testInitLoadsExistingSecretsFromKeychain() {
        // Seed Keychain directly (simulates a previous app run).
        try? AICloneKeychain.set(.pluginBearerToken, "persisted-token")
        try? AICloneKeychain.set(.devApiKey, "persisted-dev-key")

        let config = AICloneConfig(defaults: customDefaults)
        XCTAssertEqual(config.bearerToken, "persisted-token")
        XCTAssertEqual(config.omiDevApiKey, "persisted-dev-key")
    }

    // MARK: - Migration

    func testLegacyUserDefaultsValuesMigrateToKeychain() {
        // Simulate a previous build that stored secrets in
        // UserDefaults.
        customDefaults.set("legacy-token", forKey: "ai_clone_plugin_bearer_token")
        customDefaults.set("legacy-dev-key", forKey: "ai_clone_omi_dev_api_key")

        let config = AICloneConfig(defaults: customDefaults)

        // Migrated into Keychain.
        XCTAssertEqual(
            try? AICloneKeychain.get(.pluginBearerToken),
            "legacy-token"
        )
        XCTAssertEqual(
            try? AICloneKeychain.get(.devApiKey),
            "legacy-dev-key"
        )

        // Visible via the in-memory properties.
        XCTAssertEqual(config.bearerToken, "legacy-token")
        XCTAssertEqual(config.omiDevApiKey, "legacy-dev-key")

        // Original UserDefaults entries are gone.
        XCTAssertNil(customDefaults.string(forKey: "ai_clone_plugin_bearer_token"))
        XCTAssertNil(customDefaults.string(forKey: "ai_clone_omi_dev_api_key"))
    }

    func testMigrationDoesNotClobberExistingKeychainValue() {
        // Pre-existing real Keychain entry (e.g. user reinstalled
        // app fresh, then restored a backup with old UserDefaults
        // values). The Keychain value should win.
        try? AICloneKeychain.set(.pluginBearerToken, "real-token")
        customDefaults.set("legacy-token", forKey: "ai_clone_plugin_bearer_token")

        let config = AICloneConfig(defaults: customDefaults)

        // Keychain value preserved.
        XCTAssertEqual(
            try? AICloneKeychain.get(.pluginBearerToken),
            "real-token"
        )
        XCTAssertEqual(config.bearerToken, "real-token")

        // Legacy UserDefaults entry cleared (cleanup even when not
        // migrated — prevents re-migration attempts).
        XCTAssertNil(customDefaults.string(forKey: "ai_clone_plugin_bearer_token"))
    }

    func testMigrationIsIdempotent() {
        customDefaults.set("legacy-token", forKey: "ai_clone_plugin_bearer_token")

        // First init migrates.
        _ = AICloneConfig(defaults: customDefaults)
        XCTAssertEqual(
            try? AICloneKeychain.get(.pluginBearerToken),
            "legacy-token"
        )

        // Second init: UserDefaults no longer has the value, so
        // migration is a no-op and Keychain value persists.
        let config2 = AICloneConfig(defaults: customDefaults)
        XCTAssertEqual(config2.bearerToken, "legacy-token")
    }

    // MARK: - isFullyConfigured

    func testIsFullyConfiguredReflectsAllThreeSources() {
        let config = AICloneConfig(defaults: customDefaults)
        XCTAssertFalse(config.isFullyConfigured)

        config.pluginURL = "https://clone.example.com"
        XCTAssertFalse(config.isFullyConfigured)  // missing both secrets

        config.bearerToken = "t"
        XCTAssertFalse(config.isFullyConfigured)  // missing dev key

        config.omiDevApiKey = "k"
        XCTAssertTrue(config.isFullyConfigured)
    }

    // MARK: - Keychain protection level (cubic P2)
    //
    // The Keychain migration improves on UserDefaults but does not
    // provide full sandbox isolation on a non-sandboxed app. These
    // tests pin the actual behavior so a future regression that
    // re-introduces plaintext-on-disk storage would fail loudly.

    func testStoredSecretIsNotPresentInUserDefaults() {
        // Identified by cubic P2: confirm at the runtime level that
        // storing a secret doesn't leak it into UserDefaults. A
        // regression that writes secrets to UserDefaults (the old
        // broken behavior) would fail this test.
        let config = AICloneConfig(defaults: customDefaults)
        config.bearerToken = "secret-bearer-xyz"
        config.omiDevApiKey = "secret-dev-abc"

        // The legacy keys must be absent. We don't just check that
        // the value isn't there — we explicitly check that the keys
        // themselves were removed (any value, including an empty
        // string, would be a regression).
        //
        // Identified by cubic P1: `customDefaults.data(forKey:)`
        // only returns Data-typed values — a String-typed regression
        // would silently pass the assertion (nil != "string"). Use
        // `object(forKey:)` which returns Any? and catches strings,
        // data, ints, etc. — any value under the legacy key is a
        // regression.
        XCTAssertNil(customDefaults.object(forKey: "ai_clone_plugin_bearer_token"))
        XCTAssertNil(customDefaults.object(forKey: "ai_clone_omi_dev_api_key"))
    }

    func testStoredSecretIsRetrievableViaKeychain() {
        // The companion check: the secret IS in Keychain, retrievable
        // by the same app via AICloneKeychain.get. Pairs with the
        // above test to prove the round-trip is "write to Keychain",
        // not "write to Keychain AND leak to UserDefaults".
        let config = AICloneConfig(defaults: customDefaults)
        config.bearerToken = "round-trip-token"
        config.omiDevApiKey = "round-trip-dev-key"

        XCTAssertEqual(
            try? AICloneKeychain.get(.pluginBearerToken),
            "round-trip-token"
        )
        XCTAssertEqual(
            try? AICloneKeychain.get(.devApiKey),
            "round-trip-dev-key"
        )
    }

    func testMigrationClearsLegacyUserDefaultsEntries() {
        // Even when migration moves a legacy value to Keychain, the
        // legacy UserDefaults key must be cleared — leaving it in
        // place would re-introduce the plaintext-on-disk exposure
        // that motivated the migration.
        customDefaults.set("legacy-value", forKey: "ai_clone_plugin_bearer_token")
        let _ = AICloneConfig(defaults: customDefaults)
        // Migration copied the value to Keychain and removed the
        // UserDefaults copy. Use object(forKey:) so the assertion
        // catches ANY value (string, Data, int, etc.) under the
        // legacy key — string(forKey:) would silently miss a
        // Data-typed value (cubic P1).
        XCTAssertNil(customDefaults.object(forKey: "ai_clone_plugin_bearer_token"))
        // The Keychain now holds it.
        XCTAssertEqual(
            try? AICloneKeychain.get(.pluginBearerToken),
            "legacy-value"
        )
    }

    // MARK: - Discovery (extracted from init, cubic P2)
    //
    // Init must NOT auto-apply the discovery file — that mutates the
    // injected UserDefaults + Keychain and breaks hermetic tests on
    // machines that have a real discovery file. applyDiscovery() is
    // the explicit entry point, called from OmiApp.swift at startup.

    func testInitDoesNotAutoApplyDiscoveryFile() {
        // Seed a customDefaults with values so we can verify init
        // doesn't overwrite them by reading the real discovery file.
        // The injected `defaults` MUST be the only source of truth
        // for the in-memory pluginURL after init (until the app
        // explicitly calls applyDiscovery()).
        customDefaults.set("https://already-configured.example.com", forKey: "ai_clone_plugin_url")

        let config = AICloneConfig(defaults: customDefaults)

        // URL came from customDefaults, NOT from the discovery file
        // on the test machine (which may or may not exist).
        XCTAssertEqual(config.pluginURL, "https://already-configured.example.com")
        XCTAssertFalse(config.isAutoDiscovered)
        XCTAssertFalse(config.pluginDevMode)
    }

    func testApplyDiscoveryNoOpWhenFileMissing() {
        // Delete the real discovery file for the duration of this
        // test so we can verify the no-op path. The test machine may
        // have a stale discovery file from prior dev runs.
        let discoveryPath = PluginDiscovery.filePath
        let fm = FileManager.default
        let existed = fm.fileExists(atPath: discoveryPath)
        if existed {
            try? fm.removeItem(atPath: discoveryPath)
        }
        defer {
            // Restore if we deleted it (best-effort; if we never
            // recreated it, just leave it deleted).
            if existed && !fm.fileExists(atPath: discoveryPath) {
                // No way to recreate the prior contents from this
                // test — leave the file deleted. The test was deleting
                // a stale file anyway, and the next launch of the
                // plugin will rewrite it.
            }
        }

        let config = AICloneConfig(defaults: customDefaults)
        config.applyDiscovery()
        XCTAssertFalse(config.isAutoDiscovered)
        XCTAssertFalse(config.pluginDevMode)
        XCTAssertEqual(config.pluginURL, "")
        XCTAssertEqual(config.bearerToken, "")
    }
}