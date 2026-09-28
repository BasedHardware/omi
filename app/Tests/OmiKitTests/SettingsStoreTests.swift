import XCTest

@testable import OmiKit

/// `SettingsStore` round-trips through the native defaults store with the
/// upstream record translation: native defaults keys go in, the JS-named
/// record (`desktopSettingsClient.ts` / `OmiDesktopCommandsModule.mm`)
/// comes out for `snapshotFromRecord` to parse. The translation used to be
/// missing, so every preference read back as its default.
final class SettingsStoreTests: XCTestCase {
    /// In-memory `KeyValueStoring` standing in for UserDefaults /
    /// SharedPreferences host backends.
    private final class MemoryKeyValueStore: KeyValueStoring, @unchecked Sendable {
        private var values: [String: PreferenceValue] = [:]

        func value(forKey key: String) -> PreferenceValue? {
            values[key]
        }

        func set(_ value: PreferenceValue?, forKey key: String) {
            values[key] = value
        }
    }

    func testSetPreferenceTranslatesNativeKeyToRecordName() async {
        let storage = MemoryKeyValueStore()
        let settings = SettingsStore(storage: storage)

        let snapshot = await settings.setPreference(
            desktopPreferenceKeys.screenCapture, PreferenceValue.bool(true))

        // Stored under the native defaults key…
        XCTAssertEqual(
            storage.value(forKey: desktopPreferenceKeys.screenCapture),
            PreferenceValue.bool(true))
        // …and parsed back through the JS record name.
        XCTAssertTrue(snapshot.screenCapture)
    }

    func testLoadPreferencesRoundTripsEveryWhitelistKey() async {
        let storage = MemoryKeyValueStore()
        storage.set(.string("new"), forKey: SOFTWARE_PLANE_DEFAULTS_KEY)
        storage.set(.string("always"), forKey: desktopPreferenceKeys.audioMode)
        storage.set(.integer(140), forKey: desktopPreferenceKeys.fontScale)
        storage.set(.integer(30), forKey: desktopPreferenceKeys.rewindRetentionDays)
        storage.set(.string("light"), forKey: desktopPreferenceKeys.appearance)
        storage.set(.string("v5"), forKey: desktopPreferenceKeys.uiVersion)
        storage.set(.string("recall,chat"), forKey: desktopPreferenceKeys.exploreProgress)
        let settings = SettingsStore(storage: storage)

        let snapshot = await settings.loadPreferences()

        XCTAssertEqual(snapshot.softwarePlane, .new)
        XCTAssertEqual(snapshot.audioMode, .always)
        XCTAssertEqual(snapshot.fontScale, 140)
        XCTAssertEqual(snapshot.rewindRetentionDays, 30)
        XCTAssertEqual(snapshot.appearance, .light)
        XCTAssertEqual(snapshot.uiVersion, .v5)
        XCTAssertEqual(snapshot.exploreProgress, "recall,chat")
        // Untouched tolerant booleans keep their defaults.
        XCTAssertTrue(snapshot.interfaceSounds)
        XCTAssertFalse(snapshot.screenCapture)
    }

    func testOnboardingSetupRevisionMarkerParses() async {
        let storage = MemoryKeyValueStore()
        let settings = SettingsStore(storage: storage)

        let before = await settings.loadPreferences()
        XCTAssertFalse(before.onboardingSetupCompleted)

        _ = await settings.setPreference(
            desktopPreferenceKeys.onboardingSetupRevision, PreferenceValue.string("1"))
        let after = await settings.loadPreferences()
        XCTAssertTrue(after.onboardingSetupCompleted)
        // The marker key stays out of the explore-check CSV.
        XCTAssertEqual(after.exploreProgress, "")
    }

    func testSnapshotFromRecordReadsJsNamesDirectly() {
        // The record shape the native hosts compose (JS names, upstream
        // `OmiDesktopCommandsModule.mm`).
        let record = JSONValue.object([
            ("screenCapture", JSONValue.bool(true)),
            ("appearance", JSONValue.string("light")),
            ("exploreProgress", JSONValue.string("tasks,settings")),
            ("onboardingSetupRevision", JSONValue.string("1")),
            ("stampedV5Origin", JSONValue.string("https://api.omi.me")),
        ])
        let snapshot = snapshotFromRecord(record)
        XCTAssertTrue(snapshot.screenCapture)
        XCTAssertEqual(snapshot.appearance, .light)
        XCTAssertEqual(snapshot.exploreProgress, "tasks,settings")
        XCTAssertTrue(snapshot.onboardingSetupCompleted)
        XCTAssertEqual(snapshot.stampedV5Origin, "https://api.omi.me")
        XCTAssertEqual(snapshot.softwarePlane, .new)
    }
}
