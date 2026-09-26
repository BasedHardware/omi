import XCTest

@testable import Omi_Computer

/// Day-0 chips are gated on what Omi can answer with zero history.
final class DayZeroChipsTests: XCTestCase {
  func testNoSignalsYieldsOnlyTheTeachMeDraft() {
    XCTAssertEqual(DayZeroChips.chips(for: DayZeroChipSignals()), [DayZeroChips.rememberDraft])
  }

  func testScreenPermissionUnlocksTheThreeScreenChipsInOrder() {
    var signals = DayZeroChipSignals()
    signals.canSeeScreen = true
    signals.screenHistoryEnabled = true
    XCTAssertEqual(
      DayZeroChips.chips(for: signals),
      [DayZeroChips.summarizeScreen, DayZeroChips.lastHour, DayZeroChips.screenToTasks, DayZeroChips.rememberDraft])
  }

  func testLastHourNeedsScreenHistoryNotJustPermission() {
    var signals = DayZeroChipSignals()
    signals.canSeeScreen = true
    XCTAssertEqual(
      DayZeroChips.chips(for: signals),
      [DayZeroChips.summarizeScreen, DayZeroChips.screenToTasks, DayZeroChips.rememberDraft])
  }

  func testLanguageMismatchLeadsAndTheDraftCloses() {
    var signals = DayZeroChipSignals()
    signals.canSeeScreen = true
    signals.screenHistoryEnabled = true
    signals.systemLanguageName = "日本語"
    let chips = DayZeroChips.chips(for: signals)
    XCTAssertEqual(chips.first, "Switch to 日本語")
    XCTAssertEqual(chips.last, DayZeroChips.rememberDraft)
    XCTAssertFalse(
      chips.contains(DayZeroChips.calendarToday),
      "The Home top-up has no live connector signal; the calendar chip comes from onboarding's setup state")
  }

  func testEveryChipFitsTheHomeChipBudget() {
    var signals = DayZeroChipSignals()
    signals.canSeeScreen = true
    signals.screenHistoryEnabled = true
    signals.systemLanguageName = "Português"
    for chip in DayZeroChips.chips(for: signals) {
      XCTAssertLessThanOrEqual(chip.count, HomeSuggestionComposer.maxPersonalizedLength, chip)
    }
  }

  func testDraftChipPrefillsWithATrailingSpaceAndNothingElseIsADraft() {
    XCTAssertTrue(DayZeroChips.isDraftPrompt(DayZeroChips.rememberDraft))
    XCTAssertTrue(DayZeroChips.isDraftPrompt("  \(DayZeroChips.rememberDraft) "))
    XCTAssertEqual(DayZeroChips.draftText(for: DayZeroChips.rememberDraft), "Remember that I ")
    XCTAssertFalse(DayZeroChips.isDraftPrompt(DayZeroChips.summarizeScreen))
    XCTAssertEqual(DayZeroChips.draftText(for: DayZeroChips.summarizeScreen), DayZeroChips.summarizeScreen)
  }

  func testLanguageMismatchUsesTheEndonymAndIgnoresRegion() {
    XCTAssertEqual(DayZeroChipSignals.languageMismatchName(systemLanguageCode: "es", omiLanguageCode: "en"), "Español")
    XCTAssertNil(DayZeroChipSignals.languageMismatchName(systemLanguageCode: "pt", omiLanguageCode: "pt-BR"))
    XCTAssertNil(DayZeroChipSignals.languageMismatchName(systemLanguageCode: "en", omiLanguageCode: "en"))
    XCTAssertNil(DayZeroChipSignals.languageMismatchName(systemLanguageCode: nil, omiLanguageCode: "en"))
    XCTAssertNil(DayZeroChipSignals.languageMismatchName(systemLanguageCode: "", omiLanguageCode: "en"))
  }
}
