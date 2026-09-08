import XCTest

@testable import Omi_Computer

/// Regression coverage for the onboarding voice-demo corrupting the saved PTT
/// mode.
///
/// The demo used to force `.live` by assigning `pttTranscriptionMode`, whose
/// didSet persists to UserDefaults immediately — so a quit/crash before the
/// restore in onDisappear permanently changed the user's saved mode. The demo
/// now uses a transient, never-persisted override.
@MainActor
final class ShortcutSettingsPTTDemoOverrideTests: XCTestCase {
  func testDemoOverrideDoesNotPersistOrChangeStoredMode() {
    let settings = ShortcutSettings.shared
    let originalStored = settings.pttTranscriptionMode
    let originalOverride = settings.pttTranscriptionModeDemoOverride
    defer {
      settings.pttTranscriptionModeDemoOverride = originalOverride
      settings.pttTranscriptionMode = originalStored
    }

    settings.pttTranscriptionMode = .batch

    // Enter the demo: override to live. The stored preference is the ONLY
    // writer of the persisted UserDefaults key (via its didSet), so asserting
    // it is untouched proves the override never persisted.
    settings.pttTranscriptionModeDemoOverride = .live
    XCTAssertEqual(settings.effectivePTTTranscriptionMode, .live, "override wins while active")
    XCTAssertEqual(
      settings.pttTranscriptionMode, .batch,
      "override must not touch the stored (persisted) preference")

    // Leave the demo (or crash-then-relaunch clears the transient override).
    settings.pttTranscriptionModeDemoOverride = nil
    XCTAssertEqual(settings.effectivePTTTranscriptionMode, .batch, "falls back to stored preference")
  }
}
