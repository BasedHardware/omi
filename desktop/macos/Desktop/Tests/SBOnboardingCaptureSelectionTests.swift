import XCTest

@testable import Omi_Computer

@MainActor
final class SBOnboardingCaptureSelectionTests: XCTestCase {
  func testDefaultCaptureSelectionRecordsOnlyDuringMeetings() {
    let selection = SBOnboardingModel.defaultCaptureSelection

    XCTAssertEqual(selection.audioRecordingMode, .onlyMeetings)
  }

  func testAlwaysSelectionMapsToAlwaysOn() {
    let selection = SBOnboardingModel.CaptureSelection.always

    XCTAssertEqual(selection.audioRecordingMode, .always)
  }
}
