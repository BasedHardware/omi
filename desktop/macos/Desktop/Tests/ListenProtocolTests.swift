import XCTest
@testable import Omi_Computer

/// Tests for the Python backend WebSocket protocol parsing.
/// Exercises TranscriptionService.parseBackendResponse() end-to-end with real callback dispatch.
final class ListenProtocolTests: XCTestCase {

    // MARK: - BackendSegment Decoding

    func testDecodeSegmentWithAllFields() throws {
        let json = """
        [{"id":"seg-1","text":"hello world","speaker":"SPEAKER_00","speaker_id":0,"is_user":true,"person_id":"p1","start":1.5,"end":3.2}]
        """
        let data = json.data(using: .utf8)!
        let segments = try JSONDecoder().decode([TranscriptionService.BackendSegment].self, from: data)

        XCTAssertEqual(segments.count, 1)
        let seg = segments[0]
        XCTAssertEqual(seg.id, "seg-1")
        XCTAssertEqual(seg.text, "hello world")
        XCTAssertEqual(seg.speaker, "SPEAKER_00")
        XCTAssertEqual(seg.speaker_id, 0)
        XCTAssertTrue(seg.is_user)
        XCTAssertEqual(seg.person_id, "p1")
        XCTAssertEqual(seg.start, 1.5)
        XCTAssertEqual(seg.end, 3.2)
    }

    func testDecodeSegmentWithNullOptionals() throws {
        let json = """
        [{"id":null,"text":"test","speaker":null,"speaker_id":null,"is_user":false,"person_id":null,"start":0.0,"end":1.0}]
        """
        let data = json.data(using: .utf8)!
        let segments = try JSONDecoder().decode([TranscriptionService.BackendSegment].self, from: data)

        XCTAssertEqual(segments.count, 1)
        let seg = segments[0]
        XCTAssertNil(seg.id)
        XCTAssertNil(seg.speaker)
        XCTAssertNil(seg.speaker_id)
        XCTAssertNil(seg.person_id)
        XCTAssertFalse(seg.is_user)
    }

    func testDecodeMultipleSegments() throws {
        let json = """
        [
            {"id":"s1","text":"first","speaker":"SPEAKER_00","speaker_id":0,"is_user":true,"person_id":null,"start":0.0,"end":1.0},
            {"id":"s2","text":"second","speaker":"SPEAKER_01","speaker_id":1,"is_user":false,"person_id":"p2","start":1.0,"end":2.5}
        ]
        """
        let data = json.data(using: .utf8)!
        let segments = try JSONDecoder().decode([TranscriptionService.BackendSegment].self, from: data)

        XCTAssertEqual(segments.count, 2)
        XCTAssertEqual(segments[0].speaker_id, 0)
        XCTAssertTrue(segments[0].is_user)
        XCTAssertEqual(segments[1].speaker_id, 1)
        XCTAssertFalse(segments[1].is_user)
    }

    func testDecodeEmptySegmentArray() throws {
        let json = "[]"
        let data = json.data(using: .utf8)!
        let segments = try JSONDecoder().decode([TranscriptionService.BackendSegment].self, from: data)
        XCTAssertTrue(segments.isEmpty)
    }

    // MARK: - parseBackendResponse: Callback Dispatch

    /// Helper: create a TranscriptionService and wire its callbacks for testing.
    /// Uses forBatchOnly init to avoid needing Firebase auth.
    private func makeServiceWithCallbacks(
        onSegments: @escaping ([TranscriptionService.BackendSegment]) -> Void,
        onEvent: @escaping (TranscriptionService.ListenEvent) -> Void
    ) -> TranscriptionService? {
        // Use batch init to skip auth/URL requirements, then set callbacks manually
        guard let service = try? TranscriptionService(language: "en", forBatchOnly: true) else {
            // Batch init — create with streaming init fallback if needed
            return try? TranscriptionService(language: "en")
        }
        service.start(
            onSegments: onSegments,
            onEvent: onEvent,
            onError: nil,
            onConnected: nil,
            onDisconnected: nil
        )
        return service
    }

    func testParserDispatchesSegmentCallback() throws {
        var receivedSegments: [TranscriptionService.BackendSegment] = []
        let service = try TranscriptionService(language: "en")
        service.start(
            onSegments: { receivedSegments = $0 },
            onEvent: { _ in },
            onError: nil,
            onConnected: nil,
            onDisconnected: nil
        )

        let json = """
        [{"id":"s1","text":"hello","speaker":"SPEAKER_00","speaker_id":0,"is_user":true,"person_id":null,"start":0.0,"end":1.5}]
        """
        service.parseBackendResponse(json)

        XCTAssertEqual(receivedSegments.count, 1)
        XCTAssertEqual(receivedSegments[0].id, "s1")
        XCTAssertEqual(receivedSegments[0].text, "hello")
        XCTAssertTrue(receivedSegments[0].is_user)
    }

    func testParserDispatchesEventCallback() throws {
        var receivedEvent: TranscriptionService.ListenEvent?
        let service = try TranscriptionService(language: "en")
        service.start(
            onSegments: { _ in },
            onEvent: { receivedEvent = $0 },
            onError: nil,
            onConnected: nil,
            onDisconnected: nil
        )

        let json = """
        {"type":"memory_created","memory":{"id":"conv-abc"}}
        """
        service.parseBackendResponse(json)

        XCTAssertEqual(receivedEvent?.type, "memory_created")
        let memory = receivedEvent?.raw["memory"] as? [String: Any]
        XCTAssertEqual(memory?["id"] as? String, "conv-abc")
    }

    func testParserIgnoresPingHeartbeat() throws {
        var segmentsCalled = false
        var eventCalled = false
        let service = try TranscriptionService(language: "en")
        service.start(
            onSegments: { _ in segmentsCalled = true },
            onEvent: { _ in eventCalled = true },
            onError: nil,
            onConnected: nil,
            onDisconnected: nil
        )

        service.parseBackendResponse("ping")
        service.parseBackendResponse("  ping  \n")

        XCTAssertFalse(segmentsCalled, "ping should not trigger segments callback")
        XCTAssertFalse(eventCalled, "ping should not trigger event callback")
    }

    func testParserIgnoresEmptySegmentArray() throws {
        var segmentsCalled = false
        let service = try TranscriptionService(language: "en")
        service.start(
            onSegments: { _ in segmentsCalled = true },
            onEvent: { _ in },
            onError: nil,
            onConnected: nil,
            onDisconnected: nil
        )

        service.parseBackendResponse("[]")

        XCTAssertFalse(segmentsCalled, "empty array should not trigger segments callback")
    }

    func testParserHandlesInvalidJsonGracefully() throws {
        var segmentsCalled = false
        var eventCalled = false
        let service = try TranscriptionService(language: "en")
        service.start(
            onSegments: { _ in segmentsCalled = true },
            onEvent: { _ in eventCalled = true },
            onError: nil,
            onConnected: nil,
            onDisconnected: nil
        )

        service.parseBackendResponse("not json at all")
        service.parseBackendResponse("{invalid json")
        service.parseBackendResponse("")

        XCTAssertFalse(segmentsCalled)
        XCTAssertFalse(eventCalled)
    }

    func testParserDispatchesSegmentsDeletedEvent() throws {
        var receivedEvent: TranscriptionService.ListenEvent?
        let service = try TranscriptionService(language: "en")
        service.start(
            onSegments: { _ in },
            onEvent: { receivedEvent = $0 },
            onError: nil,
            onConnected: nil,
            onDisconnected: nil
        )

        let json = """
        {"type":"segments_deleted","segment_ids":["s1","s2"]}
        """
        service.parseBackendResponse(json)

        XCTAssertEqual(receivedEvent?.type, "segments_deleted")
        let ids = receivedEvent?.raw["segment_ids"] as? [String]
        XCTAssertEqual(ids, ["s1", "s2"])
    }

    func testParserDispatchesSpeakerLabelEvent() throws {
        var receivedEvent: TranscriptionService.ListenEvent?
        let service = try TranscriptionService(language: "en")
        service.start(
            onSegments: { _ in },
            onEvent: { receivedEvent = $0 },
            onError: nil,
            onConnected: nil,
            onDisconnected: nil
        )

        let json = """
        {"type":"speaker_label_suggestion","speaker_id":1,"person_id":"p1","person_name":"Alice"}
        """
        service.parseBackendResponse(json)

        XCTAssertEqual(receivedEvent?.type, "speaker_label_suggestion")
        XCTAssertEqual(receivedEvent?.raw["speaker_id"] as? Int, 1)
        XCTAssertEqual(receivedEvent?.raw["person_name"] as? String, "Alice")
    }

    func testParserIgnoresObjectWithoutType() throws {
        var eventCalled = false
        let service = try TranscriptionService(language: "en")
        service.start(
            onSegments: { _ in },
            onEvent: { _ in eventCalled = true },
            onError: nil,
            onConnected: nil,
            onDisconnected: nil
        )

        // JSON object without "type" field should be silently ignored
        service.parseBackendResponse("""
        {"data":"something","value":42}
        """)

        XCTAssertFalse(eventCalled, "object without type should not trigger event callback")
    }

    // MARK: - Parser Boundary Tests

    func testParserHandlesArrayOfInvalidSegments() throws {
        // Valid JSON array but objects don't match BackendSegment schema
        var segmentsCalled = false
        var eventCalled = false
        let service = try TranscriptionService(language: "en")
        service.start(
            onSegments: { _ in segmentsCalled = true },
            onEvent: { _ in eventCalled = true },
            onError: nil,
            onConnected: nil,
            onDisconnected: nil
        )

        // Array of objects missing required fields (text, is_user, start, end)
        service.parseBackendResponse("""
        [{"foo":"bar","baz":123}]
        """)

        XCTAssertFalse(segmentsCalled, "array with non-decodable objects should not trigger segments")
        XCTAssertFalse(eventCalled)
    }

    func testParserHandlesEventWithMissingNestedFields() throws {
        // Event with type but missing expected nested fields (memory.id)
        var receivedEvent: TranscriptionService.ListenEvent?
        let service = try TranscriptionService(language: "en")
        service.start(
            onSegments: { _ in },
            onEvent: { receivedEvent = $0 },
            onError: nil,
            onConnected: nil,
            onDisconnected: nil
        )

        // memory_created without memory object
        service.parseBackendResponse("""
        {"type":"memory_created"}
        """)

        XCTAssertEqual(receivedEvent?.type, "memory_created")
        XCTAssertNil(receivedEvent?.raw["memory"], "missing memory field should be nil, not crash")
    }

    func testParserHandlesSegmentsDeletedWithMissingIds() throws {
        var receivedEvent: TranscriptionService.ListenEvent?
        let service = try TranscriptionService(language: "en")
        service.start(
            onSegments: { _ in },
            onEvent: { receivedEvent = $0 },
            onError: nil,
            onConnected: nil,
            onDisconnected: nil
        )

        // segments_deleted without segment_ids
        service.parseBackendResponse("""
        {"type":"segments_deleted"}
        """)

        XCTAssertEqual(receivedEvent?.type, "segments_deleted")
        XCTAssertNil(receivedEvent?.raw["segment_ids"])
    }

    func testParserHandlesJsonNumber() throws {
        // Plain number is valid JSON but not array or object
        var segmentsCalled = false
        var eventCalled = false
        let service = try TranscriptionService(language: "en")
        service.start(
            onSegments: { _ in segmentsCalled = true },
            onEvent: { _ in eventCalled = true },
            onError: nil,
            onConnected: nil,
            onDisconnected: nil
        )

        service.parseBackendResponse("42")
        service.parseBackendResponse("\"just a string\"")

        XCTAssertFalse(segmentsCalled)
        XCTAssertFalse(eventCalled)
    }

    func testParserHandlesUnknownEventType() throws {
        var receivedEvent: TranscriptionService.ListenEvent?
        let service = try TranscriptionService(language: "en")
        service.start(
            onSegments: { _ in },
            onEvent: { receivedEvent = $0 },
            onError: nil,
            onConnected: nil,
            onDisconnected: nil
        )

        // Unknown event type should still be dispatched
        service.parseBackendResponse("""
        {"type":"future_event_type","data":"something"}
        """)

        XCTAssertEqual(receivedEvent?.type, "future_event_type")
        XCTAssertEqual(receivedEvent?.raw["data"] as? String, "something")
    }

    // MARK: - Reconnection State Machine

    func testHandleDisconnectionRequiresConnected() throws {
        let service = try TranscriptionService(language: "en")
        // Not connected — handleDisconnection should be a no-op
        service.isConnected = false
        service.shouldReconnect = true
        service.reconnectAttempts = 0

        service.handleDisconnection()

        // reconnectAttempts should NOT increment — guard blocked the call
        XCTAssertEqual(service.reconnectAttempts, 0)
    }

    func testHandleDisconnectionIncrementsAttempts() throws {
        let service = try TranscriptionService(language: "en")
        service.isConnected = true
        service.shouldReconnect = true
        service.reconnectAttempts = 0

        service.handleDisconnection()

        XCTAssertFalse(service.isConnected)
        XCTAssertEqual(service.reconnectAttempts, 1)
    }

    func testCleanupAndReconnectWorksWhenNotConnected() throws {
        let service = try TranscriptionService(language: "en")
        // Pre-connect state — isConnected is false
        service.isConnected = false
        service.shouldReconnect = true
        service.reconnectAttempts = 0

        service.cleanupAndReconnect()

        // Should increment attempts even though not connected
        XCTAssertEqual(service.reconnectAttempts, 1)
    }

    func testMaxReconnectAttemptsTriggersError() throws {
        var receivedError: Error?
        let service = try TranscriptionService(language: "en")
        service.start(
            onSegments: { _ in },
            onEvent: { _ in },
            onError: { receivedError = $0 },
            onConnected: nil,
            onDisconnected: nil
        )

        // Set attempts to max
        service.reconnectAttempts = service.maxReconnectAttempts
        service.isConnected = true
        service.shouldReconnect = true

        service.handleDisconnection()

        XCTAssertNotNil(receivedError, "should trigger error when max attempts reached")
    }

    func testCleanupAndReconnectMaxAttemptsTriggersError() throws {
        var receivedError: Error?
        let service = try TranscriptionService(language: "en")
        service.start(
            onSegments: { _ in },
            onEvent: { _ in },
            onError: { receivedError = $0 },
            onConnected: nil,
            onDisconnected: nil
        )

        service.reconnectAttempts = service.maxReconnectAttempts
        service.shouldReconnect = true

        service.cleanupAndReconnect()

        XCTAssertNotNil(receivedError, "should trigger error when max attempts reached (pre-connect)")
    }

    func testHandleDisconnectionCallsOnDisconnected() throws {
        var disconnectedCalled = false
        let service = try TranscriptionService(language: "en")
        service.start(
            onSegments: { _ in },
            onEvent: { _ in },
            onError: nil,
            onConnected: nil,
            onDisconnected: { disconnectedCalled = true }
        )

        service.isConnected = true
        service.shouldReconnect = false  // Don't attempt reconnect

        service.handleDisconnection()

        XCTAssertTrue(disconnectedCalled)
        XCTAssertFalse(service.isConnected)
    }

    // MARK: - Multi-Segment Dispatch

    func testParserDispatchesMultipleSegments() throws {
        var receivedSegments: [TranscriptionService.BackendSegment] = []
        let service = try TranscriptionService(language: "en")
        service.start(
            onSegments: { receivedSegments = $0 },
            onEvent: { _ in },
            onError: nil,
            onConnected: nil,
            onDisconnected: nil
        )

        let json = """
        [
            {"id":"s1","text":"hello","speaker":"SPEAKER_00","speaker_id":0,"is_user":true,"person_id":null,"start":0.0,"end":1.0},
            {"id":"s2","text":"world","speaker":"SPEAKER_01","speaker_id":1,"is_user":false,"person_id":"p2","start":1.0,"end":2.0}
        ]
        """
        service.parseBackendResponse(json)

        XCTAssertEqual(receivedSegments.count, 2)
        XCTAssertEqual(receivedSegments[0].text, "hello")
        XCTAssertEqual(receivedSegments[1].text, "world")
        XCTAssertEqual(receivedSegments[1].person_id, "p2")
    }
}
