import Vision
import XCTest

@testable import Omi_Computer

final class RewindOCRQualityTests: XCTestCase {

  func testOCRModeAlwaysUsesAccurateRecognition() {
    XCTAssertEqual(
      RewindOCRService.recognitionLevel(),
      VNRequestTextRecognitionLevel.accurate,
      "Rewind OCR must always use Apple's accurate recognition level for readable screenshot text")
  }

  func testOCRAlwaysUsesLanguageCorrection() {
    XCTAssertTrue(RewindOCRService.usesLanguageCorrection())
  }

  func testRecognitionLanguagesFollowThePreferredLocaleInsteadOfAPinnedOne() {
    // The bug: the list was the constant ["en-US"], so a Japanese-preferring Mac
    // recognised no Japanese at all — the script was out of scope, not misread.
    XCTAssertEqual(
      RewindOCRService.resolveRecognitionLanguages(
        preferred: ["ja-JP"],
        supported: ["en-US", "ja-JP", "fr-FR"]),
      ["ja-JP", "en-US"],
      "the user's own language must lead, with English retained for mixed screen text")
  }

  func testRegionlessPreferredLanguageSelectsASupportedRegionalVariant() {
    XCTAssertEqual(
      RewindOCRService.resolveRecognitionLanguages(
        preferred: ["ja"],
        supported: ["en-US", "ja-JP"]),
      ["ja-JP", "en-US"],
      "a region-less preference such as `ja` must still reach Vision's `ja-JP`")
  }

  func testUnsupportedPreferredLanguagesAreDroppedRatherThanPassedToVision() {
    // Vision throws on an unsupported tag, which would fail the whole request —
    // turning a partial-recognition bug into total OCR loss.
    XCTAssertEqual(
      RewindOCRService.resolveRecognitionLanguages(
        preferred: ["xx-YY"],
        supported: ["en-US", "ja-JP"]),
      ["en-US"])
  }

  func testEnglishIsNotDuplicatedWhenItIsAlreadyPreferred() {
    XCTAssertEqual(
      RewindOCRService.resolveRecognitionLanguages(
        preferred: ["en-US", "ja-JP"],
        supported: ["en-US", "ja-JP"]),
      ["en-US", "ja-JP"])
  }

  func testAnUnavailableSupportedListStillYieldsAUsableLanguage() {
    XCTAssertEqual(
      RewindOCRService.resolveRecognitionLanguages(preferred: ["ja-JP"], supported: []),
      ["en-US"],
      "a failed capability query must not leave the request with an empty language list")
  }

  func testBatteryOptimizationLowersCaptureCadenceInsteadOfOCRQuality() {
    let settings = RewindSettings.shared
    let savedInterval = settings.captureInterval
    settings.captureInterval = 2.0
    defer { settings.captureInterval = savedInterval }

    XCTAssertEqual(settings.effectiveCaptureInterval(isOnBattery: false), 2.0)
    XCTAssertEqual(
      settings.effectiveCaptureInterval(isOnBattery: true),
      2.0 * RewindSettings.batteryCaptureIntervalMultiplier)
    XCTAssertEqual(RewindOCRService.recognitionLevel(), VNRequestTextRecognitionLevel.accurate)
  }
}
