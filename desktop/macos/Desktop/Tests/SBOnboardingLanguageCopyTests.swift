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

  func testLanguageSelectionRejectsEmptyAndPartialInput() {
    XCTAssertNil(SBOnboardingModel.languageSelection(for: ""))
    XCTAssertNil(SBOnboardingModel.languageSelection(for: "   \n"))
    XCTAssertNil(SBOnboardingModel.languageSelection(for: "Span"))
    XCTAssertEqual(SBOnboardingModel.languageSelection(for: "Spanish")?.code, "es")
  }

  func testLanguageSuggestionsPreferTheCurrentLocaleThenCommonLanguages() {
    XCTAssertEqual(
      SBOnboardingModel.preferredLanguageCodes(localeCode: "fr").prefix(4),
      ["fr", "en", "es", "de"]
    )
  }

  func testLanguageSuggestionsNormalizeLocaleCodes() {
    XCTAssertEqual(SBOnboardingModel.preferredLanguageCodes(localeCode: "zh").first, "zh-CN")
  }
}
