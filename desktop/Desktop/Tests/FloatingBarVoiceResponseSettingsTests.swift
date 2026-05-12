import XCTest
@testable import Omi_Computer

@MainActor
final class FloatingBarVoiceResponseSettingsTests: XCTestCase {

    func testDefaultVoiceIsOnyxOpenAIHumanVoice() {
        XCTAssertEqual(ShortcutSettings.defaultVoiceID, ShortcutSettings.openAIOnyxVoiceID)

        let voice = ShortcutSettings.voiceOption(for: ShortcutSettings.defaultVoiceID)
        XCTAssertEqual(voice.name, "Onyx")
        XCTAssertTrue(voice.isOpenAI)
        XCTAssertEqual(voice.provider, .openAI)
        XCTAssertEqual(voice.openAIVoice, "onyx")
    }

    func testShimmerVoiceHasNeutralDisplayName() {
        let voice = ShortcutSettings.voiceOption(for: ShortcutSettings.openAIShimmerVoiceID)
        XCTAssertEqual(voice.name, "Shimmer")
        XCTAssertEqual(voice.openAIVoice, "shimmer")
    }

    func testOnlyOpenAIVoicesAreAvailableInPicker() {
        XCTAssertFalse(ShortcutSettings.availableVoices.contains { $0.isLocalSystem })
    }

    func testLegacyProxyVoicesAreNotAvailableInPicker() {
        XCTAssertFalse(
            ShortcutSettings.availableVoices.contains {
                $0.name.localizedCaseInsensitiveContains("Sloane")
                    || $0.id == "BAMYoBHLZM7lJgJAmFz0"
            }
        )
    }

    func testInvalidVoiceFallsBackToDefaultOpenAIVoice() {
        let voice = ShortcutSettings.voiceOption(for: "missing")
        XCTAssertEqual(voice.id, ShortcutSettings.defaultVoiceID)
        XCTAssertTrue(voice.isOpenAI)
        XCTAssertEqual(voice.openAIVoice, "onyx")
    }

    func testVoiceQueryUsesVoiceToggle() {
        let settings = ShortcutSettings.shared
        let originalVoiceSetting = settings.floatingBarVoiceAnswersEnabled
        let originalTypedSetting = settings.floatingBarTypedQuestionVoiceAnswersEnabled

        defer {
            settings.floatingBarVoiceAnswersEnabled = originalVoiceSetting
            settings.floatingBarTypedQuestionVoiceAnswersEnabled = originalTypedSetting
        }

        settings.floatingBarVoiceAnswersEnabled = true
        settings.floatingBarTypedQuestionVoiceAnswersEnabled = false
        XCTAssertTrue(settings.shouldSpeakFloatingBarResponse(forVoiceQuery: true))
        XCTAssertFalse(settings.shouldSpeakFloatingBarResponse(forVoiceQuery: false))

        settings.floatingBarVoiceAnswersEnabled = false
        settings.floatingBarTypedQuestionVoiceAnswersEnabled = true
        XCTAssertFalse(settings.shouldSpeakFloatingBarResponse(forVoiceQuery: true))
        XCTAssertTrue(settings.shouldSpeakFloatingBarResponse(forVoiceQuery: false))
    }
}
