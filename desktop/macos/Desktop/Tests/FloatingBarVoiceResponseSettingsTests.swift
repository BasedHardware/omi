import AVFoundation
import XCTest

@testable import Omi_Computer

@MainActor
final class FloatingBarVoiceResponseSettingsTests: XCTestCase {

  /// The system voice honors the user's Voice Speed multiplier the same way the cloud
  /// audio path does — a hardcoded utterance rate made spoken notifications crawl at ~1×
  /// while push-to-talk answers played at the default 1.4×.
  func testSystemSpeechRateScalesWithVoiceSpeed() {
    let normal = FloatingBarVoicePlaybackService.systemSpeechRate(playbackSpeed: 1.0)
    let fast = FloatingBarVoicePlaybackService.systemSpeechRate(playbackSpeed: 1.4)
    XCTAssertEqual(normal, 0.47, accuracy: 0.001)
    XCTAssertEqual(fast, 0.658, accuracy: 0.001)
    XCTAssertGreaterThan(fast, normal)
    // Extreme multipliers stay inside AVSpeechUtterance's legal range.
    XCTAssertLessThanOrEqual(
      FloatingBarVoicePlaybackService.systemSpeechRate(playbackSpeed: 10),
      AVSpeechUtteranceMaximumSpeechRate)
    XCTAssertGreaterThanOrEqual(
      FloatingBarVoicePlaybackService.systemSpeechRate(playbackSpeed: 0),
      AVSpeechUtteranceMinimumSpeechRate)
  }

  func testVoiceQueryAlwaysSpeaksAndTypedQueryUsesToggle() {
    let settings = ShortcutSettings.shared
    let originalTypedSetting = settings.floatingBarTypedQuestionVoiceAnswersEnabled

    defer {
      settings.floatingBarTypedQuestionVoiceAnswersEnabled = originalTypedSetting
    }

    settings.floatingBarTypedQuestionVoiceAnswersEnabled = false
    XCTAssertTrue(settings.shouldSpeakFloatingBarResponse(forVoiceQuery: true))
    XCTAssertFalse(settings.shouldSpeakFloatingBarResponse(forVoiceQuery: false))

    settings.floatingBarTypedQuestionVoiceAnswersEnabled = true
    XCTAssertTrue(settings.shouldSpeakFloatingBarResponse(forVoiceQuery: true))
    XCTAssertTrue(settings.shouldSpeakFloatingBarResponse(forVoiceQuery: false))
  }

  func testLegacyOpenAIVoiceDefaultsKeyIsIgnored() throws {
    let suite = try XCTUnwrap(UserDefaults(suiteName: "AssistantVoiceStoreTests.legacy"))
    defer { suite.removePersistentDomain(forName: "AssistantVoiceStoreTests.legacy") }
    suite.set("openai:shimmer", forKey: ScopedDefaultsKey.legacyShortcutSelectedVoiceID)
    suite.set("Puck", forKey: ScopedDefaultsKey.assistantVoiceID(ownerID: "owner-1"))
    let store = AssistantVoiceStore(
      fetchCatalog: { _ in AssistantVoiceCatalogResponse(voices: [], defaultVoiceId: "Charon") },
      fetchPreference: { _ in throw APIError.invalidResponse },
      ownerIDProvider: { "owner-1" },
      defaults: suite,
      notificationCenter: NotificationCenter(),
      observeOwnerChanges: false)
    XCTAssertEqual(store.selectedVoiceID, "Puck")
  }
}
