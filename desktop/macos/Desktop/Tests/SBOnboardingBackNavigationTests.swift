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

  func testBackFromPermissionsReturnsToRoleAndPreservesSelectedRole() {
    let model = SBOnboardingModel(
      appState: AppState(), chatProvider: ChatProvider(), onComplete: nil)
    UserDefaults.standard.set("Student", forKey: DefaultsKey.onboardingRole)
    model.step = .mic

    model.goBack()

    XCTAssertEqual(model.step, .role)
    XCTAssertEqual(model.role, "Student")
    XCTAssertEqual(
      UserDefaults.standard.integer(forKey: SBOnboardingModel.resumeStepKey),
      SBOnboardingModel.Step.role.rawValue)
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
