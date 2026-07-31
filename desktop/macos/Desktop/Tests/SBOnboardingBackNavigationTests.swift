import XCTest

@testable import Omi_Computer

@MainActor
final class SBOnboardingBackNavigationTests: XCTestCase {
  private let resumeStepKey = "sbOnboardingResumeStep"

  override func setUp() {
    super.setUp()
    UserDefaults.standard.removeObject(forKey: resumeStepKey)
    UserDefaults.standard.removeObject(forKey: DefaultsKey.onboardingHowDidYouHearSource)
    UserDefaults.standard.removeObject(forKey: DefaultsKey.onboardingRole)
  }

  override func tearDown() {
    UserDefaults.standard.removeObject(forKey: resumeStepKey)
    UserDefaults.standard.removeObject(forKey: DefaultsKey.onboardingHowDidYouHearSource)
    UserDefaults.standard.removeObject(forKey: DefaultsKey.onboardingRole)
    super.tearDown()
  }

  func testBackFromPermissionsRetractsTheCurrentExchangeAndClearsRole() {
    let model = SBOnboardingModel(
      appState: AppState(), chatProvider: ChatProvider(), onComplete: nil)
    UserDefaults.standard.set("Student", forKey: DefaultsKey.onboardingRole)
    model.role = "Student"
    model.roleDraft = "Student"
    model.thread = [
      .init(isOmi: true, text: "What do your days look like?"),
      .init(isOmi: false, text: "Student"),
      .init(isOmi: true, text: "Let's give me senses."),
    ]
    model.step = .mic

    model.goBack()

    XCTAssertEqual(model.step, .role)
    XCTAssertNil(model.role)
    XCTAssertEqual(model.roleDraft, "")
    XCTAssertNil(UserDefaults.standard.object(forKey: DefaultsKey.onboardingRole))
    XCTAssertEqual(model.thread.map(\.text), ["What do your days look like?"])
    XCTAssertTrue(model.showWidget)
    XCTAssertEqual(
      UserDefaults.standard.integer(forKey: SBOnboardingModel.resumeStepKey),
      SBOnboardingModel.Step.role.rawValue)
  }

  func testBackToLanguageClearsItsPreviousChoiceWithoutAppendingMessages() {
    let model = SBOnboardingModel(
      appState: AppState(), chatProvider: ChatProvider(), onComplete: nil)
    model.languageDraft = "Spanish"
    model.thread = [
      .init(isOmi: true, text: SBOnboardingLanguageCopy.question),
      .init(isOmi: false, text: "Spanish"),
      .init(isOmi: true, text: "What do your days look like?"),
    ]
    model.step = .role

    model.goBack()

    XCTAssertEqual(model.step, .language)
    XCTAssertEqual(model.languageDraft, "")
    XCTAssertEqual(model.thread.map(\.text), [SBOnboardingLanguageCopy.question])
  }

  func testBackSkipsPermissionsThatWereNeverDisplayed() {
    let model = SBOnboardingModel(
      appState: AppState(), chatProvider: ChatProvider(), onComplete: nil)
    UserDefaults.standard.set("Student", forKey: DefaultsKey.onboardingRole)
    model.role = "Student"
    model.roleDraft = "Student"
    model.thread = [
      .init(isOmi: true, text: "What do your days look like?"),
      .init(isOmi: false, text: "Student"),
      .init(isOmi: true, text: "Let me read your files."),
    ]
    model.displayedSteps = [.role, .files]
    model.step = .files

    model.goBack()

    XCTAssertEqual(model.step, .role)
    XCTAssertNil(model.role)
    XCTAssertEqual(model.thread.map(\.text), ["What do your days look like?"])
  }

  func testCancelledStreamCannotRestoreTextAfterBack() async {
    var continuation: AsyncStream<Void>.Continuation?
    let pauses = AsyncStream<Void> { continuation = $0 }
    let model = SBOnboardingModel(
      appState: AppState(),
      chatProvider: ChatProvider(),
      streamSleeper: { _ in
        for await _ in pauses {
          return
        }
      },
      onComplete: nil)
    model.step = .name
    model.streamMessage(for: .name)
    await Task.yield()

    model.goBack()
    continuation?.yield()
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
