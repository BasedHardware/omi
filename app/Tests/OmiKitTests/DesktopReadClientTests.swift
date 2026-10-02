import XCTest

@testable import OmiKit

private actor DesktopReadTransportStub: BackendTransport {
    private var responses: [BackendResponse]
    private let contract: APIContract?
    private var capturedRequests: [BackendRequest] = []
    private var plane: SoftwarePlane?

    init(_ responses: [BackendResponse], contract: APIContract? = .canonical) {
        self.responses = responses
        self.contract = contract
    }

    func request(_ request: BackendRequest) async throws -> BackendResponse {
        capturedRequests.append(request)
        guard !responses.isEmpty else { throw StubError.noResponse }
        return responses.removeFirst()
    }

    func generationEvents(
        generationId: String, lastEventId: String?,
        onFrame: @escaping @Sendable (String) -> Void
    ) async throws -> BackendResponse {
        _ = generationId
        _ = lastEventId
        _ = onFrame
        guard !responses.isEmpty else { throw StubError.noResponse }
        return responses.removeFirst()
    }

    func cancelGenerationEvents(generationId: String) async { _ = generationId }
    func createWriteId() async throws -> String { "write-id" }
    func createRecordingId() async throws -> String { "recording-id" }
    func apiContract() async -> APIContract? { contract }
    func softwarePlane() async -> SoftwarePlane? { plane }
    func setSoftwarePlane(_ plane: SoftwarePlane) async -> SoftwarePlane? {
        self.plane = plane
        return plane
    }
    func stampedBackendOrigin() async -> String? { nil }
    func requests() -> [BackendRequest] { capturedRequests }

    private enum StubError: Error {
        case noResponse
    }
}

final class DesktopReadClientTests: XCTestCase {
    func testCanonicalConversationReadMapsCursorEnvelopeAndProjection() async throws {
        let transport = DesktopReadTransportStub([
            response(
                200,
                """
                {
                  "contractVersion":"1.0.0",
                  "items":[{
                    "id":"c-1","title":"Planning","overview":"Ship v5",
                    "createdAt":1700000000000,"updatedAt":1700000001000,
                    "startedAt":null,"finishedAt":null,"source":"omi",
                    "status":"finished","discarded":false,"capturedAtMs":1699999999000,
                    "starred":true,"visibility":"private","isLocked":true,"folderId":null
                  }],
                  "window":{"status":"more","complete":false,"hasMore":true,"nextCursor":"next"},
                  "completeness":{"version":"conversations-completeness-v1","status":"partial","reasons":["projection lag"]},
                  "absence":null
                }
                """)
        ])

        let result = try await loadConversations(transport, cursor: "a/b? c")

        XCTAssertEqual(result.items.count, 1)
        XCTAssertEqual(result.items[0].id, "c-1")
        XCTAssertEqual(result.items[0].title, "Planning")
        XCTAssertEqual(result.items[0].summary, "Ship v5")
        XCTAssertEqual(result.items[0].createdAt, "2023-11-14T22:13:20.000Z")
        XCTAssertEqual(result.items[0].updatedAt, "2023-11-14T22:13:21.000Z")
        XCTAssertNil(result.items[0].startedAt)
        XCTAssertEqual(result.items[0].capturedAtMs, 1_699_999_999_000)
        XCTAssertEqual(result.items[0].visibility, .priv)
        XCTAssertTrue(result.items[0].locked)
        XCTAssertEqual(
            result.page,
            ReadPageState(
                windowStatus: .more, complete: false, hasMore: true, nextCursor: "next",
                completenessStatus: .partial, reasons: ["projection lag"]))

        let requests = await transport.requests()
        XCTAssertEqual(requests.count, 1)
        XCTAssertEqual(requests[0].id, "desktop-conversations-read")
        XCTAssertEqual(requests[0].expectedApiContract, .canonical)
        XCTAssertEqual(
            requests[0].path,
            "/v1/conversations?limit=50&cursor=a%2Fb%3F%20c")
    }

    func testLegacyConversationReadUsesOmiOffsetContract() async throws {
        let transport = DesktopReadTransportStub(
            [
                response(
                    200,
                    """
                    [{
                      "id":"c-legacy","structured":{"title":"Old title","overview":"Old summary"},
                      "created_at":"2025-01-02T03:04:05Z","updated_at":null,
                      "started_at":null,"finished_at":null,"starred":false,
                      "status":"completed","source":"omi","visibility":"private",
                      "folder_id":null,"is_locked":false,"discarded":false
                    }]
                    """)
            ], contract: .omi)

        let result = try await loadConversations(transport, cursor: "omi-offset:25")

        XCTAssertEqual(result.apiContract, .omi)
        XCTAssertEqual(result.items.map(\.id), ["c-legacy"])
        XCTAssertEqual(result.items[0].searchableText, "Old title\nOld summary")
        XCTAssertEqual(result.page.windowStatus, .unknown)
        XCTAssertFalse(result.page.complete)
        let requests = await transport.requests()
        XCTAssertEqual(requests[0].expectedApiContract, .omi)
        XCTAssertEqual(requests[0].path, "/v1/conversations?limit=50&offset=25")
    }

    func testLegacyOmiForbiddenReadUsesAccountCopy() async {
        let transport = DesktopReadTransportStub(
            [response(403, nil)], contract: .omi)
        let error = await capturedError { try await loadConversations(transport) }

        XCTAssertEqual(
            error as? ReadCopyError,
            ReadCopyError(desktopBackendForbiddenCopy))
    }

    func testLegacyOmiReadsRejectDuplicateIDsAcrossAllLists() async {
        let duplicateRows = #"[{"id":"same"},{"id":"same"}]"#
        let conversations = DesktopReadTransportStub(
            [response(200, duplicateRows)], contract: .omi)
        let conversationError = await capturedError {
            try await loadConversations(conversations)
        }
        XCTAssertEqual(conversationError as? LegacyOmiReadError, .duplicateIDs)

        let memories = DesktopReadTransportStub(
            [response(200, duplicateRows)], contract: .omi)
        let memoryError = await capturedError { try await loadMemories(memories) }
        XCTAssertEqual(memoryError as? LegacyOmiReadError, .duplicateIDs)

        let tasks = DesktopReadTransportStub(
            [response(200, #"{"has_more":false,"action_items":[{"id":"same"},{"id":"same"}]}"#)],
            contract: .omi)
        let taskError = await capturedError { try await loadTasks(tasks) }
        XCTAssertEqual(taskError as? LegacyOmiReadError, .duplicateIDs)
    }

    func testLegacyOmiServerErrorsUseFixedServiceCopy() async {
        for status in [500, 502, 504] {
            let transport = DesktopReadTransportStub(
                [response(status, #"{"detail":"private upstream response"}"#)],
                contract: .omi)
            let error = await capturedError { try await loadMemories(transport) }

            XCTAssertEqual(
                error as? ReadCopyError,
                ReadCopyError(desktopBackendServiceCopy),
                "HTTP \(status) must use the fixed service copy")
        }
    }

    func testCanonicalMemoryReadPreservesProvenanceAndCitation() async throws {
        let transport = DesktopReadTransportStub([
            response(
                200,
                """
                {
                  "contractVersion":"1.0.0",
                  "items":[{
                    "id":"m-1","text":"team:project:source Keep launch small",
                    "citations":["c-1"],"provenance":{
                      "synthesisVersion":"v2","inputDigest":"in-1","outputDigest":"out-1"
                    },"updatedAt":1700000000000
                  }],
                  "window":{"status":"complete","complete":true,"hasMore":false,"nextCursor":null},
                  "completeness":{"version":"recall-completeness-v1","status":"complete","reasons":[]},
                  "absence":null
                }
                """)
        ])

        let result = try await loadMemories(transport)

        XCTAssertEqual(result.items.count, 1)
        XCTAssertEqual(result.items[0].title, "Keep launch small")
        XCTAssertEqual(result.items[0].citations, ["c-1"])
        XCTAssertEqual(result.items[0].searchableText, "Keep launch small\nc-1")
        XCTAssertEqual(result.items[0].timestamp, 1_700_000_000_000)
        XCTAssertEqual(result.items[0].provenance.label, "team:project:source")
        XCTAssertEqual(result.items[0].provenance.synthesisVersion, "v2")
        XCTAssertEqual(result.items[0].provenance.inputDigest, "in-1")
        XCTAssertEqual(result.items[0].provenance.outputDigest, "out-1")
    }

    func testCanonicalTaskReadMapsAccountEpochAndOptionalFields() async throws {
        let transport = DesktopReadTransportStub([
            response(
                200,
                """
                {
                  "contractVersion":"1.0.0","accountEpoch":42,
                  "items":[{
                    "id":"t-1","description":"Review capture flow","completed":false,
                    "completedAt":null,"dueAt":1700000000000,"owner":null,"source":"omi",
                    "provenance":["conversation:c-1"],"sortOrder":2,"indentLevel":1,
                    "createdAt":1699000000000,"updatedAt":1699500000000,"revision":"r3"
                  }],
                  "window":{"status":"complete","complete":true,"hasMore":false,"nextCursor":null},
                  "completeness":{"version":"tasks-completeness-v1","status":"complete","reasons":[]},
                  "absence":null
                }
                """)
        ])

        let result = try await loadTasks(transport)

        XCTAssertEqual(result.accountEpoch, 42)
        XCTAssertEqual(result.items.count, 1)
        XCTAssertEqual(result.items[0].title, "Review capture flow")
        XCTAssertEqual(result.items[0].summary, "Due 1700000000000")
        XCTAssertNil(result.items[0].owner)
        XCTAssertEqual(result.items[0].provenance, ["conversation:c-1"])
        XCTAssertEqual(result.items[0].sortOrder, 2)
        XCTAssertEqual(result.items[0].indentLevel, 1)
        XCTAssertEqual(result.items[0].revision, "r3")
    }

    func testMalformedPaginationAndProjectionUnavailableAreClassified() async {
        let malformedPage = DesktopReadTransportStub([
            response(
                200,
                """
                {
                  "contractVersion":"1.0.0","items":[],
                  "window":{"status":"more","complete":false,"hasMore":true,"nextCursor":null},
                  "completeness":{"version":"conversations-completeness-v1","status":"complete","reasons":[]}
                }
                """)
        ])
        do {
            _ = try await loadConversations(malformedPage)
            XCTFail("An incomplete cursor window must be rejected")
        } catch {
            XCTAssertEqual(
                error as? ReadClientError,
                .malformed("Conversations response window is malformed"))
        }

        let unavailable = DesktopReadTransportStub([
            response(
                503,
                """
                {"error":{"code":"projection_unavailable","retryable":true,"action":"retry"}}
                """)
        ])
        do {
            _ = try await loadMemories(unavailable)
            XCTFail("A canonical projection outage should use its retryable error")
        } catch {
            XCTAssertEqual(error as? ReadClientError, .projectionUnavailable)
            XCTAssertEqual(desktopReadErrorCopy(error), desktopProjectionUnavailableCopy)
        }
    }

    func testDuplicateIDsAreRejectedForEveryCanonicalRead() async {
        let conversation =
            #"{"id":"same","title":"Plan","overview":"Ship","createdAt":1,"updatedAt":1,"startedAt":null,"finishedAt":null,"source":"omi","status":"finished","discarded":false,"capturedAtMs":null,"starred":false,"visibility":"private","isLocked":false,"folderId":null}"#
        let conversationTransport = DesktopReadTransportStub([
            response(
                200,
                canonicalPage(
                    items: "\(conversation),\(conversation)",
                    completenessVersion: "conversations-completeness-v1"))
        ])
        let conversationError = await capturedError {
            try await loadConversations(conversationTransport)
        }
        XCTAssertEqual(
            conversationError as? ReadClientError,
            .malformed("Conversation IDs are duplicated"))

        let memory =
            #"{"id":"same","text":"Remember this","citations":[],"provenance":{"synthesisVersion":"v1","inputDigest":"in","outputDigest":"out"}}"#
        let memoryTransport = DesktopReadTransportStub([
            response(
                200,
                canonicalPage(
                    items: "\(memory),\(memory)",
                    completenessVersion: "recall-completeness-v1"))
        ])
        let memoryError = await capturedError { try await loadMemories(memoryTransport) }
        XCTAssertEqual(memoryError as? ReadClientError, .malformed("Memory IDs are duplicated"))

        let task =
            #"{"id":"same","description":"Review","completed":false,"completedAt":null,"dueAt":null,"owner":null,"source":"omi","provenance":[],"sortOrder":0,"indentLevel":0,"createdAt":1,"updatedAt":1,"revision":null}"#
        let taskTransport = DesktopReadTransportStub([
            response(
                200,
                canonicalPage(
                    items: "\(task),\(task)",
                    completenessVersion: "tasks-completeness-v1"))
        ])
        let taskError = await capturedError { try await loadTasks(taskTransport) }
        XCTAssertEqual(taskError as? ReadClientError, .malformed("Task IDs are duplicated"))
    }

    func testCanonicalEnvelopeRejectsNonObjectItemsAndMissingNullableFields() async {
        let malformedItem = DesktopReadTransportStub([
            response(
                200,
                canonicalPage(
                    items: "null", completenessVersion: "conversations-completeness-v1"))
        ])
        let itemError = await capturedError { try await loadConversations(malformedItem) }
        XCTAssertEqual(
            itemError as? ReadClientError,
            .malformed("Conversations response item 0 is malformed"))

        let missingCursor = DesktopReadTransportStub([
            response(
                200,
                """
                {
                  "contractVersion":"1.0.0","items":[],
                  "window":{"status":"complete","complete":true,"hasMore":false},
                  "completeness":{"version":"conversations-completeness-v1","status":"complete","reasons":[]},
                  "absence":null
                }
                """)
        ])
        let cursorError = await capturedError { try await loadConversations(missingCursor) }
        XCTAssertEqual(
            cursorError as? ReadClientError,
            .malformed("Conversations response window cursor is malformed"))

        let missingAbsence = DesktopReadTransportStub([
            response(
                200,
                """
                {
                  "contractVersion":"1.0.0","items":[],
                  "window":{"status":"complete","complete":true,"hasMore":false,"nextCursor":null},
                  "completeness":{"version":"conversations-completeness-v1","status":"complete","reasons":[]}
                }
                """)
        ])
        let absenceError = await capturedError { try await loadConversations(missingAbsence) }
        XCTAssertEqual(
            absenceError as? ReadClientError,
            .malformed("Conversations response absence is malformed"))
    }

    func testConversationCursorExpiryAndCanonicalHTTPFailuresKeepTheirCopy() async {
        let expiredConversation = DesktopReadTransportStub([response(400, nil)])
        let cursorError = await capturedError {
            try await loadConversations(expiredConversation, cursor: "opaque-cursor")
        }
        XCTAssertEqual(cursorError as? ReadCursorError, .conversationExpired)

        let forbidden = DesktopReadTransportStub([response(403, nil)])
        let forbiddenError = await capturedError { try await loadMemories(forbidden) }
        XCTAssertEqual(
            forbiddenError as? ReadCopyError,
            ReadCopyError(desktopBackendForbiddenCopy))

        let serverFailure = DesktopReadTransportStub([response(500, nil)])
        let serverError = await capturedError { try await loadTasks(serverFailure) }
        XCTAssertEqual(
            serverError as? ReadCopyError,
            ReadCopyError(desktopBackendServiceCopy))

        for status in [502, 504] {
            let gatewayFailure = DesktopReadTransportStub([
                response(status, #"{"detail":"private upstream response"}"#)
            ])
            let gatewayError = await capturedError { try await loadTasks(gatewayFailure) }
            XCTAssertEqual(
                gatewayError as? ReadCopyError,
                ReadCopyError(desktopBackendServiceCopy),
                "HTTP \(status) must use fixed service copy")
        }

        let untypedProjectionFailure = DesktopReadTransportStub([
            response(
                503,
                #"{"error":{"code":"projection_unavailable","retryable":false,"action":"retry"}}"#)
        ])
        let projectionError = await capturedError {
            try await loadMemories(untypedProjectionFailure)
        }
        XCTAssertEqual(
            projectionError as? ReadCopyError,
            ReadCopyError(desktopBackendServiceCopy))

        let notFound = DesktopReadTransportStub([response(404, nil)])
        let notFoundError = await capturedError { try await loadConversations(notFound) }
        XCTAssertEqual(
            notFoundError as? ReadCopyError,
            ReadCopyError(desktopReadFailureCopy))
    }

    func testTaskCursorExpiryAndUnauthorizedCopyStayDistinct() async {
        let expired = DesktopReadTransportStub([response(400, nil)])
        do {
            _ = try await loadTasks(expired, cursor: "cursor")
            XCTFail("An expired task cursor should request a refresh")
        } catch {
            XCTAssertEqual(error as? ReadCursorError, .taskExpired)
        }

        let unauthorized = DesktopReadTransportStub([response(401, nil)])
        do {
            _ = try await loadConversations(unauthorized)
            XCTFail("Unauthorized reads must preserve the sign-in recovery copy")
        } catch {
            XCTAssertEqual(error as? ReadCopyError, ReadCopyError(desktopBackendUnauthorizedCopy))
            XCTAssertEqual(desktopReadErrorCopy(error), desktopBackendUnauthorizedCopy)
        }
    }

    private func response(_ status: Int, _ body: String?) -> BackendResponse {
        BackendResponse(id: "desktop-read-test", status: status, body: body)
    }

    private func canonicalPage(items: String, completenessVersion: String) -> String {
        """
        {
          "contractVersion":"1.0.0","items":[\(items)],
          "window":{"status":"complete","complete":true,"hasMore":false,"nextCursor":null},
          "completeness":{"version":"\(completenessVersion)","status":"complete","reasons":[]},
          "absence":null
        }
        """
    }

    private func capturedError<Value>(
        _ operation: () async throws -> Value
    ) async -> Error? {
        do {
            _ = try await operation()
            return nil
        } catch {
            return error
        }
    }
}
