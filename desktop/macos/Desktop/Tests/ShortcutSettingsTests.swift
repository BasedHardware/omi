import XCTest

@testable import Omi_Computer

@MainActor
final class ShortcutSettingsTests: XCTestCase {
  func testPushToTalkGuidanceNamesHoldAndEnabledHandsFreeMode() {
    XCTAssertEqual(
      PushToTalkSettingsGuidance.lines(
        pttEnabled: true,
        doubleTapForLock: true,
        shortcutLabel: "⌥"
      ),
      [
        "Hold ⌥ to speak, then release to send.",
        "Double-tap to keep listening hands-free; tap again to send.",
        "Say “type…” to dictate into the focused app.",
      ]
    )
  }

  func testPushToTalkGuidanceExplainsDisabledHandsFreeMode() {
    XCTAssertEqual(
      PushToTalkSettingsGuidance.lines(
        pttEnabled: true,
        doubleTapForLock: false,
        shortcutLabel: "⌘J"
      )[1],
      "Turn on Double-tap for Locked Mode for hands-free listening."
    )
  }

  func testPushToTalkGuidanceRequiresPTTWhenDisabled() {
    XCTAssertEqual(
      PushToTalkSettingsGuidance.lines(
        pttEnabled: false,
        doubleTapForLock: false,
        shortcutLabel: "⌥"
      ),
      [
        "Enable Push to Talk to use voice input."
      ]
    )
  }

  func testPushToTalkRequiresAtLeastOneModifier() {
    let bareU = ShortcutSettings.KeyboardShortcut(keyCode: 32, keyDisplay: "U")
    let commandU = ShortcutSettings.KeyboardShortcut(keyCode: 32, keyDisplay: "U", modifiers: .command)
    let optionOnly = ShortcutSettings.KeyboardShortcut(modifierOnly: .option)

    XCTAssertFalse(ShortcutSettings.isSafePushToTalkShortcut(bareU))
    XCTAssertTrue(ShortcutSettings.isSafePushToTalkShortcut(commandU))
    XCTAssertTrue(ShortcutSettings.isSafePushToTalkShortcut(optionOnly))
  }

  func testAskOmiDefaultShortcutIsCommandO() {
    XCTAssertEqual(ShortcutSettings.defaultAskOmiShortcut, ShortcutSettings.askOmiCommandOShortcut)
    XCTAssertEqual(ShortcutSettings.defaultAskOmiShortcut.displayTokens, ["⌘", "O"])
  }

  func testAskOmiPresetsShowCommandOFirst() {
    XCTAssertEqual(ShortcutSettings.askOmiPresets.first, ShortcutSettings.askOmiCommandOShortcut)
    XCTAssertEqual(
      ShortcutSettings.askOmiPresets,
      [
        ShortcutSettings.askOmiCommandOShortcut,
        ShortcutSettings.askOmiCommandReturnShortcut,
        ShortcutSettings.askOmiCommandShiftReturnShortcut,
        ShortcutSettings.askOmiCommandJShortcut,
      ]
    )
  }

  func testAskOmiCommandShiftReturnShowsEveryShortcutToken() {
    let tokens = ShortcutSettings.askOmiCommandShiftReturnShortcut.displayTokens

    XCTAssertEqual(tokens, ["⇧", "⌘", "↩"])
    XCTAssertEqual(ShortcutHintLayout.visibleTokens(for: tokens), tokens)
  }

  func testOnboardingFloatingBarPresetPersistsImmediately() {
    let previousShortcut = ShortcutSettings.shared.askOmiShortcut
    defer { ShortcutSettings.shared.askOmiShortcut = previousShortcut }

    let preset = ShortcutSettings.askOmiCommandJShortcut
    let model = SBOnboardingModel(appState: AppState(), chatProvider: ChatProvider(), onComplete: nil)
    model.pickShortcut(preset, isTalk: false)

    XCTAssertEqual(ShortcutSettings.shared.askOmiShortcut, preset)
    XCTAssertFalse(ShortcutSettings.shared.askOmiUsesCustomShortcut)
  }

  func testOnboardingVoicePresetPersistsImmediately() {
    let previousShortcut = ShortcutSettings.shared.pttShortcut
    defer { ShortcutSettings.shared.pttShortcut = previousShortcut }

    let preset = ShortcutSettings.pttPresets[0]
    let model = SBOnboardingModel(appState: AppState(), chatProvider: ChatProvider(), onComplete: nil)
    model.pickShortcut(preset, isTalk: true)

    XCTAssertEqual(ShortcutSettings.shared.pttShortcut, preset)
    XCTAssertFalse(ShortcutSettings.shared.pttUsesCustomShortcut)
  }

  func testExplicitPTTMicrophoneOverridesAutomaticBluetoothFallback() {
    XCTAssertEqual(
      PTTInputDeviceRouting.overrideDeviceID(
        selectedDeviceID: 41,
        outputIsBluetooth: true,
        builtInDeviceID: 86
      ),
      41
    )
  }

  func testAutomaticPTTMicrophoneUsesBuiltInForBluetoothOutput() {
    XCTAssertEqual(
      PTTInputDeviceRouting.overrideDeviceID(
        selectedDeviceID: nil,
        outputIsBluetooth: true,
        builtInDeviceID: 86
      ),
      86
    )
  }

  func testAutomaticPTTMicrophoneUsesSystemDefaultForNonBluetoothOutput() {
    XCTAssertNil(
      PTTInputDeviceRouting.overrideDeviceID(
        selectedDeviceID: nil,
        outputIsBluetooth: false,
        builtInDeviceID: 86
      )
    )
  }
}
