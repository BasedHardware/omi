import XCTest

@testable import Omi_Computer

final class AgentSpeechMatcherTests: XCTestCase {
    func testExactNames() {
        XCTAssertEqual(AgentSpeechMatcher.resolve("codex")?.harness, .codex)
        XCTAssertEqual(AgentSpeechMatcher.resolve("hermes")?.harness, .hermes)
        XCTAssertEqual(AgentSpeechMatcher.resolve("openclaw")?.harness, .openclaw)
        XCTAssertEqual(AgentSpeechMatcher.resolve("claude code")?.harness, .acp)
        XCTAssertEqual(AgentSpeechMatcher.resolve("omi")?.harness, .piMono)
    }

    // The whole point: speech-to-text mangles the names and we still route correctly.
    func testMangledSpeech() {
        XCTAssertEqual(AgentSpeechMatcher.resolve("open claw")?.harness, .openclaw)
        XCTAssertEqual(AgentSpeechMatcher.resolve("open flaw")?.harness, .openclaw)
        XCTAssertEqual(AgentSpeechMatcher.resolve("code x")?.harness, .codex)
        XCTAssertEqual(AgentSpeechMatcher.resolve("code decks")?.harness, .codex)
        XCTAssertEqual(AgentSpeechMatcher.resolve("her mees")?.harness, .hermes)
        XCTAssertEqual(AgentSpeechMatcher.resolve("hermies")?.harness, .hermes)
        XCTAssertEqual(AgentSpeechMatcher.resolve("cloud code")?.harness, .acp)
    }

    func testNonAgentReturnsNil() {
        XCTAssertNil(AgentSpeechMatcher.resolve(""))
        XCTAssertNil(AgentSpeechMatcher.resolve("banana"))
        XCTAssertNil(AgentSpeechMatcher.resolve("the weather today"))
    }

    func testExactConfidenceIsOne() {
        XCTAssertEqual(AgentSpeechMatcher.resolve("codex")?.confidence, 1)
    }
}
