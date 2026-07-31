import XCTest

@testable import Omi_Computer

@MainActor
final class SBOnboardingLanguageCopyTests: XCTestCase {

  func testLanguagePickerCopyExplainsTheSpokenLanguagePreference() {
    XCTAssertEqual(SBOnboardingLanguageCopy.question, "What language should Omi listen and reply in?")
  }

  func testLanguageStepStartsWithAnEmptyDraft() {
    let model = SBOnboardingModel(appState: AppState(), chatProvider: ChatProvider(), onComplete: nil)

    XCTAssertEqual(model.languageDraft, "")
  }
}
