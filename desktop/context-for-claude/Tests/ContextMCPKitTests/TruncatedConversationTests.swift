import Foundation
import XCTest

@testable import ContextMCPKit

final class TruncatedConversationTests: XCTestCase {

    func testATruncatedAnswerIsServedNotCachedAndTheCompleteOneIs() {
        let sent = RequestLog()
        let responses = ResponseQueue([
            .success(Self.conversationJSON(truncated: true)),
            .success(Self.conversationJSON(truncated: false)),
        ])
        let backend = OmiBackend(
            credential: (key: "test-key", source: .appSupportFile),
            isAirgapped: { false },
            transport: { request in
                sent.record(request)
                return responses.next()
            })

        guard case let .ok(first) = backend.conversation(id: "c1") else {
            return XCTFail("a truncated body is still a served answer")
        }
        XCTAssertTrue(first.truncated)
        XCTAssertEqual(first.segments.count, 1)

        guard case let .ok(second) = backend.conversation(id: "c1") else {
            return XCTFail("the refetch is a real request, not the cached partial")
        }
        XCTAssertFalse(second.truncated)
        XCTAssertEqual(second.segments.count, 1)

        guard case let .ok(third) = backend.conversation(id: "c1") else {
            return XCTFail("the complete answer is the one that caches")
        }
        XCTAssertFalse(third.truncated)
        XCTAssertEqual(sent.count, 2, "one fetch for the partial, one for the complete, none for the hit")
    }

    func testTruncatedDefaultsToFalseWhenTheFieldIsAbsent() throws {
        let full = try JSONDecoder().decode(OmiFullConversation.self, from: Self.conversationJSON(truncated: nil))
        XCTAssertFalse(full.truncated)
        XCTAssertEqual(full.conversation.title, "Standup")
    }

    func testRenderedTranscriptAnnouncesTruncation() throws {
        let decoder = JSONDecoder()
        let truncated = try decoder.decode(OmiFullConversation.self, from: Self.conversationJSON(truncated: true))
        let complete = try decoder.decode(OmiFullConversation.self, from: Self.conversationJSON(truncated: false))

        let partial = Tools.renderOmiTranscript(truncated)
        XCTAssertTrue(partial.contains("This transcript is partial"), "the cut is stated, not implied")
        XCTAssertFalse(Tools.renderOmiTranscript(complete).contains("This transcript is partial"))
    }

    func testRenderedEmptyTruncatedTranscriptNeverClaimsNoTranscript() throws {
        let full = try JSONDecoder().decode(
            OmiFullConversation.self,
            from: Self.conversationJSON(truncated: true, segments: "[]"))

        let text = Tools.renderOmiTranscript(full)
        XCTAssertTrue(text.contains("This transcript is partial"))
        XCTAssertFalse(text.contains("no transcript for this conversation"))
    }

    // MARK: Fixtures

    private static func conversationJSON(truncated: Bool?, segments: String = defaultSegments) -> Data {
        var json = """
        {"id":"c1","started_at":"2026-08-14T09:00:00Z","finished_at":"2026-08-14T09:30:00Z",
        "structured":{"title":"Standup","overview":"Weekly sync."},
        "transcript_segments":\(segments)
        """
        if let truncated { json += ",\"truncated\":\(truncated)" }
        return Data((json + "}").utf8)
    }

    private static let defaultSegments = """
    [{"text":"Shipped the fix.","speaker_name":"User","speaker_id":0,"start":0,"end":5}]
    """

    private final class ResponseQueue: @unchecked Sendable {
        private let lock = NSLock()
        private var responses: [Result<Data, OmiBackendError>]

        init(_ responses: [Result<Data, OmiBackendError>]) {
            self.responses = responses
        }

        func next() -> Result<Data, OmiBackendError> {
            lock.lock()
            defer { lock.unlock() }
            guard !responses.isEmpty else { return .failure(.malformedResponse("script exhausted")) }
            return responses.removeFirst()
        }
    }

    private final class RequestLog: @unchecked Sendable {
        private let lock = NSLock()
        private var requests: [URLRequest] = []

        func record(_ request: URLRequest) {
            lock.lock()
            requests.append(request)
            lock.unlock()
        }

        var count: Int {
            lock.lock()
            defer { lock.unlock() }
            return requests.count
        }
    }
}
