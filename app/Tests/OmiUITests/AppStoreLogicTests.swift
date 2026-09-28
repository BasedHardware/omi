import OmiKit
import XCTest

@testable import OmiUI

// Tests for the pure logic added with the App/AppStore wave: the chat
// transcript settle and the rewind capture-group → timeline-summary mapping.
final class AppStoreLogicTests: XCTestCase {
    private func message(
        _ id: String, _ text: String, _ sender: ChatSender,
        outcome: GenerationOutcome? = nil, localOnly: Bool? = nil
    ) -> ChatMessage {
        ChatMessage(
            id: id, text: text, sender: sender, createdAt: 1,
            generationOutcome: outcome, localOnly: localOnly)
    }

    func testSettleReplacesEchoAndPendingAtEchoPosition() {
        let older = message("a", "earlier", .human, outcome: .completed)
        let local = message("local", "hi", .human, localOnly: true)
        let pending = message(
            "pending:local", "", .ai, localOnly: true)
        let canonicalHuman = message("c-human", "hi", .human)
        let canonicalAssistant = message("c-ai", "hello", .ai, outcome: .completed)
        let settled = settleChatTranscript(
            current: [older, local, pending], echoId: "local",
            pendingId: "pending:local", human: canonicalHuman,
            assistant: canonicalAssistant)
        XCTAssertEqual(
            settled.map { $0.id }, ["a", "c-human", "c-ai"])
    }

    func testSettleAppendsWhenEchoIsMissing() {
        let canonicalHuman = message("c-human", "hi", .human)
        let settled = settleChatTranscript(
            current: [], echoId: "local", pendingId: "pending:local",
            human: canonicalHuman, assistant: nil)
        XCTAssertEqual(settled.map { $0.id }, ["c-human"])
    }

    func testSettleKeepsUnrelatedRowsAroundInsertion() {
        let before = message("b1", "before", .human)
        let after = message("a1", "after", .ai, outcome: .completed)
        let local = message("local", "hi", .human, localOnly: true)
        let human = message("c-human", "hi", .human)
        let assistant = message("c-ai", "hello", .ai, outcome: .completed)
        let settled = settleChatTranscript(
            current: [before, local, after], echoId: "local",
            pendingId: "pending:local", human: human, assistant: assistant)
        XCTAssertEqual(
            settled.map { $0.id }, ["b1", "c-human", "c-ai", "a1"])
    }

    func testCaptureSummariesMapGroupsToTimelineSummaries() {
        let frame = RewindFrame(
            id: "f1", capturedAtMs: 5_000, appName: "Xcode",
            windowTitle: "AppStore.swift")
        let older = RewindFrame(
            id: "f0", capturedAtMs: 1_000, appName: "Xcode",
            windowTitle: "AppStore.swift")
        // groupRewindFrames is the public constructor path for groups.
        let groups = groupRewindFrames([frame, older])
        XCTAssertEqual(groups.count, 1)
        let summaries = captureSummaries(from: groups)
        XCTAssertEqual(summaries.count, 1)
        XCTAssertEqual(summaries[0].id, "f1")
        XCTAssertEqual(summaries[0].appName, "Xcode")
        XCTAssertEqual(summaries[0].count, 2)
        XCTAssertEqual(summaries[0].capturedAtMs, 5_000)
    }

    func testAppServicesDefaultsToNilDependencies() {
        let services = AppServices()
        XCTAssertNil(services.auth)
        XCTAssertNil(services.chat)
        XCTAssertNil(services.reads)
        XCTAssertNil(services.tasks)
        XCTAssertNil(services.cloud)
        XCTAssertNil(services.settings)
        XCTAssertNil(services.devices)
        XCTAssertNil(services.rewindCapture)
        XCTAssertNil(services.transport)
    }
}
