import XCTest

@testable import Omi_Computer

// The defaults `PostOnboardingPromptSuggestions` owns, plus the SB resume key.
// Free constants rather than members because `setUp`/`tearDown` are nonisolated
// overrides and cannot reach main-actor-isolated state.
private let guidanceSuggestionsKey = "postOnboardingPromptSuggestions"
private let guidanceShowPopupKey = "showPostOnboardingPromptPopup"
private let guidanceDismissedKey = "dismissedPostOnboardingPromptSuggestions"
private let sbOnboardingResumeStepKey = "sbOnboardingResumeStep"

private func clearGuidanceDefaults() {
  UserDefaults.standard.removeObject(forKey: guidanceSuggestionsKey)
  UserDefaults.standard.removeObject(forKey: guidanceShowPopupKey)
  UserDefaults.standard.removeObject(forKey: guidanceDismissedKey)
}

/// Regression coverage for the orphaned post-onboarding guidance surface.
///
/// `DashboardPage` gates its "try asking" popup and suggestion banner on
/// `PostOnboardingPromptSuggestions.shouldShowPopup && !suggestions.isEmpty`,
/// and `ChatProvider.presentOnboardingOpener()` builds its starter chips from
/// the same saved array. Nothing in the live Second Brain flow ever wrote it —
/// `save(_:)` was reachable only from the retired paged-intro onboarding — so
/// the array stayed empty, the flag stayed false, and a user who finished setup
/// was handed a silent app with no next step.
///
/// These tests drive the real exit paths and assert the persisted outcome.
@MainActor
final class SBPostOnboardingGuidanceWiringTests: XCTestCase {

  override nonisolated func setUp() {
    super.setUp()
    clearGuidanceDefaults()
  }

  override nonisolated func tearDown() {
    clearGuidanceDefaults()
    UserDefaults.standard.removeObject(forKey: sbOnboardingResumeStepKey)
    UserDefaults.standard.removeObject(forKey: DefaultsKey.onboardingJustCompleted)
    super.tearDown()
  }

  /// `SBOnboardingModel` holds `appState` `unowned` (the real owner is the view
  /// hierarchy), so the test case has to be the owner here or the model reads a
  /// destroyed reference.
  private var appState: AppState?
  private var chatProvider: ChatProvider?

  private func makeModel() -> SBOnboardingModel {
    let appState = AppState()
    let chatProvider = ChatProvider()
    self.appState = appState
    self.chatProvider = chatProvider
    return SBOnboardingModel(appState: appState, chatProvider: chatProvider, onComplete: nil)
  }

  /// A model whose setup answers are the ones a real run would have produced:
  /// Screen Recording granted, Calendar connected, Gmail skipped, one agent
  /// connected and one merely installed.
  private func makeConfiguredModel() -> SBOnboardingModel {
    let model = makeModel()
    appState?.hasScreenRecordingPermission = true
    model.role = "Founder"
    model.contextStates = ["calendar": "on", "gmail": "idle", "applenotes": "unavailable"]
    model.agentStates = ["claudeCode": "on", "codex": "idle"]
    return model
  }

  // MARK: - The snapshot only claims what onboarding observed

  func testSetupSnapshotCountsOnlyConnectorsObservedConnected() {
    let model = makeConfiguredModel()

    let setup = model.postOnboardingSetup

    XCTAssertEqual(setup.connectedContextIDs, ["calendar"])
    XCTAssertEqual(setup.connectedAgentNames, ["Claude Code"])
    XCTAssertTrue(setup.canSeeScreen)
    XCTAssertEqual(setup.role, "Founder")
  }

  func testSetupSnapshotReportsDeniedPermissionsAsDenied() {
    let model = makeModel()

    let setup = model.postOnboardingSetup

    XCTAssertFalse(setup.canSeeScreen)
    XCTAssertTrue(setup.connectedContextIDs.isEmpty)
    XCTAssertTrue(setup.connectedAgentNames.isEmpty)
  }

  // MARK: - Both exit paths produce the guidance

  func testSkipSavesSetupAwareGuidanceAndArmsTheDashboardSurfaces() {
    let model = makeConfiguredModel()
    XCTAssertTrue(
      PostOnboardingPromptSuggestions.suggestions().isEmpty,
      "Precondition: nothing saved before the exit path runs")

    model.skip()

    let saved = PostOnboardingPromptSuggestions.suggestions()
    XCTAssertEqual(saved, SBPostOnboardingGuidance.suggestions(for: model.postOnboardingSetup))
    XCTAssertFalse(saved.isEmpty, "The dashboard popup and banner are gated on this being non-empty")
    XCTAssertTrue(saved.contains("What's on my screen right now?"))
    XCTAssertTrue(saved.contains("What's on my calendar today?"))
    XCTAssertTrue(PostOnboardingPromptSuggestions.shouldShowPopup)
    XCTAssertFalse(PostOnboardingPromptSuggestions.isDismissed)
  }

  func testCompletionHandoffSavesSetupAwareGuidance() {
    let model = makeConfiguredModel()

    // The exact call `complete(startListening:)` makes; the heavier service
    // starts around it (capture, agent pipeline, login item) are deliberately
    // not driven here so the test stays hermetic.
    model.finishOnboardingHandoff(clearOnboardingChatFlag: true)

    let saved = PostOnboardingPromptSuggestions.suggestions()
    XCTAssertEqual(saved, SBPostOnboardingGuidance.suggestions(for: model.postOnboardingSetup))
    XCTAssertTrue(PostOnboardingPromptSuggestions.shouldShowPopup)
  }

  func testSkippedSetupStillProducesAnswerableGuidance() {
    let model = makeModel()

    model.skip()

    let saved = PostOnboardingPromptSuggestions.suggestions()
    XCTAssertEqual(
      saved,
      [HomeSuggestionComposer.universalFirstQuestion, SBPostOnboardingGuidance.universalFallback],
      "A user who skipped everything still needs a next step, and it must not name a skipped connector")
    XCTAssertTrue(PostOnboardingPromptSuggestions.shouldShowPopup)
  }

  // MARK: - The shell can arm the popup from what onboarding saved

  /// The second half of this stranding. Once `save(_:)` had a live caller the guidance was still
  /// invisible, because the only thing that armed the popup was `DashboardPage.onAppear` — and
  /// `DashboardPage` is Home only behind `useLegacyHomeDesign`, which is off by default. Onboarding
  /// wrote the array and set the flag; nothing on the shipped Home read either.
  ///
  /// `shouldArmPopup()` is the condition as a value, so the shell can ask it from wherever the
  /// overlay lives and a page that stops being Home cannot take the trigger with it.
  func testFinishingOnboardingLeavesThePopupArmedForTheShell() {
    let model = makeConfiguredModel()
    XCTAssertFalse(
      PostOnboardingPromptSuggestions.shouldArmPopup(),
      "Precondition: nothing to show before onboarding saves anything")

    model.skip()

    XCTAssertTrue(
      PostOnboardingPromptSuggestions.shouldArmPopup(),
      "A user who just finished setup must be offered a next step on the Home they actually have")
  }

  func testDismissingTheGuidanceDisarmsItForGood() {
    let model = makeConfiguredModel()
    model.skip()
    XCTAssertTrue(PostOnboardingPromptSuggestions.shouldArmPopup())

    // What the popup's dismiss handler persists.
    PostOnboardingPromptSuggestions.shouldShowPopup = false
    PostOnboardingPromptSuggestions.isDismissed = true

    XCTAssertFalse(PostOnboardingPromptSuggestions.shouldArmPopup())
  }

  /// The flag alone must never raise an empty popup — that is the shape the first half of this bug
  /// shipped in, and it renders as a titled card with nothing in it.
  func testTheFlagAloneDoesNotArmAnEmptyPopup() {
    PostOnboardingPromptSuggestions.shouldShowPopup = true

    XCTAssertTrue(PostOnboardingPromptSuggestions.suggestions().isEmpty, "Precondition")
    XCTAssertFalse(PostOnboardingPromptSuggestions.shouldArmPopup())
  }

  // MARK: - Ordering: saved before anything reads it

  func testOpenerStartersAreBuiltFromTheGuidanceSavedInTheSameHandoff() throws {
    let model = makeConfiguredModel()

    model.skip()

    let opener = try XCTUnwrap(
      model.chatProvider.onboardingOpener, "Completing onboarding must present the Chat tab opener")

    // Recompute with the production composers from the same live inputs. If the
    // guidance were saved *after* `presentOnboardingOpener()`, the opener would
    // have been composed against an empty onboarding array and these would
    // diverge for any account with fewer than two personalized questions —
    // which is every account on the run this feature exists for.
    let expectedStarters = OnboardingOpenerComposer.starters(
      meetings: [],
      baseStarters: HomeSuggestionComposer.compose(
        personalized: HomeSuggestionsStore.shared.personalizedQuestions,
        onboarding: PostOnboardingPromptSuggestions.suggestions()))

    XCTAssertEqual(opener.starters, expectedStarters)
  }
}
