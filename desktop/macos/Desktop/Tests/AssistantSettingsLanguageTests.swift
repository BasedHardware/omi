import XCTest
@testable import Omi_Computer

@MainActor
final class AssistantSettingsLanguageTests: XCTestCase {
    private let languageKey = "transcriptionLanguage"
    private let autoDetectKey = "transcriptionAutoDetect"

    override func setUp() {
        super.setUp()
        UserDefaults.standard.removeObject(forKey: languageKey)
        UserDefaults.standard.removeObject(forKey: autoDetectKey)
    }

    override func tearDown() {
        UserDefaults.standard.removeObject(forKey: languageKey)
        UserDefaults.standard.removeObject(forKey: autoDetectKey)
        super.tearDown()
    }

    func testNormalizesChineseAliasesToDeepgramCode() {
        XCTAssertEqual(AssistantSettings.normalizeTranscriptionLanguageCode("chinese"), "zh-CN")
        XCTAssertEqual(AssistantSettings.normalizeTranscriptionLanguageCode("zh"), "zh-CN")
        XCTAssertEqual(AssistantSettings.normalizeTranscriptionLanguageCode("zh_Hans"), "zh-CN")
        XCTAssertEqual(AssistantSettings.normalizeTranscriptionLanguageCode("中文"), "zh-CN")
        XCTAssertEqual(AssistantSettings.normalizeTranscriptionLanguageCode("zh-Hant"), "zh-TW")
        XCTAssertEqual(AssistantSettings.normalizeTranscriptionLanguageCode("粤语"), "zh-HK")
    }

    func testPersistedAliasIsNormalizedAndWrittenBackOnRead() {
        UserDefaults.standard.set("chinese", forKey: languageKey)

        XCTAssertEqual(AssistantSettings.shared.transcriptionLanguage, "zh-CN")
        XCTAssertEqual(UserDefaults.standard.string(forKey: languageKey), "zh-CN")
    }

    func testChineseDoesNotUseAutoDetectMultiLanguageMode() {
        AssistantSettings.shared.transcriptionLanguage = "chinese"
        AssistantSettings.shared.transcriptionAutoDetect = true

        XCTAssertEqual(AssistantSettings.shared.effectiveTranscriptionLanguage, "zh-CN")
        XCTAssertFalse(AssistantSettings.supportsAutoDetect("chinese"))
    }

    func testBrazilianPortugueseAliasIsSupported() {
        XCTAssertEqual(AssistantSettings.normalizeTranscriptionLanguageCode("br"), "pt-BR")
        XCTAssertEqual(AssistantSettings.shared.transcriptionLanguage, "en")
        XCTAssertTrue(AssistantSettings.supportsAutoDetect("br"))
    }

    func testDesktopLanguagePickerIncludesBackendSupportedLanguages() {
        let languageCodes = Set(AssistantSettings.supportedLanguages.map(\.code))

        XCTAssertTrue(languageCodes.contains("zh-CN"))
        XCTAssertTrue(languageCodes.contains("zh-HK"))
        XCTAssertTrue(languageCodes.contains("zh-TW"))
        XCTAssertTrue(languageCodes.contains("ar"))
        XCTAssertTrue(languageCodes.contains("bn"))
        XCTAssertTrue(languageCodes.contains("ta"))
        XCTAssertTrue(languageCodes.contains("ur"))
    }
}
