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

  // MARK: - The orientation cue describes the window the user actually has

  /// The cue used to read "I live in your menu bar. Closing this window doesn't stop me." Both
  /// halves of the second sentence were wrong: the window has no close button (`ShellWindowChrome`
  /// hides all three traffic lights), and completing onboarding turns the shell into a `.summoned`
  /// panel with `hidesOnDeactivate = true`. So the first click into another app made the whole
  /// window disappear, having just been told the opposite about a control that isn't there.
  func testTheMenuBarCuePreparesTheUserForTheWindowDisappearing() throws {
    let cues = SBPostOnboardingGuidance.orientationCues(
      openShortcutTokens: ["⌃", "⌘", "O"], talkShortcutTokens: [], setup: SBSetupSnapshot())
    let menubar = try XCTUnwrap(cues.first { $0.id == "menubar" })

    XCTAssertFalse(
      menubar.title.lowercased().contains("clos"),
      "there is no close button on this window, and describing one is how the old cue went stale")
    XCTAssertTrue(
      menubar.title.lowercased().contains("menu bar"),
      "the always-available way back must be named — the chord cue is conditional, this one is not")
  }

  /// Whatever chord the user actually picked, never a hardcoded one.
  func testTheOpenCueCarriesTheUsersOwnChord() throws {
    let cues = SBPostOnboardingGuidance.orientationCues(
      openShortcutTokens: ["⌘", "J"], talkShortcutTokens: [], setup: SBSetupSnapshot())

    XCTAssertEqual(try XCTUnwrap(cues.first { $0.id == "open" }).keys, ["⌘", "J"])
  }

  /// A user who set no chord gets no chord cue, so the menu-bar sentence is then the *only* thing
  /// standing between them and a window that has vanished with no explanation.
  func testWithNoChordTheMenuBarCueIsStillTheWayBack() {
    let cues = SBPostOnboardingGuidance.orientationCues(
      openShortcutTokens: [], talkShortcutTokens: [], setup: SBSetupSnapshot())

    XCTAssertNil(cues.first { $0.id == "open" })
    XCTAssertTrue(cues.contains { $0.id == "menubar" && $0.title.lowercased().contains("menu bar") })
  }

  // MARK: - The screen step discloses what granting it starts

  /// `complete()` sets `screenAnalysisEnabled = true` unconditionally and Rewind then captures for
  /// as long as the app runs. The step used to say only "so I can help with whatever you're looking
  /// at", which reads as an on-demand glance; the app stated the truth once, in Rewind's own empty
  /// state, which a user reaches days later. These assertions are on the disclosure's substance
  /// rather than its wording: it must say that capture is ongoing, name the feature so the archive
  /// is findable, and say it can be turned off.
  func testTheScreenStepSaysCaptureIsOngoingNamedAndReversible() {
    let model = makeModel()

    let message = model.message(for: .screen).lowercased()

    XCTAssertTrue(message.contains("every few seconds"), "an on-demand reading of this step is the whole bug")
    XCTAssertTrue(message.contains("rewind"), "the archive is unfindable if the step never names it")
    XCTAssertTrue(message.contains("turn it off"), "a capability this consequential must be presented as reversible")
  }

  /// The local claim is scoped to the images on purpose: `RewindStorage` keeps them under
  /// Application Support and nothing uploads them, but `ScreenActivitySyncService` does sync their
  /// OCR text and embeddings to the backend. An unqualified "it stays on this Mac" would be false,
  /// and a false reassurance here is worse than none.
  func testTheScreenStepDoesNotClaimEverythingStaysLocal() {
    let model = makeModel()

    let message = model.message(for: .screen)

    XCTAssertFalse(message.contains("Nothing leaves"))
    XCTAssertFalse(message.contains("stays private"))
    if message.contains("stay on this Mac") {
      XCTAssertTrue(
        message.contains("pictures stay on this Mac"),
        "only the images are local; the claim has to name what it covers")
    }
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
