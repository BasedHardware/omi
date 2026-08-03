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
}
