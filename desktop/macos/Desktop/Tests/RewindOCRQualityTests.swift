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

  func testAScopeSharingNothingWithTheUserStillComesFromVisionsOwnList() {
    // Returning a tag Vision did not report makes `perform` throw and takes the
    // whole request down, so the no-overlap branch must pick from `supported`
    // rather than falling back to a literal.
    let supported = ["fr-FR", "de-DE"]
    let resolved = RewindOCRService.resolveRecognitionLanguages(
      preferred: ["ja-JP"],
      supported: supported)

    XCTAssertEqual(resolved.count, 1)
    XCTAssertTrue(
      supported.contains(resolved[0]),
      "resolved \(resolved) must be drawn from Vision's reported list \(supported)")
  }

  func testTraditionalChineseIsNotRecognisedWithTheSimplifiedScope() {
    // Collapsing zh-TW to its primary language would match zh-Hans and read
    // Traditional text with the Simplified model.
    XCTAssertEqual(
      RewindOCRService.resolveRecognitionLanguages(
        preferred: ["zh-TW"],
        supported: ["en-US", "zh-Hans", "zh-Hant"]),
      ["zh-Hant", "en-US"])
  }

  func testSimplifiedChinesePicksItsOwnScope() {
    XCTAssertEqual(
      RewindOCRService.resolveRecognitionLanguages(
        preferred: ["zh-CN"],
        supported: ["en-US", "zh-Hans", "zh-Hant"]),
      ["zh-Hans", "en-US"])
  }

  func testAnUnavailableSupportedListStillYieldsAUsableLanguage() {
    XCTAssertEqual(
      RewindOCRService.resolveRecognitionLanguages(preferred: ["ja-JP"], supported: []),
      ["en-US"],
      "with no reported list there is nothing to choose from, so English is the only safe guess")
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
