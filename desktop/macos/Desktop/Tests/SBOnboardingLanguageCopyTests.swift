import XCTest

@testable import Omi_Computer

@MainActor
final class SBOnboardingLanguageCopyTests: XCTestCase {

  func testLanguagePickerCopyExplainsTheSpokenLanguagePreference() {
    XCTAssertEqual(SBOnboardingLanguageCopy.question, "What language should Omi listen and reply in?")
    XCTAssertEqual(SBOnboardingLanguageCopy.detectedLanguageDetail, "· detected from your Mac")
    XCTAssertEqual(SBOnboardingLanguageCopy.continueAction(for: "English"), "Continue in English")
    XCTAssertEqual(SBOnboardingLanguageCopy.changeSpokenLanguageAction, "Change spoken language")
  }

  func testDetectedLanguageDetailIsShownOnlyForAMacLocalePrefill() {
    let model = SBOnboardingModel(appState: AppState(), chatProvider: ChatProvider(), onComplete: nil)

    model.prefillDetectedLanguage(from: "es")

    XCTAssertEqual(model.languageDraft, "Spanish")
    XCTAssertTrue(model.languageIsDetectedFromMac)
  }

  func testExistingLanguageDraftIsNotRelabeledAsMacDetected() {
    let model = SBOnboardingModel(appState: AppState(), chatProvider: ChatProvider(), onComplete: nil)
    model.languageDraft = "English"

    model.prefillDetectedLanguage(from: "es")

    XCTAssertEqual(model.languageDraft, "English")
    XCTAssertFalse(model.languageIsDetectedFromMac)
  }
}
