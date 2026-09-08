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

  func testSetupSnapshotReportsAudioRecordingOff() {
    let model = makeModel()
    appState?.hasMicrophonePermission = true
    let previousMode = AssistantSettings.shared.audioRecordingMode
    AssistantSettings.shared.audioRecordingMode = .off
    defer { AssistantSettings.shared.audioRecordingMode = previousMode }

    XCTAssertEqual(model.postOnboardingSetup.listening, .disabled)
  }

  func testSetupSnapshotRejectsStaleOrBrokenScreenCapture() {
    let model = makeModel()
    appState?.hasScreenRecordingPermission = true
    model.scrState = .on

    XCTAssertTrue(model.postOnboardingSetup.canSeeScreen)

    appState?.isScreenRecordingStale = true
    XCTAssertFalse(
      model.postOnboardingSetup.canSeeScreen,
      "A stale TCC grant must not unlock a screen question")

    appState?.isScreenRecordingStale = false
    appState?.isScreenCaptureKitBroken = true
    XCTAssertFalse(
      model.postOnboardingSetup.canSeeScreen,
      "A broken ScreenCaptureKit path must not unlock a screen question")
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
    XCTAssertTrue(saved.contains(DayZeroChips.summarizeScreen))
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

  func testCaptureChoiceAdvancesToOptionalReferralBeforeCompletion() {
    let model = makeConfiguredModel()
    let previousMode = AssistantSettings.shared.audioRecordingMode
    let previousCompletion = appState?.hasCompletedOnboarding ?? false
    appState?.hasCompletedOnboarding = false
    defer {
      AssistantSettings.shared.audioRecordingMode = previousMode
      appState?.hasCompletedOnboarding = previousCompletion
    }

    model.capture(SBOnboardingModel.defaultCaptureSelection)

    XCTAssertEqual(model.step, .referral)
    XCTAssertEqual(
      UserDefaults.standard.integer(forKey: SBOnboardingModel.resumeStepKey),
      SBOnboardingModel.Step.referral.rawValue)
    XCTAssertFalse(try XCTUnwrap(appState).hasCompletedOnboarding)
  }

  func testReferralRewardCopyStaysPlanAgnostic() {
    let model = makeModel()

    XCTAssertEqual(
      model.message(for: .referral),
      "Want to invite a friend? They'll get one free month.")
  }

  func testSkippedSetupStillProducesAnswerableGuidance() {
    let model = makeModel()

    model.skip()

    let saved = PostOnboardingPromptSuggestions.suggestions()
    XCTAssertEqual(
      saved,
      [HomeSuggestionComposer.universalFirstQuestion, SBPostOnboardingGuidance.teachMeDraft],
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

    PostOnboardingPromptSuggestions.consume()

    XCTAssertFalse(PostOnboardingPromptSuggestions.shouldArmPopup())
    XCTAssertFalse(PostOnboardingPromptSuggestions.shouldShowPopup)
    XCTAssertTrue(PostOnboardingPromptSuggestions.isDismissed)
  }

  /// The flag alone must never raise an empty popup — that is the shape the first half of this bug
  /// shipped in, and it renders as a titled card with nothing in it.
  func testTheFlagAloneDoesNotArmAnEmptyPopup() {
    PostOnboardingPromptSuggestions.shouldShowPopup = true

    XCTAssertTrue(PostOnboardingPromptSuggestions.suggestions().isEmpty, "Precondition")
    XCTAssertFalse(PostOnboardingPromptSuggestions.shouldArmPopup())
  }

  // MARK: - The orientation cue describes the window the user actually has

  /// The orientation cue must describe the window the user actually has. It described click-away
  /// dismissal for as long as the shell hid itself on deactivation; the shell now stays open when you
  /// switch apps, and a cue promising it disappears is worse than no cue.
  func testTheMenuBarCueDescribesAWindowThatStaysOpenAndNamesTheWayBack() throws {
    let cues = SBPostOnboardingGuidance.orientationCues(
      openShortcutTokens: ["⌃", "⌘", "O"], talkShortcutTokens: [], setup: SBSetupSnapshot())
    let menubar = try XCTUnwrap(cues.first { $0.id == "menubar" })
    let title = menubar.title.lowercased()

    XCTAssertFalse(
      title.contains("clos"),
      "there is no close button on this window, and describing one is how the first cue went stale")
    XCTAssertFalse(
      title.contains("put me away") || title.contains("click the desktop"),
      "the shell no longer dismisses itself when another app takes focus")
    XCTAssertTrue(
      title.contains("stay open"),
      "the cue must say the window survives switching apps — that is the behaviour change users see")
    XCTAssertTrue(
      title.contains("menu bar"),
      "the always-available way back must be named — the chord cue is conditional, this one is not")
  }

  /// Whatever chord the user actually picked, never a hardcoded one.
  func testTheOpenCueCarriesTheUsersOwnChord() throws {
    let cues = SBPostOnboardingGuidance.orientationCues(
      openShortcutTokens: ["⌘", "J"], talkShortcutTokens: [], setup: SBSetupSnapshot())

    XCTAssertEqual(try XCTUnwrap(cues.first { $0.id == "open" }).keys, ["⌘", "J"])
  }

  /// A user who set no chord gets no chord cue, so the menu-bar sentence is then the *only* thing
  /// standing between them and a shell they dismissed with no idea how to get it back.
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
