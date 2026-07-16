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

    // MARK: - Telegram user-session (plan §7)

    func testTelegramUserSessionGoesToKeychainNotUserDefaults() {
        // The Telethon session string is a fully-compromising identity
        // secret. It must NEVER land in UserDefaults (plaintext on
        // disk, readable by any process as the same user). It goes
        // to Keychain (encrypted at rest, locked-screen gated).
        let config = AICloneConfig(defaults: customDefaults)
        let session = "1AgAOMT946OxqWq3" + String(repeating: "A", count: 200)
        try? config.setTelegramUserSession(session)
        XCTAssertEqual(
            try? AICloneKeychain.get(.telegramUserSession),
            session
        )
        // Pin: UserDefaults has no key for the session string. We use
        // telegramAccountEnabled (a boolean flag), not the session
        // itself, for the UserDefaults entry.
        XCTAssertNil(customDefaults.string(
            forKey: "ai_clone.telegram_user_session"
        ))
    }

    func testSettingEmptyTelegramSessionDisablesAccount() {
        // Calling setTelegramUserSession("") is the "Sign out" path.
        // It must clear the Keychain entry AND flip the enabled
        // flag off.
        let config = AICloneConfig(defaults: customDefaults)
        try? AICloneKeychain.set(
            .telegramUserSession,
            "1AgAOMT946OxqWq3" + String(repeating: "A", count: 200)
        )
        config.telegramAccountEnabled = true
        try? config.setTelegramUserSession("")
        XCTAssertNil(try? AICloneKeychain.get(.telegramUserSession))
        XCTAssertFalse(config.telegramAccountEnabled)
    }

    func testInitFlipsTelegramAccountEnabledWhenSessionInKeychain() {
        // The session in Keychain is the authoritative source of
        // truth. If the UserDefaults flag is off but the session
        // IS in Keychain, init() should flip the flag on.
        try? AICloneKeychain.set(
            .telegramUserSession,
            "1AgAOMT946OxqWq3" + String(repeating: "A", count: 200)
        )
        customDefaults.set(false, forKey: "ai_clone.telegram_user_enabled")
        let config = AICloneConfig(defaults: customDefaults)
        XCTAssertTrue(config.telegramAccountEnabled)
    }

    func testClearTelegramUserSessionRemovesIt() {
        // Happy path: session in Keychain, call clear(),
        // session should be gone.
        let config = AICloneConfig(defaults: customDefaults)
        try? AICloneKeychain.set(
            .telegramUserSession,
            "1AgAOMT946OxqWq3" + String(repeating: "A", count: 200)
        )
        config.telegramAccountEnabled = true
        try? config.clearTelegramUserSession()
        XCTAssertNil(try? AICloneKeychain.get(.telegramUserSession))
        XCTAssertFalse(config.telegramAccountEnabled)
    }

    func testSetTelegramUserSessionEmptyHappyPathDoesNotThrow() {
        // cubic review 4615559812 P1: the empty-string sign-out
        // path is `throws` so callers can handle Keychain delete
        // failures instead of masking them. This test pins the
        // happy-path contract: when there is no preexisting entry
        // to delete, the empty-string call must NOT throw.
        //
        // (Renamed from testSetTelegramUserSessionEmptyIsThrows
        // per cubic review 4615819409 P3: the original name read
        // as if it verified the call throws, but the actual
        // assertion is XCTAssertNoThrow on the happy path.)
        let config = AICloneConfig(defaults: customDefaults)
        try? AICloneKeychain.delete(.telegramUserSession)
        XCTAssertNoThrow(try config.setTelegramUserSession(""))
        XCTAssertFalse(config.telegramAccountEnabled)
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

    // MARK: - Telegram user-account ToS acknowledgement (plan §8)

    func testSetTelegramUserSessionEnablesAccount() {
        // Renamed from testTelegramUserSessionEnabledPersistsIndependentlyFromAcknowledgement
        // per cubic review 4617059500 P2: the previous name and
        // docstring claimed to verify that the ToS acknowledgement
        // flag and telegramAccountEnabled are independent concepts,
        // but the test only asserted that setting a session
        // enables the account -- it never read the acknowledgement
        // flag. The renamed test pins what the test actually
        // exercises: setTelegramUserSession(non-empty) flips
        // telegramAccountEnabled to true. The two-flag-independence
        // contract is exercised by the SwiftUI view layer (the
        // "Generate session" button is gated on
        // telegramAccountAcknowledged) -- not by a config-only
        // unit test.
        let config = AICloneConfig(defaults: customDefaults)
        XCTAssertFalse(config.telegramAccountEnabled)
        try? config.setTelegramUserSession(
            "1AgAOMT946OxqWq3" + String(repeating: "A", count: 200)
        )
        XCTAssertTrue(config.telegramAccountEnabled)
    }

    func testSetTelegramUserSessionOverwritesPreviousSession() {
        // Calling setTelegramUserSession(non-empty) twice should
        // overwrite the Keychain entry -- not append, not fail.
        // The single-slot contract: there is at most one active
        // Telethon session per AICloneConfig.
        let config = AICloneConfig(defaults: customDefaults)
        let session1 = "1AgAOMT_FIRST" + String(repeating: "A", count: 200)
        let session2 = "1AgAOMT_SECOND" + String(repeating: "B", count: 200)
        try? config.setTelegramUserSession(session1)
        XCTAssertEqual(try? AICloneKeychain.get(.telegramUserSession), session1)
        try? config.setTelegramUserSession(session2)
        XCTAssertEqual(try? AICloneKeychain.get(.telegramUserSession), session2)
    }


    // MARK: - RateLimitDisplay (plan §8)

    func testRateLimitDisplayFormatted() {
        let rl = RateLimitDisplay(maxPerHour: 30, inWindowCount: 3, isBlocked: false)
        XCTAssertEqual(rl.formatted, "3 / 30 sent this hour")
    }

    func testRateLimitDisplayIsNearCapAt80Percent() {
        // cubic review 4618627789 P2: the previous
        // `Int(Double(maxPerHour) * 0.8)` truncated toward
        // zero and produced wrong thresholds for small
        // maxPerHour values. Verify the integer math works
        // at the boundary for maxPerHour=30, AND for the
        // problematic small values.
        // maxPerHour=30, 80% = 24
        XCTAssertTrue(RateLimitDisplay(maxPerHour: 30, inWindowCount: 24).isNearCap)
        XCTAssertFalse(RateLimitDisplay(maxPerHour: 30, inWindowCount: 23).isNearCap)
        // maxPerHour=1, 80% = 0.8 -> ceil(0.8) = 1 (was 0 with
        // the buggy truncating math, which made the warning
        // permanently active at zero usage).
        XCTAssertFalse(RateLimitDisplay(maxPerHour: 1, inWindowCount: 0).isNearCap)
        XCTAssertTrue(RateLimitDisplay(maxPerHour: 1, inWindowCount: 1).isNearCap)
        // maxPerHour=2, 80% = 1.6 -> ceil(1.6) = 2 (was 1 with
        // the buggy truncating math, which fired the warning
        // at 50% rather than 80%).
        XCTAssertFalse(RateLimitDisplay(maxPerHour: 2, inWindowCount: 1).isNearCap)
        XCTAssertTrue(RateLimitDisplay(maxPerHour: 2, inWindowCount: 2).isNearCap)
        // maxPerHour=5, 80% = 4
        XCTAssertFalse(RateLimitDisplay(maxPerHour: 5, inWindowCount: 3).isNearCap)
        XCTAssertTrue(RateLimitDisplay(maxPerHour: 5, inWindowCount: 4).isNearCap)
    }

    func testRateLimitDisplayBlockedIsAlwaysNearCap() {
        // Even one send + blocked should flag as near-cap so
        // the user gets the warning. This is the cubic
        // review 4617059500 P1 protection: the local gate
        // must be visible to the user when Telegram has
        // placed a cooldown on the account.
        let rl = RateLimitDisplay(maxPerHour: 30, inWindowCount: 1, isBlocked: true, secondsUntilNextSlot: 60)
        XCTAssertTrue(rl.isNearCap)
    }

    func testRateLimitDisplayZeroMaxPerHourNotConsideredNearCap() {
        // Defensive: if the plugin reports 0 max, the percent
        // calc would be NaN. Treat 0 max as "unknown" -- not
        // near cap.
        let rl = RateLimitDisplay(maxPerHour: 0, inWindowCount: 0)
        XCTAssertFalse(rl.isNearCap)
    }

    func testAICloneConfigRateLimitStartsEmpty() {
        let config = AICloneConfig(defaults: customDefaults)
        XCTAssertEqual(config.telegramRateLimit, .empty)
        XCTAssertEqual(config.telegramMessagesSentToday, 0)
    }


    // MARK: - Sign-out clears rate-limit state (cubic 4618627789 P2)

    func testSignOutClearsRateLimitState() {
        // cubic review 4618627789 P2: sign-out must reset
        // telegramRateLimit and telegramMessagesSentToday
        // alongside telegramAccountMeta. Otherwise the UI
        // shows stale metrics from the previous account.
        let config = AICloneConfig(defaults: customDefaults)
        // Set up a "logged in" state with non-empty metrics.
        try? config.setTelegramUserSession(
            "1AgAOMT946OxqWq3" + String(repeating: "A", count: 200)
        )
        config.telegramRateLimit = RateLimitDisplay(
            maxPerHour: 30, inWindowCount: 5, isBlocked: false
        )
        config.telegramMessagesSentToday = 42
        XCTAssertTrue(config.telegramAccountEnabled)
        XCTAssertEqual(config.telegramRateLimit.inWindowCount, 5)
        XCTAssertEqual(config.telegramMessagesSentToday, 42)
        // Sign out via clearTelegramUserSession().
        try? config.clearTelegramUserSession()
        XCTAssertFalse(config.telegramAccountEnabled)
        XCTAssertEqual(config.telegramRateLimit, .empty)
        XCTAssertEqual(config.telegramMessagesSentToday, 0)
    }

    func testSetTelegramUserSessionEmptyClearsRateLimitState() {
        // The empty-string sign-out path (setTelegramUserSession(""))
        // must ALSO clear the rate-limit state, not just the
        // sign-out-via-clearTelegramUserSession path. They share
        // the same UI surface; the user shouldn't see stale
        // metrics after EITHER path.
        let config = AICloneConfig(defaults: customDefaults)
        try? config.setTelegramUserSession(
            "1AgAOMT946OxqWq3" + String(repeating: "A", count: 200)
        )
        config.telegramRateLimit = RateLimitDisplay(
            maxPerHour: 30, inWindowCount: 7, isBlocked: true, secondsUntilNextSlot: 60
        )
        config.telegramMessagesSentToday = 99
        // Sign out via the empty-string path.
        try? config.setTelegramUserSession("")
        XCTAssertFalse(config.telegramAccountEnabled)
        XCTAssertEqual(config.telegramRateLimit, .empty)
        XCTAssertEqual(config.telegramMessagesSentToday, 0)
    }


    // MARK: - Status poll lifecycle (plan §8)

    func testStartStatusPollIsIdempotent() {
        // Calling startTelegramUserAccountStatusPoll twice in
        // a row must not spawn two concurrent pollers.
        let config = AICloneConfig(defaults: customDefaults)
        config.startTelegramUserAccountStatusPoll()
        let firstTask = config.telegramStatusPollTask
        XCTAssertNotNil(firstTask)
        config.startTelegramUserAccountStatusPoll()
        let secondTask = config.telegramStatusPollTask
        XCTAssertNotNil(secondTask)
        XCTAssertFalse(firstTask == secondTask,
            "Second startTelegramUserAccountStatusPoll must cancel the first; the underlying Task should be a new instance.")
        // Cleanup so the test doesn't leave a poll running.
        config.stopTelegramUserAccountStatusPoll()
        XCTAssertNil(config.telegramStatusPollTask)
    }

    func testStopStatusPollIsSafeWhenNoPollActive() {
        // Calling stop without a prior start must not crash.
        let config = AICloneConfig(defaults: customDefaults)
        XCTAssertNil(config.telegramStatusPollTask)
        config.stopTelegramUserAccountStatusPoll()
        XCTAssertNil(config.telegramStatusPollTask)
    }

    func testSignOutStopsStatusPoll() {
        // cubic review 4619143030 P2: merely dropping the last
        // reference to a Task does not cancel it -- the task
        // keeps running its body until it returns or is
        // explicitly cancelled. We need to capture the old
        // task BEFORE sign-out and assert isCancelled on it
        // AFTER. If a future change to
        // stopTelegramUserAccountStatusPoll() drops the
        // .cancel() call while keeping `telegramStatusPollTask
        // = nil`, this test would fail (the old task would
        // still be running with isCancelled == false).
        let config = AICloneConfig(defaults: customDefaults)
        try? config.setTelegramUserSession(
            "1AgAOMT946OxqWq3" + String(repeating: "A", count: 200)
        )
        config.startTelegramUserAccountStatusPoll()
        let oldTask = config.telegramStatusPollTask
        XCTAssertNotNil(oldTask)
        try? config.clearTelegramUserSession()
        XCTAssertNil(config.telegramStatusPollTask,
            "Sign-out must cancel the status poll")
        XCTAssertTrue(oldTask?.isCancelled ?? false,
            "Sign-out must CANCEL the old task (not just drop the reference). Without explicit cancel(), the task continues to make /status requests every 30s after the user has signed out.")
    }

    func testEmptyStringSignOutAlsoCancelsStatusPoll() {
        // Symmetry check: the empty-string sign-out path in
        // setTelegramUserSession must ALSO cancel the poll,
        // not just the clearTelegramUserSession path. Both
        // are valid sign-out routes; both must stop the poll.
        let config = AICloneConfig(defaults: customDefaults)
        try? config.setTelegramUserSession(
            "1AgAOMT946OxqWq3" + String(repeating: "A", count: 200)
        )
        config.startTelegramUserAccountStatusPoll()
        let oldTask = config.telegramStatusPollTask
        XCTAssertNotNil(oldTask)
        try? config.setTelegramUserSession("")
        XCTAssertNil(config.telegramStatusPollTask)
        XCTAssertTrue(oldTask?.isCancelled ?? false)
    }


    // MARK: - Telegram user-account auto-reply toggle state (plan)

    func testTelegramAutoReplyStartsFalse() {
        // Fresh AICloneConfig: auto-reply toggle defaults to off
        // until the 30s /status poll syncs it from the plugin.
        let config = AICloneConfig(defaults: customDefaults)
        XCTAssertFalse(config.telegramAutoReplyEnabled)
        XCTAssertFalse(config.telegramAutoReplyInFlight)
    }

    func testSignOutClearsTelegramAutoReplyState() {
        // Sign-out resets the auto-reply toggle alongside the
        // rate-limit + daily-sent state. So a future
        // sign-in for a different account doesn't show stale
        // auto-reply=on from the previous user.
        let config = AICloneConfig(defaults: customDefaults)
        try? config.setTelegramUserSession(
            "1AgAOMT946OxqWq3" + String(repeating: "A", count: 200)
        )
        config.telegramAutoReplyEnabled = true
        config.telegramAutoReplyInFlight = true
        XCTAssertTrue(config.telegramAutoReplyEnabled)
        XCTAssertTrue(config.telegramAutoReplyInFlight)
        try? config.clearTelegramUserSession()
        XCTAssertFalse(config.telegramAutoReplyEnabled)
        XCTAssertFalse(config.telegramAutoReplyInFlight)
    }
}
