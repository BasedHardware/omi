import XCTest

@testable import Omi_Computer

@MainActor
final class SBOnboardingBackNavigationTests: XCTestCase {
  private let resumeStepKey = "sbOnboardingResumeStep"
  // Literals, not `SBOnboardingModel.*`: setUp/tearDown are nonisolated and
  // those constants are main-actor isolated. Mirrors this file's existing style.
  private let resumeSchemaKey = "sbOnboardingResumeStepSchema"
  private let currentResumeSchemaVersion = 3

  override func setUp() {
    super.setUp()
    UserDefaults.standard.removeObject(forKey: resumeStepKey)
    // These tests seed resume values in the *current* `Step` numbering. Without
    // the schema stamp, `begin()` would correctly read them as pre-scenario
    // state and restart at `hello`, so the assertions below would be about a
    // step nobody wrote. Stamping says "this install is already current".
    UserDefaults.standard.set(currentResumeSchemaVersion, forKey: resumeSchemaKey)
  }

  override func tearDown() {
    UserDefaults.standard.removeObject(forKey: resumeStepKey)
    UserDefaults.standard.removeObject(forKey: resumeSchemaKey)
    super.tearDown()
  }

  func testVoiceDemoArmsPTTOnlyAfterBridgeWarmupWhileStillOnDemoStage() async {
    let model = SBOnboardingModel(
      appState: AppState(), chatProvider: ChatProvider(), onComplete: nil)
    model.step = .talk
    model.talkPhase = .demo
    var activated = false

    await model.activateScreenDemoPTTAfterBridgeWarmup(
      warmup: { true },
      activate: { activated = true }
    )

    XCTAssertTrue(activated)

    activated = false
    model.step = .talk
    model.talkPhase = .demo
    await model.activateScreenDemoPTTAfterBridgeWarmup(
      warmup: {
        model.step = .write  // the user pressed Skip while the warmup ran
        return true
      },
      activate: { activated = true }
    )

    XCTAssertFalse(activated, "A late bridge warmup must not arm PTT after navigating away")
  }

  func testVoiceDemoKeepsPTTUnarmedWhenBridgeWarmupFails() async {
    let model = SBOnboardingModel(
      appState: AppState(), chatProvider: ChatProvider(), onComplete: nil)
    model.step = .talk
    model.talkPhase = .demo
    var activated = false

    await model.activateScreenDemoPTTAfterBridgeWarmup(
      warmup: { false },
      activate: { activated = true }
    )

    XCTAssertFalse(activated)
    XCTAssertFalse(model.screenDemoPTTReady)
    XCTAssertTrue(model.screenDemoPTTUnavailable)
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
    model.step = .talk
    model.talkPhase = .shortcut
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
    model.step = .talk
    model.talkPhase = .shortcut
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
    model.step = .talk
    model.talkPhase = .shortcut
    let option = try XCTUnwrap(model.talkShortcutOptions.last)

    model.pickShortcut(option.shortcut, isTalk: true)

    XCTAssertFalse(model.shortcutRecording)
    XCTAssertTrue(model.shortcutPicked)
    XCTAssertTrue(model.chosenShortcutIsPTT)
    XCTAssertEqual(model.chosenShortcut, option.shortcut)
    XCTAssertEqual(settings.pttShortcut, option.shortcut)
    XCTAssertTrue(settings.pttEnabled)
  }

  /// Mirrors the retired two-stage (Open Omi + Talk) shortcut gate: picking a chord is not the
  /// same as exercising it, so the flow must not advance on the pick alone.
  func testTalkShortcutPhaseCannotAdvanceUntilTheSelectedChordIsExercised() {
    let settings = ShortcutSettings.shared
    let previousShortcut = settings.pttShortcut
    let previousEnabled = settings.pttEnabled
    defer {
      settings.pttShortcut = previousShortcut
      settings.pttEnabled = previousEnabled
    }

    // Held for the life of the test: `finishTalkShortcut()` advances into
    // `startScreenDemo()`, which reads `appState` (`unowned` on the model), and
    // an inline `AppState()` temporary is deallocated the moment init returns.
    let appState = AppState()
    let model = SBOnboardingModel(
      appState: appState, chatProvider: ChatProvider(), onComplete: nil)
    model.step = .talk
    model.talkPhase = .shortcut

    model.pickShortcut(ShortcutSettings.KeyboardShortcut(modifierOnly: .option), isTalk: true)
    model.answerShortcutTalk()
    XCTAssertEqual(model.talkPhase, .shortcut, "picking a chord without pressing it must not advance")

    model.shortcutPressed = true
    model.answerShortcutTalk()
    XCTAssertEqual(model.talkPhase, .demo)
  }

  func testFullOnboardingSkipUnlocksOnlyAfterTheTalkChord() {
    let key = SBOnboardingModel.shortcutsCompletedKey
    let previous = UserDefaults.standard.bool(forKey: key)
    defer { UserDefaults.standard.set(previous, forKey: key) }
    UserDefaults.standard.set(false, forKey: key)

    let model = SBOnboardingModel(
      appState: AppState(), chatProvider: ChatProvider(), onComplete: nil)

    model.step = .hello
    XCTAssertFalse(model.canSkipOnboarding)
    model.step = .talk
    XCTAssertFalse(model.canSkipOnboarding, "the talk chord itself is never skippable")
    model.step = .write
    // Without the completion flag, Skip stays hidden even past the talk beat.
    XCTAssertFalse(model.canSkipOnboarding)
    // After completing the talk chord, Skip unlocks.
    UserDefaults.standard.set(true, forKey: key)
    XCTAssertTrue(model.canSkipOnboarding)
  }

  func testResumingAtTalkWithTheChordAlreadyCompletedLandsOnTheDemoPhase() {
    let resumeKey = SBOnboardingModel.resumeStepKey
    let completedKey = SBOnboardingModel.shortcutsCompletedKey
    let prevResume = UserDefaults.standard.integer(forKey: resumeKey)
    let prevCompleted = UserDefaults.standard.bool(forKey: completedKey)
    // The beat phases persist alongside the resume step; a phase left behind by another test
    // would otherwise resume this model mid-beat.
    let phaseKeys = [SBOnboardingModel.cardPhaseKey, SBOnboardingModel.talkPhaseKey, SBOnboardingModel.writePhaseKey, SBOnboardingModel.writeReceiptsKey]
    let prevPhases = phaseKeys.map { UserDefaults.standard.object(forKey: $0) }
    phaseKeys.forEach { UserDefaults.standard.removeObject(forKey: $0) }
    defer {
      UserDefaults.standard.set(prevResume, forKey: resumeKey)
      UserDefaults.standard.set(prevCompleted, forKey: completedKey)
      for (key, value) in zip(phaseKeys, prevPhases) {
        if let value { UserDefaults.standard.set(value, forKey: key) } else { UserDefaults.standard.removeObject(forKey: key) }
      }
    }

    // Hold a strong reference to AppState for the life of the test. SBOnboardingModel
    // stores appState as `unowned`, so a temporary would be deallocated before begin()
    // touches it.
    let appState = AppState()

    UserDefaults.standard.set(SBOnboardingModel.Step.talk.rawValue, forKey: resumeKey)
    UserDefaults.standard.set(false, forKey: completedKey)
    let notYetCompleted = SBOnboardingModel(
      appState: appState, chatProvider: ChatProvider(), onComplete: nil)
    notYetCompleted.begin()
    XCTAssertEqual(notYetCompleted.step, .talk)
    XCTAssertEqual(
      notYetCompleted.talkPhase, .microphone,
      "without a completed chord, resuming at talk starts over from the microphone")

    UserDefaults.standard.set(SBOnboardingModel.Step.talk.rawValue, forKey: resumeKey)
    UserDefaults.standard.set(true, forKey: completedKey)
    let completed = SBOnboardingModel(
      appState: appState, chatProvider: ChatProvider(), onComplete: nil)
    completed.begin()
    XCTAssertEqual(completed.step, .talk)
    XCTAssertEqual(
      completed.talkPhase, .demo,
      "a genuinely completed chord resumes straight at the demo, not back at the microphone")
  }
}
