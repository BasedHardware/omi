import XCTest
@testable import Omi_Computer

@MainActor
final class FloatingBarVoiceResponseSettingsTests: XCTestCase {

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
