import XCTest
import Vision

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
