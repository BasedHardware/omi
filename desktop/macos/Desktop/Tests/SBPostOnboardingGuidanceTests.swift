import XCTest

@testable import Omi_Computer

/// Behavioral coverage for the post-onboarding guidance rules.
///
/// The dashboard has always been able to render this guidance
/// (`TryAskingPopupView` / `PromptSuggestionBanner`), but nothing produced it:
/// `PostOnboardingPromptSuggestions.save(_:)` was reachable only from the
/// retired paged-intro onboarding, so the live Second Brain flow finished with
/// an empty array and both surfaces were permanently gated off. These tests
/// pin the rules that now produce it — in particular that a suggestion is never
/// emitted for a connector the user skipped or a permission they denied.
final class SBPostOnboardingGuidanceTests: XCTestCase {

  // MARK: - Preconditions

  func testSkippedEverythingStillGetsAnswerableSuggestions() {
    let suggestions = SBPostOnboardingGuidance.suggestions(for: SBSetupSnapshot())

    XCTAssertEqual(
      suggestions,
      [HomeSuggestionComposer.universalFirstQuestion, SBPostOnboardingGuidance.teachMeDraft],
      "A user who skipped every step must still get questions that need no connector and no permission")
    XCTAssertFalse(
      suggestions.contains("What can you help me with?"),
      "The capability-list question over-indexed among users who stopped after one question")
  }

  func testNoConnectorSuggestionSurvivesASkippedConnector() {
    var setup = SBSetupSnapshot()
    setup.connectedContextIDs = []
    setup.canSeeScreen = false

    let suggestions = SBPostOnboardingGuidance.suggestions(for: setup)

    for banned in [
      "What's on my calendar today?",
      "What email follow-ups matter most today?",
      "What am I working on, based on my files?",
      "Summarize my recent notes.",
      DayZeroChips.summarizeScreen,
      DayZeroChips.lastHour,
    ] {
      XCTAssertFalse(
        suggestions.contains(banned),
        "\(banned) depends on setup this user skipped and must not be suggested")
    }
  }

  func testScreenPermissionUnlocksTheScreenQuestion() {
    var granted = SBSetupSnapshot()
    granted.canSeeScreen = true

    XCTAssertTrue(SBPostOnboardingGuidance.suggestions(for: granted).contains(DayZeroChips.summarizeScreen))
    XCTAssertFalse(
      SBPostOnboardingGuidance.suggestions(for: SBSetupSnapshot()).contains(DayZeroChips.summarizeScreen),
      "Screen Recording denied must not produce a question that reads the screen")
  }

  func testSystemLanguageMismatchLeadsWithTheSwitchChip() {
    var setup = SBSetupSnapshot()
    setup.systemLanguageName = "Español"
    let suggestions = SBPostOnboardingGuidance.suggestions(for: setup)
    XCTAssertEqual(suggestions.dropFirst().first, "Switch to Español")
    XCTAssertFalse(
      SBPostOnboardingGuidance.suggestions(for: SBSetupSnapshot()).contains { $0.hasPrefix("Switch to") },
      "No mismatch, no switch chip")
  }

  func testConnectedContextConnectorsProduceTheirOwnQuestions() {
    var setup = SBSetupSnapshot()
    setup.connectedContextIDs = ["calendar"]
    XCTAssertTrue(SBPostOnboardingGuidance.suggestions(for: setup).contains("What's on my calendar today?"))

    setup.connectedContextIDs = ["gmail"]
    XCTAssertTrue(
      SBPostOnboardingGuidance.suggestions(for: setup).contains("What email follow-ups matter most today?"))

    setup.connectedContextIDs = ["files"]
    XCTAssertTrue(
      SBPostOnboardingGuidance.suggestions(for: setup).contains("What am I working on, based on my files?"))

    setup.connectedContextIDs = ["applenotes"]
    XCTAssertTrue(SBPostOnboardingGuidance.suggestions(for: setup).contains("Summarize my recent notes."))
  }

  func testConnectedAgentIsNamedInItsSuggestion() {
    var setup = SBSetupSnapshot()
    setup.connectedAgentNames = ["Claude Code", "Codex"]

    XCTAssertTrue(
      SBPostOnboardingGuidance.suggestions(for: setup).contains("What can Claude Code do for me?"),
      "A connected agent should be offered by its real name")
  }

  func testDisconnectedAgentIsNeverNamed() {
    let suggestions = SBPostOnboardingGuidance.suggestions(for: SBSetupSnapshot())

    XCTAssertFalse(suggestions.contains { $0.contains("do for me?") })
  }

  // MARK: - Role tailoring

  func testFounderGetsATailoredQuestionWithNoConnectorDependency() {
    var setup = SBSetupSnapshot()
    setup.role = "Founder"

    XCTAssertEqual(SBPostOnboardingGuidance.roleQuestion(for: setup), "What did I commit to this week?")
    XCTAssertTrue(SBPostOnboardingGuidance.suggestions(for: setup).contains("What did I commit to this week?"))
  }

  func testSalesFollowUpQuestionRequiresAPeopleBearingConnector() {
    var setup = SBSetupSnapshot()
    setup.role = "Sales"

    XCTAssertNil(
      SBPostOnboardingGuidance.roleQuestion(for: setup),
      "'Who should I follow up with' is unanswerable without Gmail or Calendar")

    setup.connectedContextIDs = ["calendar"]
    XCTAssertEqual(SBPostOnboardingGuidance.roleQuestion(for: setup), "Who should I follow up with today?")
  }

  func testEngineerQuestionRequiresFilesOrScreen() {
    var setup = SBSetupSnapshot()
    setup.role = "Engineer"

    XCTAssertNil(SBPostOnboardingGuidance.roleQuestion(for: setup))

    setup.canSeeScreen = true
    XCTAssertEqual(SBPostOnboardingGuidance.roleQuestion(for: setup), "What was I working on last?")

    setup.canSeeScreen = false
    setup.connectedContextIDs = ["files"]
    XCTAssertEqual(SBPostOnboardingGuidance.roleQuestion(for: setup), "What was I working on last?")
  }

  func testFreeTextRoleProducesNoFabricatedQuestion() {
    var setup = SBSetupSnapshot()
    setup.role = "I run a small design studio in Lisbon"

    XCTAssertNil(
      SBPostOnboardingGuidance.roleQuestion(for: setup),
      "An unrecognized free-text role must not be interpolated into a sentence")
  }

  func testRoleMatchingIgnoresCaseAndSurroundingWhitespace() {
    var setup = SBSetupSnapshot()
    setup.role = "  student  "

    XCTAssertEqual(SBPostOnboardingGuidance.roleQuestion(for: setup), "What should I study today?")
  }

  // MARK: - Shape

  func testSuggestionsAreCappedAndDeduplicated() {
    var setup = SBSetupSnapshot()
    setup.role = "Founder"
    setup.canSeeScreen = true
    setup.connectedContextIDs = ["calendar", "gmail", "files", "applenotes"]
    setup.connectedAgentNames = ["Codex"]

    let suggestions = SBPostOnboardingGuidance.suggestions(for: setup)

    XCTAssertEqual(suggestions.count, SBPostOnboardingGuidance.maxSuggestions)
    XCTAssertEqual(Set(suggestions).count, suggestions.count, "Suggestions must not repeat")
    XCTAssertEqual(
      suggestions.first, HomeSuggestionComposer.universalFirstQuestion,
      "The universal question keeps the first slot, matching the home ask bar")
  }

  func testEverySuggestionFitsTheHomeChipComposer() {
    var setup = SBSetupSnapshot()
    setup.role = "Founder"
    setup.canSeeScreen = true
    setup.connectedContextIDs = ["calendar", "gmail", "files", "applenotes"]
    setup.connectedAgentNames = ["Claude Code"]

    // The saved suggestions are also fed to the home ask bar via
    // HomeSuggestionComposer, which silently drops anything over its chip
    // budget. A suggestion that cannot survive that trip is dead weight.
    for suggestion in SBPostOnboardingGuidance.suggestions(for: setup) {
      XCTAssertLessThanOrEqual(
        suggestion.count, HomeSuggestionComposer.maxPersonalizedLength,
        "\(suggestion) is too long for the home suggestion chips")
    }
  }

  // MARK: - Orientation cues

  func testMenuBarCueIsAlwaysPresent() {
    let cues = SBPostOnboardingGuidance.orientationCues(
      openShortcutTokens: [], talkShortcutTokens: [], setup: SBSetupSnapshot())

    XCTAssertEqual(cues.first?.id, "menubar", "Where the app lives must be the first thing said")
  }

  func testShortcutCueRendersTheUsersRealChord() {
    var setup = SBSetupSnapshot()
    setup.canHear = true

    let cues = SBPostOnboardingGuidance.orientationCues(
      openShortcutTokens: ["⌘", "↩"], talkShortcutTokens: ["⌥"], setup: setup)

    XCTAssertEqual(cues.first { $0.id == "open" }?.keys, ["⌘", "↩"])
    XCTAssertEqual(cues.first { $0.id == "talk" }?.keys, ["⌥"])
  }

  func testUnsetShortcutProducesNoCue() {
    var setup = SBSetupSnapshot()
    setup.canHear = true

    let cues = SBPostOnboardingGuidance.orientationCues(
      openShortcutTokens: [], talkShortcutTokens: ["  "], setup: setup)

    XCTAssertNil(cues.first { $0.id == "open" }, "An unset chord must not be presented as an instruction")
    XCTAssertNil(cues.first { $0.id == "talk" })
  }

  func testHoldToTalkIsNotOfferedWithoutAMicrophone() {
    var setup = SBSetupSnapshot()
    setup.canHear = false

    let cues = SBPostOnboardingGuidance.orientationCues(
      openShortcutTokens: ["⌘", "O"], talkShortcutTokens: ["⌥"], setup: setup)

    XCTAssertNil(
      cues.first { $0.id == "talk" },
      "Telling a user to hold-to-talk with the mic denied teaches a gesture that does nothing")
    XCTAssertEqual(cues.first { $0.id == "listening" }?.symbol, "mic.slash")
  }

  func testListeningCueReflectsTheChosenCaptureMode() {
    var setup = SBSetupSnapshot()
    setup.canHear = true

    setup.listening = .always
    XCTAssertEqual(
      SBPostOnboardingGuidance.listeningCue(for: setup).title,
      "I'm listening now, and I'll remember what matters.")

    setup.listening = .meetingsOnly
    XCTAssertEqual(
      SBPostOnboardingGuidance.listeningCue(for: setup).title,
      "I'll start listening when a call starts.")
  }

  func testOffMeansListeningDisabled() {
    XCTAssertEqual(
      SBSetupSnapshot.Listening(audioRecordingModeRaw: "off", canHear: true),
      .disabled)

    var setup = SBSetupSnapshot()
    setup.canHear = true
    setup.listening = .disabled

    let cue = SBPostOnboardingGuidance.listeningCue(for: setup)
    XCTAssertEqual(cue.title, "I can't hear yet. Turn on the microphone in Settings whenever you want me to.")
  }

  func testUnavailableMicrophoneProducesDisabledListeningCue() {
    let setup = SBSetupSnapshot()

    XCTAssertEqual(
      SBSetupSnapshot.Listening(audioRecordingModeRaw: "always", canHear: false),
      .disabled)
    XCTAssertEqual(SBPostOnboardingGuidance.listeningCue(for: setup).symbol, "mic.slash")
  }
}
