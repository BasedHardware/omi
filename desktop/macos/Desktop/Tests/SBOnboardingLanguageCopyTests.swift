import XCTest

@testable import Omi_Computer

final class SBOnboardingLanguageCopyTests: XCTestCase {

  func testLanguagePickerCopyExplainsTheSpokenLanguagePreference() {
    XCTAssertEqual(SBOnboardingLanguageCopy.question, "What language should Omi listen and reply in?")
    XCTAssertEqual(SBOnboardingLanguageCopy.detectedLanguageDetail, "· detected from your Mac")
    XCTAssertEqual(SBOnboardingLanguageCopy.continueAction(for: "English"), "Continue in English")
    XCTAssertEqual(SBOnboardingLanguageCopy.changeSpokenLanguageAction, "Change spoken language")
  }
}
