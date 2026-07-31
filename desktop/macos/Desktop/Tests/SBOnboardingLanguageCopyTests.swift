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

  func testEmptyLanguageSubmissionDoesNotChooseASuggestion() {
    XCTAssertFalse(SBOnboardingModel.shouldSelectLanguageOnSubmit(""))
    XCTAssertFalse(SBOnboardingModel.shouldSelectLanguageOnSubmit("   \n"))
    XCTAssertTrue(SBOnboardingModel.shouldSelectLanguageOnSubmit("Spanish"))
  }

  func testLanguageSuggestionsPreferTheCurrentLocaleThenCommonLanguages() {
    XCTAssertEqual(
      SBOnboardingModel.preferredLanguageCodes(localeCode: "fr").prefix(4),
      ["fr", "en", "es", "de"]
    )
  }
}
