import XCTest

@testable import Omi_Computer

final class SharedCaptureSilentMicRecoveryPolicyTests: XCTestCase {
  func testConfiguresNonBluetoothInputsForSilentCaptureDetection() {
    let capture = AudioCaptureService()
    SharedCaptureSilentMicRecoveryPolicy.configure(capture)

    XCTAssertNil(capture.evaluateSilentMicWindow(peak: 0, isBluetooth: false, now: 0))
    XCTAssertNotNil(capture.evaluateSilentMicWindow(peak: 0, isBluetooth: false, now: 1))
  }

  func testRebuildsBeforeTheBoundedRecoveryLimit() {
    XCTAssertEqual(SharedCaptureSilentMicRecoveryPolicy.action(for: 1), .rebuild)
    XCTAssertEqual(SharedCaptureSilentMicRecoveryPolicy.action(for: 2), .rebuild)
  }

  func testStopsAndSurfacesErrorAtTheRecoveryLimit() {
    XCTAssertEqual(
      SharedCaptureSilentMicRecoveryPolicy.action(for: 3),
      .stopAndSurfaceError)
  }
}

/// Nik's prod log showed 31 silent-mic detections and 14 alerts in one sitting: the
/// fallback pinned the built-in mic, the rebuild re-resolved the system default back to a
/// silent AirPods Max, repeat. These pin that a healed route outranks the system default.
final class SilentMicRoutePolicyTests: XCTestCase {
  func testHealedDeviceSurvivesARebuild() {
    XCTAssertEqual(
      SilentMicRoutePolicy.captureDeviceID(healed: 86, systemDefault: 97), 86,
      "a rebuild must not move capture back onto the route that was already proven silent")
  }

  func testSystemDefaultIsUsedWhenNothingHasBeenHealed() {
    XCTAssertEqual(SilentMicRoutePolicy.captureDeviceID(healed: nil, systemDefault: 97), 97)
  }

  func testNoDeviceAtAllStaysNil() {
    XCTAssertNil(SilentMicRoutePolicy.captureDeviceID(healed: nil, systemDefault: nil))
  }
}

/// Behavioural, not a source tripwire: the migration is pure UserDefaults, so it can be
/// exercised directly. A legacy PTT-only microphone must reach the shared preference the
/// first time anything asks for it — previously it only moved during a push-to-talk turn,
/// so Transcription showed "System Default" and recorded with it until the user happened
/// to hold the PTT key.
@MainActor
final class PTTMicrophoneMigrationTests: XCTestCase {
  private let legacyKey = DefaultsKey.shortcutPTTInputDeviceUID.rawValue
  private let sharedKey = AudioCaptureService.preferredInputUIDDefaultsKey
  private let markerKey = DefaultsKey.shortcutPTTMicrophoneMergedIntoPreferred.rawValue

  private func withCleanDefaults(_ body: () -> Void) {
    let d = UserDefaults.standard
    let saved = (d.string(forKey: legacyKey), d.string(forKey: sharedKey), d.bool(forKey: markerKey))
    defer {
      saved.0.map { d.set($0, forKey: legacyKey) } ?? d.removeObject(forKey: legacyKey)
      saved.1.map { d.set($0, forKey: sharedKey) } ?? d.removeObject(forKey: sharedKey)
      d.set(saved.2, forKey: markerKey)
    }
    d.removeObject(forKey: legacyKey)
    d.removeObject(forKey: sharedKey)
    d.set(false, forKey: markerKey)
    body()
  }

  func testLegacyPTTChoiceIsCarriedIntoTheSharedPreference() {
    withCleanDefaults {
      UserDefaults.standard.set("BuiltInMicrophoneDevice", forKey: legacyKey)
      ShortcutSettings.migratePTTMicrophoneChoiceIfNeeded()
      XCTAssertEqual(
        UserDefaults.standard.string(forKey: sharedKey), "BuiltInMicrophoneDevice",
        "unifying the setting must not silently discard a microphone the user picked")
    }
  }

  /// An explicit transcription choice is the newer, more visible decision; the legacy
  /// PTT-only value must not overwrite it.
  func testAnExistingSharedChoiceIsNotOverwritten() {
    withCleanDefaults {
      UserDefaults.standard.set("legacy-ptt-uid", forKey: legacyKey)
      UserDefaults.standard.set("chosen-in-transcription", forKey: sharedKey)
      ShortcutSettings.migratePTTMicrophoneChoiceIfNeeded()
      XCTAssertEqual(UserDefaults.standard.string(forKey: sharedKey), "chosen-in-transcription")
    }
  }

  func testMigrationRunsOnlyOnce() {
    withCleanDefaults {
      UserDefaults.standard.set("legacy-ptt-uid", forKey: legacyKey)
      ShortcutSettings.migratePTTMicrophoneChoiceIfNeeded()
      UserDefaults.standard.set("", forKey: sharedKey)
      ShortcutSettings.migratePTTMicrophoneChoiceIfNeeded()
      XCTAssertEqual(
        UserDefaults.standard.string(forKey: sharedKey), "",
        "a second run must not resurrect a choice the user has since cleared")
    }
  }
}
