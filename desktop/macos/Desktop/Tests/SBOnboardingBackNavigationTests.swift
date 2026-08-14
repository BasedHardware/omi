import XCTest

@testable import Omi_Computer

@MainActor
final class SBOnboardingBackNavigationTests: XCTestCase {
  private let resumeStepKey = "sbOnboardingResumeStep"
  private var voiceLanguages: [String] = []
  private var hasExplicitVoiceLanguages = false

  override func setUp() async throws {
    voiceLanguages = AssistantSettings.shared.voiceLanguages
    hasExplicitVoiceLanguages = AssistantSettings.shared.hasExplicitVoiceLanguages
    UserDefaults.standard.removeObject(forKey: resumeStepKey)
    UserDefaults.standard.removeObject(forKey: DefaultsKey.onboardingHowDidYouHearSource)
    UserDefaults.standard.removeObject(forKey: DefaultsKey.onboardingRole)
  }

  override func tearDown() async throws {
    AssistantSettings.shared.voiceLanguages = hasExplicitVoiceLanguages ? voiceLanguages : []
    UserDefaults.standard.removeObject(forKey: resumeStepKey)
    UserDefaults.standard.removeObject(forKey: DefaultsKey.onboardingHowDidYouHearSource)
    UserDefaults.standard.removeObject(forKey: DefaultsKey.onboardingRole)
  }

  func testBackFromPermissionsRetractsTheCurrentExchangeAndPreservesRole() {
    let model = SBOnboardingModel(
      appState: AppState(), chatProvider: ChatProvider(), onComplete: nil)
    let rolePrompt = model.message(for: .role)
    UserDefaults.standard.set("Student", forKey: DefaultsKey.onboardingRole)
    model.role = "Student"
    model.roleDraft = "Student"
    model.thread = [
      .init(isOmi: true, text: rolePrompt),
      .init(isOmi: false, text: "Student"),
      .init(isOmi: true, text: model.message(for: .mic)),
    ]
    model.step = .mic

    model.goBack()

    XCTAssertEqual(model.step, .role)
    XCTAssertEqual(model.role, "Student")
    XCTAssertEqual(model.roleDraft, "Student")
    XCTAssertEqual(UserDefaults.standard.string(forKey: DefaultsKey.onboardingRole), "Student")
    XCTAssertEqual(model.thread.map(\.text), [rolePrompt])
    XCTAssertTrue(model.showWidget)
    XCTAssertEqual(
      UserDefaults.standard.integer(forKey: SBOnboardingModel.resumeStepKey),
      SBOnboardingModel.Step.role.rawValue)
  }

  func testBackToLanguageKeepsItsActiveSelectionWithoutAppendingMessages() {
    let model = SBOnboardingModel(
      appState: AppState(), chatProvider: ChatProvider(), onComplete: nil)
    model.languageDraft = "Spanish"
    AssistantSettings.shared.voiceLanguages = ["es"]
    model.thread = [
      .init(isOmi: true, text: SBOnboardingLanguageCopy.question),
      .init(isOmi: false, text: "Spanish"),
      .init(isOmi: true, text: model.message(for: .role)),
    ]
    model.step = .role

    model.goBack()

    XCTAssertEqual(model.step, .language)
    XCTAssertEqual(model.languageDraft, "Spanish")
    XCTAssertEqual(AssistantSettings.shared.voiceLanguages, ["es"])
    XCTAssertEqual(model.thread.map(\.text), [SBOnboardingLanguageCopy.question])
  }

  func testResumingAfterLanguageSelectionRehydratesItsDraft() {
    AssistantSettings.shared.voiceLanguages = ["es"]
    UserDefaults.standard.set(SBOnboardingModel.Step.role.rawValue, forKey: resumeStepKey)
    let appState = AppState()
    let chatProvider = ChatProvider()
    let model = SBOnboardingModel(
      appState: appState, chatProvider: chatProvider, onComplete: nil)

    model.begin()

    XCTAssertEqual(model.languageDraft, "Spanish")
    model.streamTask?.cancel()
  }

  func testBackSkipsPermissionsThatWereNeverDisplayed() {
    let model = SBOnboardingModel(
      appState: AppState(), chatProvider: ChatProvider(), onComplete: nil)
    let rolePrompt = model.message(for: .role)
    UserDefaults.standard.set("Student", forKey: DefaultsKey.onboardingRole)
    model.role = "Student"
    model.roleDraft = "Student"
    model.thread = [
      .init(isOmi: true, text: rolePrompt),
      .init(isOmi: false, text: "Student"),
      .init(isOmi: true, text: model.message(for: .files)),
    ]
    model.displayedSteps = [.role, .files]
    model.step = .files

    model.goBack()

    XCTAssertEqual(model.step, .role)
    XCTAssertEqual(model.role, "Student")
    XCTAssertEqual(model.roleDraft, "Student")
    XCTAssertEqual(model.thread.map(\.text), [rolePrompt])
  }

  func testBackDuringSkippedPermissionStreamReturnsToTheLastDisplayedStep() async {
    var continuation: AsyncStream<Void>.Continuation?
    let pauses = AsyncStream<Void> { continuation = $0 }
    let appState = AppState()
    let chatProvider = ChatProvider()
    let model = SBOnboardingModel(
      appState: appState, chatProvider: chatProvider,
      streamSleeper: { _ in
        for await _ in pauses {
          return
        }
      }, onComplete: nil)
    let rolePrompt = model.message(for: .role)
    model.thread = [
      .init(isOmi: true, text: rolePrompt),
      .init(isOmi: false, text: "Student"),
    ]
    model.step = .files
    model.displayedSteps = [.role]

    model.streamMessage(for: .files)
    await Task.yield()
    model.goBack()

    XCTAssertEqual(model.step, .role)
    XCTAssertEqual(model.thread.map(\.text), [rolePrompt])
    XCTAssertTrue(model.showWidget)
    continuation?.yield()
    continuation?.finish()
    await Task.yield()
    await Task.yield()
  }

  func testBackFromFilesRetractsTheFilesPromptAndAnswer() {
    let model = SBOnboardingModel(
      appState: AppState(), chatProvider: ChatProvider(), onComplete: nil)
    model.thread = [
      .init(isOmi: true, text: model.message(for: .role)),
      .init(isOmi: false, text: "Allowed"),
      .init(isOmi: true, text: model.message(for: .files)),
      .init(isOmi: false, text: "Allowed"),
    ]
    model.step = .files
    model.displayedSteps = [.role, .files]

    model.goBack()

    XCTAssertEqual(model.step, .role)
    XCTAssertEqual(model.thread.map(\.text), [model.message(for: .role)])
    XCTAssertTrue(model.showWidget)
  }

  func testReturningToCompletedFilesRestoresItsAnswerOnContinue() {
    let appState = AppState()
    let chatProvider = ChatProvider()
    let model = SBOnboardingModel(
      appState: appState, chatProvider: chatProvider, onComplete: nil)
    model.fdaState = .on
    model.localFileProfileState = .complete(fileCount: 1, memoryCount: 1, deniedFolders: [])
    model.thread = [
      .init(isOmi: true, text: model.message(for: .files)),
      .init(isOmi: false, text: "Allowed"),
      .init(isOmi: true, text: model.message(for: .accessibility)),
      .init(isOmi: false, text: "Skip"),
    ]
    model.step = .accessibility
    model.displayedSteps = [.files, .accessibility]

    model.goBack()
    model.finishFilesStep()

    XCTAssertEqual(
      model.thread.map(\.text),
      [model.message(for: .files), "Allowed"])
    model.streamTask?.cancel()
  }

  func testBackStreamsThePriorPromptWhenResumingWithoutHistory() async {
    var continuation: AsyncStream<Void>.Continuation?
    let pauses = AsyncStream<Void> { continuation = $0 }
    let appState = AppState()
    let chatProvider = ChatProvider()
    let model = SBOnboardingModel(
      appState: appState, chatProvider: chatProvider,
      streamSleeper: { _ in
        for await _ in pauses {
          return
        }
      }, onComplete: nil)
    model.thread = [.init(isOmi: true, text: model.message(for: .role))]
    model.step = .role
    model.displayedSteps = [.role]

    model.goBack()
    await Task.yield()

    XCTAssertEqual(model.step, .language)
    XCTAssertFalse(model.showWidget)
    XCTAssertTrue(model.typing)
    continuation?.yield()
    continuation?.finish()
    await Task.yield()
    await Task.yield()
  }

  func testCancelledStreamCannotRestoreTextAfterBack() async {
    var continuation: AsyncStream<Void>.Continuation?
    let pauses = AsyncStream<Void> { continuation = $0 }
    let appState = AppState()
    let chatProvider = ChatProvider()
    let model = SBOnboardingModel(
      appState: appState,
      chatProvider: chatProvider,
      streamSleeper: { _ in
        for await _ in pauses {
          return
        }
      },
      onComplete: nil)
    model.step = .name
    model.thread = [.init(isOmi: true, text: model.message(for: .promise))]
    model.streamMessage(for: .name)
    await Task.yield()

    model.goBack()
    continuation?.yield()
    await Task.yield()
    await Task.yield()

    XCTAssertNil(model.streamingText)
    XCTAssertFalse(model.typing)
  }

  func testAssistantChoicesAreAlwaysPresentedAsSeparateOptions() {
    let model = SBOnboardingModel(
      appState: AppState(), chatProvider: ChatProvider(), onComplete: nil)

    XCTAssertEqual(
      model.agentRows.map { $0.id },
      ["openclaw", "hermes", "claudeCode", "codex"])
    XCTAssertEqual(
      model.agentRows.map { $0.name },
      ["OpenClaw", "Hermes", "Claude Code", "Codex"])
  }

  func testAssistantTogglePresentationCoversConnectAndFailureStates() {
    XCTAssertEqual(
      SBOnboardingModel.agentTogglePresentation(for: "idle", detail: "runs tasks on your Mac"),
      .init(isOn: false, isDisabled: false, detail: "runs tasks on your Mac"))
    XCTAssertEqual(
      SBOnboardingModel.agentTogglePresentation(for: "connecting", detail: "runs tasks on your Mac"),
      .init(isOn: true, isDisabled: true, detail: "connecting…"))
    XCTAssertEqual(
      SBOnboardingModel.agentTogglePresentation(for: "on", detail: "runs tasks on your Mac"),
      .init(isOn: true, isDisabled: true, detail: "runs tasks on your Mac"))
    XCTAssertEqual(
      SBOnboardingModel.agentTogglePresentation(for: "unavailable", detail: "runs tasks on your Mac"),
      .init(isOn: false, isDisabled: true, detail: "not installed"))
  }

  func testBackPreservesEarlierAcquisitionChoiceAndStopsAtFirstStep() {
    let model = SBOnboardingModel(
      appState: AppState(), chatProvider: ChatProvider(), onComplete: nil)
    model.howHeard = "Friend"
    UserDefaults.standard.set("Friend", forKey: DefaultsKey.onboardingHowDidYouHearSource)
    model.step = .language

    model.goBack()

    XCTAssertEqual(model.step, .howHeard)
    XCTAssertEqual(model.howHeard, "Friend")

    model.step = .promise
    model.goBack()
    XCTAssertEqual(model.step, .promise)
  }

  func testVoiceDemoArmsPTTOnlyAfterBridgeWarmupWhileStillOnDemoStage() async {
    let model = SBOnboardingModel(
      appState: AppState(), chatProvider: ChatProvider(), onComplete: nil)
    model.step = .screenDemo
    var activated = false

    await model.activateScreenDemoPTTAfterBridgeWarmup(
      warmup: { true },
      activate: { activated = true }
    )

    XCTAssertTrue(activated)

    activated = false
    model.step = .screenDemo
    await model.activateScreenDemoPTTAfterBridgeWarmup(
      warmup: {
        model.step = .agents
        return true
      },
      activate: { activated = true }
    )

    XCTAssertFalse(activated, "A late bridge warmup must not arm PTT after navigating away")
  }

  func testVoiceDemoKeepsPTTUnarmedWhenBridgeWarmupFails() async {
    let model = SBOnboardingModel(
      appState: AppState(), chatProvider: ChatProvider(), onComplete: nil)
    model.step = .screenDemo
    var activated = false

    await model.activateScreenDemoPTTAfterBridgeWarmup(
      warmup: { false },
      activate: { activated = true }
    )

    XCTAssertFalse(activated)
    XCTAssertFalse(model.screenDemoPTTReady)
    XCTAssertTrue(model.screenDemoPTTUnavailable)
  }

  func testCustomOpenShortcutRecordsAnArbitraryChord() throws {
    let settings = ShortcutSettings.shared
    let previousShortcut = settings.askOmiShortcut
    let previousEnabled = settings.askOmiEnabled
    defer {
      settings.askOmiShortcut = previousShortcut
      settings.askOmiEnabled = previousEnabled
    }

    let model = SBOnboardingModel(
      appState: AppState(), chatProvider: ChatProvider(), onComplete: nil)
    model.step = .shortcutOpen
    model.beginShortcutRecording(isTalk: false)
    let event = try XCTUnwrap(
      NSEvent.keyEvent(
        with: .keyDown,
        location: .zero,
        modifierFlags: [.control, .option],
        timestamp: 0,
        windowNumber: 0,
        context: nil,
        characters: "p",
        charactersIgnoringModifiers: "p",
        isARepeat: false,
        keyCode: 35
      ))

    XCTAssertTrue(model.recordShortcut(from: event))
    XCTAssertFalse(model.shortcutRecording)
    XCTAssertEqual(model.chosenShortcut?.keyCode, 35)
    XCTAssertEqual(model.chosenShortcut?.modifiers, [.control, .option])
    XCTAssertEqual(settings.askOmiShortcut.keyCode, 35)
    XCTAssertFalse(model.shortcutPressed, "Recording a shortcut must not count as exercising it.")
  }

  func testCustomPushToTalkShortcutRecordsAnArbitraryChord() throws {
    let settings = ShortcutSettings.shared
    let previousShortcut = settings.pttShortcut
    let previousEnabled = settings.pttEnabled
    defer {
      settings.pttShortcut = previousShortcut
      settings.pttEnabled = previousEnabled
    }

    let model = SBOnboardingModel(
      appState: AppState(), chatProvider: ChatProvider(), onComplete: nil)
    model.step = .shortcutTalk
    model.beginShortcutRecording(isTalk: true)
    let modifierDown = try XCTUnwrap(
      NSEvent.keyEvent(
        with: .flagsChanged,
        location: .zero,
        modifierFlags: .command,
        timestamp: 0,
        windowNumber: 0,
        context: nil,
        characters: "",
        charactersIgnoringModifiers: "",
        isARepeat: false,
        keyCode: 55
      ))

    XCTAssertTrue(model.recordShortcut(from: modifierDown))
    XCTAssertTrue(model.shortcutRecording)
    XCTAssertNil(model.chosenShortcut)

    let event = try XCTUnwrap(
      NSEvent.keyEvent(
        with: .keyDown,
        location: .zero,
        modifierFlags: [.command, .shift],
        timestamp: 0,
        windowNumber: 0,
        context: nil,
        characters: "k",
        charactersIgnoringModifiers: "k",
        isARepeat: false,
        keyCode: 40
      ))

    XCTAssertTrue(model.recordShortcut(from: event))
    XCTAssertFalse(model.shortcutRecording)
    XCTAssertEqual(model.chosenShortcut?.keyCode, 40)
    XCTAssertEqual(model.chosenShortcut?.modifiers, [.command, .shift])
    XCTAssertEqual(settings.pttShortcut.keyCode, 40)
  }

  func testCustomPushToTalkModifierOnlyShortcutCompletesOnRelease() throws {
    let settings = ShortcutSettings.shared
    let previousShortcut = settings.pttShortcut
    let previousEnabled = settings.pttEnabled
    defer {
      settings.pttShortcut = previousShortcut
      settings.pttEnabled = previousEnabled
    }

    let model = SBOnboardingModel(
      appState: AppState(), chatProvider: ChatProvider(), onComplete: nil)
    model.step = .shortcutTalk
    model.beginShortcutRecording(isTalk: true)
    let modifierDown = try XCTUnwrap(
      NSEvent.keyEvent(
        with: .flagsChanged,
        location: .zero,
        modifierFlags: .option,
        timestamp: 0,
        windowNumber: 0,
        context: nil,
        characters: "",
        charactersIgnoringModifiers: "",
        isARepeat: false,
        keyCode: 58
      ))
    let modifierUp = try XCTUnwrap(
      NSEvent.keyEvent(
        with: .flagsChanged,
        location: .zero,
        modifierFlags: [],
        timestamp: 0,
        windowNumber: 0,
        context: nil,
        characters: "",
        charactersIgnoringModifiers: "",
        isARepeat: false,
        keyCode: 58
      ))

    XCTAssertTrue(model.recordShortcut(from: modifierDown))
    XCTAssertTrue(model.shortcutRecording)
    XCTAssertTrue(model.recordShortcut(from: modifierUp))
    XCTAssertFalse(model.shortcutRecording)
    XCTAssertEqual(model.chosenShortcut, ShortcutSettings.KeyboardShortcut(modifierOnly: .option))
    XCTAssertEqual(settings.pttShortcut, ShortcutSettings.KeyboardShortcut(modifierOnly: .option))
  }

  func testPresetOpenShortcutRowSelectsItsDisplayedShortcut() throws {
    let settings = ShortcutSettings.shared
    let previousShortcut = settings.askOmiShortcut
    let previousEnabled = settings.askOmiEnabled
    defer {
      settings.askOmiShortcut = previousShortcut
      settings.askOmiEnabled = previousEnabled
    }

    let model = SBOnboardingModel(
      appState: AppState(), chatProvider: ChatProvider(), onComplete: nil)
    model.step = .shortcutOpen
    let option = try XCTUnwrap(model.openShortcutOptions.last)

    model.pickShortcut(option.shortcut, isTalk: false)

    XCTAssertFalse(model.shortcutRecording)
    XCTAssertTrue(model.shortcutPicked)
    XCTAssertEqual(model.chosenShortcut, option.shortcut)
    XCTAssertEqual(settings.askOmiShortcut, option.shortcut)
    XCTAssertTrue(settings.askOmiEnabled)
  }

  func testPresetPushToTalkShortcutRowSelectsItsDisplayedShortcut() throws {
    let settings = ShortcutSettings.shared
    let previousShortcut = settings.pttShortcut
    let previousEnabled = settings.pttEnabled
    defer {
      settings.pttShortcut = previousShortcut
      settings.pttEnabled = previousEnabled
    }

    let model = SBOnboardingModel(
      appState: AppState(), chatProvider: ChatProvider(), onComplete: nil)
    model.step = .shortcutTalk
    let option = try XCTUnwrap(model.talkShortcutOptions.last)

    model.pickShortcut(option.shortcut, isTalk: true)

    XCTAssertFalse(model.shortcutRecording)
    XCTAssertTrue(model.shortcutPicked)
    XCTAssertTrue(model.chosenShortcutIsPTT)
    XCTAssertEqual(model.chosenShortcut, option.shortcut)
    XCTAssertEqual(settings.pttShortcut, option.shortcut)
    XCTAssertTrue(settings.pttEnabled)
  }

  func testShortcutStagesCannotAdvanceUntilSelectedShortcutIsExercised() {
    let settings = ShortcutSettings.shared
    let previousOpenShortcut = settings.askOmiShortcut
    let previousOpenEnabled = settings.askOmiEnabled
    let previousTalkShortcut = settings.pttShortcut
    let previousTalkEnabled = settings.pttEnabled
    defer {
      settings.askOmiShortcut = previousOpenShortcut
      settings.askOmiEnabled = previousOpenEnabled
      settings.pttShortcut = previousTalkShortcut
      settings.pttEnabled = previousTalkEnabled
    }

    let model = SBOnboardingModel(
      appState: AppState(), chatProvider: ChatProvider(), onComplete: nil)

    model.step = .shortcutOpen
    model.pickShortcut(ShortcutSettings.askOmiCommandOShortcut, isTalk: false)
    model.answerShortcutOpen()
    XCTAssertEqual(model.step, .shortcutOpen)

    model.shortcutPressed = true
    model.answerShortcutOpen()
    XCTAssertEqual(model.step, .shortcutTalk)

    model.pickShortcut(ShortcutSettings.KeyboardShortcut(modifierOnly: .option), isTalk: true)
    model.answerShortcutTalk()
    XCTAssertEqual(model.step, .shortcutTalk)

    model.shortcutPressed = true
    model.answerShortcutTalk()
    XCTAssertEqual(model.step, .screenDemo)
  }

  func testFullOnboardingSkipUnlocksOnlyAfterRequiredShortcutStages() {
    let key = SBOnboardingModel.shortcutsCompletedKey
    let previous = UserDefaults.standard.bool(forKey: key)
    defer { UserDefaults.standard.set(previous, forKey: key) }
    UserDefaults.standard.set(false, forKey: key)

    let model = SBOnboardingModel(
      appState: AppState(), chatProvider: ChatProvider(), onComplete: nil)

    model.step = .promise
    XCTAssertFalse(model.canSkipOnboarding)
    model.step = .shortcutOpen
    XCTAssertFalse(model.canSkipOnboarding)
    model.step = .shortcutTalk
    XCTAssertFalse(model.canSkipOnboarding)
    model.step = .screenDemo
    // Without the completion flag, Skip stays hidden even at screenDemo.
    XCTAssertFalse(model.canSkipOnboarding)
    // After completing both shortcut stages, Skip unlocks.
    UserDefaults.standard.set(true, forKey: key)
    XCTAssertTrue(model.canSkipOnboarding)
  }

  func testLegacyResumeStateClampedBackThroughShortcutStages() {
    let resumeKey = SBOnboardingModel.resumeStepKey
    let completedKey = SBOnboardingModel.shortcutsCompletedKey
    let prevResume = UserDefaults.standard.integer(forKey: resumeKey)
    let prevCompleted = UserDefaults.standard.bool(forKey: completedKey)
    defer {
      UserDefaults.standard.set(prevResume, forKey: resumeKey)
      UserDefaults.standard.set(prevCompleted, forKey: completedKey)
    }

    // Simulate a legacy user who persisted a resume state past the shortcut stages
    // before shortcuts were mandatory, without the completion flag.
    UserDefaults.standard.set(SBOnboardingModel.Step.screenDemo.rawValue, forKey: resumeKey)
    UserDefaults.standard.set(false, forKey: completedKey)

    // Hold a strong reference to AppState for the life of the test. SBOnboardingModel
    // stores appState as `unowned`, so a temporary would be deallocated before begin()
    // touches it.
    let appState = AppState()
    let model = SBOnboardingModel(
      appState: appState, chatProvider: ChatProvider(), onComplete: nil)
    model.begin()

    // The model should clamp back to the first shortcut stage, not bypass it.
    XCTAssertEqual(model.step, .shortcutOpen)
    XCTAssertFalse(model.canSkipOnboarding)

    // A legacy resume at exactly shortcutTalk (without the completion flag) is also
    // clamped back to shortcutOpen — completing only Talk would bypass Open Omi.
    UserDefaults.standard.set(SBOnboardingModel.Step.shortcutTalk.rawValue, forKey: resumeKey)
    UserDefaults.standard.set(false, forKey: completedKey)
    let modelMid = SBOnboardingModel(
      appState: appState, chatProvider: ChatProvider(), onComplete: nil)
    modelMid.begin()
    XCTAssertEqual(modelMid.step, .shortcutOpen)

    // A user who genuinely completed shortcuts resumes past them.
    UserDefaults.standard.set(SBOnboardingModel.Step.screenDemo.rawValue, forKey: resumeKey)
    UserDefaults.standard.set(true, forKey: completedKey)
    let model2 = SBOnboardingModel(
      appState: appState, chatProvider: ChatProvider(), onComplete: nil)
    model2.begin()
    XCTAssertGreaterThan(model2.step.rawValue, SBOnboardingModel.Step.shortcutTalk.rawValue)
    XCTAssertTrue(model2.canSkipOnboarding)
  }
}
