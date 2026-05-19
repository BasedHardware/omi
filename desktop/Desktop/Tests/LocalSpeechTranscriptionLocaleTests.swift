import XCTest

@testable import Omi_Computer

final class LocalSpeechTranscriptionLocaleTests: XCTestCase {

    func testNormalizedLocaleUnderscoresBecomeHyphens() {
        XCTAssertEqual(
            LocalSpeechTranscriptionAdapter.normalizedLocaleIdentifier(forAssistantLanguageCode: "en_US"),
            "en-US")
    }

    func testNormalizedLocaleLowercaseUnderscores() {
        XCTAssertEqual(
            LocalSpeechTranscriptionAdapter.normalizedLocaleIdentifier(forAssistantLanguageCode: "en_au"),
            "en-au")
    }

    func testNormalizedLocalePreservesExistingHyphens() {
        XCTAssertEqual(
            LocalSpeechTranscriptionAdapter.normalizedLocaleIdentifier(forAssistantLanguageCode: "en-US"),
            "en-US")
    }

    func testNormalizedLocaleZhAlias() {
        XCTAssertEqual(
            LocalSpeechTranscriptionAdapter.normalizedLocaleIdentifier(forAssistantLanguageCode: "zh"),
            "zh-CN")
    }

    func testBackendSegmentHybridInitializerMatchesDecodedShape() throws {
        let json = """
        [{"id":"apple-hybrid-live","text":"hello","speaker":"SPEAKER_00","speaker_id":0,"is_user":true,"person_id":null,"start":0,"end":12.5,"translations":null}]
        """
        let decoded = try JSONDecoder().decode(
            [TranscriptionService.BackendSegment].self, from: XCTUnwrap(json.data(using: .utf8)))
        XCTAssertEqual(decoded.count, 1)

        let built = TranscriptionService.BackendSegment(
            id: LocalSpeechTranscriptionAdapter.pseudoBackendSegmentId,
            text: "hello",
            speaker: "SPEAKER_00",
            speaker_id: 0,
            is_user: true,
            person_id: nil,
            start: 0,
            end: 12.5,
            translations: nil
        )
        XCTAssertEqual(built.text, decoded[0].text)
        XCTAssertEqual(built.id, decoded[0].id)
        XCTAssertEqual(built.speaker_id, decoded[0].speaker_id)
        XCTAssertEqual(built.is_user, decoded[0].is_user)
    }
}
