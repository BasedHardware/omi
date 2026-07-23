import XCTest

@testable import Omi_Computer

@MainActor
final class ShortcutSettingsTests: XCTestCase {
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
