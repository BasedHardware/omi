import AVFoundation
import XCTest

@testable import Omi_Computer

@MainActor
final class FloatingBarVoiceResponseSettingsTests: XCTestCase {

  /// The system voice honors the user's Voice Speed multiplier the same way the OpenAI
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

  func testDefaultVoiceIsShimmerOpenAIHumanVoice() {
    XCTAssertEqual(ShortcutSettings.defaultVoiceID, ShortcutSettings.openAIShimmerVoiceID)

    let voice = ShortcutSettings.voiceOption(for: ShortcutSettings.defaultVoiceID)
    XCTAssertEqual(voice.name, "Shimmer")
    XCTAssertEqual(voice.gender, .female)
    XCTAssertTrue(voice.isOpenAI)
    XCTAssertEqual(voice.provider, .openAI)
    XCTAssertEqual(voice.openAIVoice, "shimmer")
  }

  func testShimmerVoiceHasNeutralDisplayName() {
    let voice = ShortcutSettings.voiceOption(for: ShortcutSettings.openAIShimmerVoiceID)
    XCTAssertEqual(voice.name, "Shimmer")
    XCTAssertEqual(voice.openAIVoice, "shimmer")
  }

  func testOnlyOpenAIVoicesAreAvailableInPicker() {
    XCTAssertFalse(ShortcutSettings.availableVoices.contains { $0.isLocalSystem })
  }

  func testLegacyProxyVoicesAreNotAvailableInPicker() {
    XCTAssertFalse(
      ShortcutSettings.availableVoices.contains {
        $0.name.localizedCaseInsensitiveContains("Sloane")
          || $0.id == "BAMYoBHLZM7lJgJAmFz0"
      }
    )
  }

  func testInvalidVoiceFallsBackToDefaultOpenAIVoice() {
    let voice = ShortcutSettings.voiceOption(for: "missing")
    XCTAssertEqual(voice.id, ShortcutSettings.defaultVoiceID)
    XCTAssertTrue(voice.isOpenAI)
    XCTAssertEqual(voice.openAIVoice, "shimmer")
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
}
