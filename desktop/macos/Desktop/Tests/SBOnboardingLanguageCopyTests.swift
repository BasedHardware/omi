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

  func testLanguageSuggestionsKeepTheCurrentRegion() {
    XCTAssertEqual(SBOnboardingModel.preferredLanguageCodes(localeCode: "zh-TW").first, "zh-TW")
  }

  func testResumedLanguageHydratesFromANormalizedPersistedCode() {
    let previousLanguages = AssistantSettings.shared.voiceLanguages
    let hadExplicitLanguages = AssistantSettings.shared.hasExplicitVoiceLanguages
    defer { AssistantSettings.shared.voiceLanguages = hadExplicitLanguages ? previousLanguages : [] }

    AssistantSettings.shared.voiceLanguages = ["zh"]
    let model = SBOnboardingModel(appState: AppState(), chatProvider: ChatProvider(), onComplete: nil)
    model.begin()

    XCTAssertEqual(model.languageDraft, "Chinese (Simplified)")
    model.streamTask?.cancel()
  }
}
