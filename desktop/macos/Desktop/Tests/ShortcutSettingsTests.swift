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
}
