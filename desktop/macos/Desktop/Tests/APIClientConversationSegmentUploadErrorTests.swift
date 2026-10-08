import XCTest

@testable import Omi_Computer

private final class SegmentUploadErrorURLStub: URLProtocol, @unchecked Sendable {
  private static let lock = NSLock()
  private nonisolated(unsafe) static var status = 410
  private nonisolated(unsafe) static var body = Data()

  static func configure(status: Int = 410, body: String) {
    lock.withLock {
      Self.status = status
      Self.body = Data(body.utf8)
    }
  }

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    let (status, body) = Self.lock.withLock { (Self.status, Self.body) }
    guard let url = request.url,
      let response = HTTPURLResponse(
        url: url, statusCode: status, httpVersion: nil,
        headerFields: ["Content-Type": "application/json"])
    else { return }
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: body)
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}
}

final class APIClientConversationSegmentUploadErrorTests: XCTestCase {
  func testStructuredDeletedReceiptReturnsTypedUploadError() async throws {
    let client = await makeClient()
    SegmentUploadErrorURLStub.configure(
      body:
        #"{"detail":{"code":"conversation_deleted","message":"A localized server message"}}"#)
    do {
      _ = try await client.createConversationFromSegments(upload())
      XCTFail("The upload's deletion receipt must be preserved as a typed result")
    } catch ConversationSegmentUploadError.userDeleted {
      // The immutable code, rather than the message text, authorizes retirement.
    }
  }

  func testUnknownOrMissingCodeDoesNotAuthorizeRetirementDespiteTheSameMessage() async throws {
    let client = await makeClient()
    for body in [
      #"{"detail":{"code":"session_expired","message":"Conversation was deleted"}}"#,
      #"{"detail":{"message":"Conversation was deleted"}}"#,
      #"{"detail":"Conversation was deleted"}"#,
      #"{"code":"different_code","detail":{"code":"conversation_deleted","message":"Conversation was deleted"}}"#,
    ] {
      SegmentUploadErrorURLStub.configure(body: body)
      do {
        _ = try await client.createConversationFromSegments(upload())
        XCTFail("An unknown 410 must retain the caller's only local transcript")
      } catch APIError.httpError(let status, let detail) {
        XCTAssertEqual(status, 410)
        XCTAssertEqual(detail, "Conversation was deleted")
      }
    }
  }

  func testDeletionCodeAtAnotherEndpointRemainsGeneric() async throws {
    struct Response: Decodable { let id: String }
    let client = await makeClient()
    SegmentUploadErrorURLStub.configure(
      body:
        #"{"detail":{"code":"conversation_deleted","message":"Conversation was deleted"}}"#)
    do {
      let _: Response = try await client.post("v1/unrelated", body: ["synthetic": "value"])
      XCTFail("A deletion-shaped response from another route cannot retire a recording")
    } catch APIError.httpError(let status, let detail) {
      XCTAssertEqual(status, 410)
      XCTAssertEqual(detail, "Conversation was deleted")
    }
  }

  func testDeletionCodeWithout410DoesNotAuthorizeRetirement() async throws {
    let client = await makeClient()
    SegmentUploadErrorURLStub.configure(
      status: 503,
      body:
        #"{"detail":{"code":"conversation_deleted","message":"Conversation was deleted"}}"#)
    do {
      _ = try await client.createConversationFromSegments(upload())
      XCTFail("The complete receipt contract includes HTTP 410")
    } catch APIError.httpError(let status, _) {
      XCTAssertEqual(status, 503)
    }
  }

  func testWrongHTTPMethodAtUploadEndpointRemainsGeneric() async throws {
    struct Response: Decodable { let id: String }
    let client = await makeClient()
    SegmentUploadErrorURLStub.configure(
      body:
        #"{"detail":{"code":"conversation_deleted","message":"Conversation was deleted"}}"#)
    do {
      let _: Response = try await client.get("v1/conversations/from-segments")
      XCTFail("Only a transcript upload response can authorize retirement")
    } catch APIError.httpError(let status, _) {
      XCTAssertEqual(status, 410)
    }
  }

  func testErrorPayloadPreservesStringDetailsAndAllExistingFields() throws {
    let payload = try JSONDecoder().decode(
      APIErrorPayload.self,
      from: Data(
        #"{"error":"failure","code":"existing_code","message":"message","detail":"string detail","provider":"gemini","reason":"reason","backend_route":"route","upstream_status_code":429,"retryable":true,"retry_after_seconds":20}"#
          .utf8))
    XCTAssertEqual(
      payload,
      APIErrorPayload(
        error: "failure", code: "existing_code", message: "message",
        detail: "string detail", provider: "gemini", reason: "reason", backendRoute: "route", upstreamStatusCode: 429,
        retryable: true, retryAfterSeconds: 20))
    XCTAssertEqual(payload.preferredMessage, "string detail")
  }

  func testStructuredDetailLiftsCodeAndReadableMessageWithoutLosingOtherMetadata() throws {
    let payload = try JSONDecoder().decode(
      APIErrorPayload.self,
      from: Data(
        #"{"detail":{"code":"conversation_deleted","message":"Conversation was deleted"},"provider":"gemini","upstream_status_code":410,"retryable":false}"#
          .utf8))
    XCTAssertEqual(payload.code, "conversation_deleted")
    XCTAssertEqual(payload.detail, "Conversation was deleted")
    XCTAssertEqual(payload.preferredMessage, "Conversation was deleted")
    XCTAssertEqual(payload.provider, "gemini")
    XCTAssertEqual(payload.upstreamStatusCode, 410)
    XCTAssertEqual(payload.retryable, false)
  }

  func testMalformedStructuredCodeCannotBecomeDeletionAuthority() throws {
    let payload = try JSONDecoder().decode(
      APIErrorPayload.self, from: Data(#"{"detail":{"code":410,"message":"Conversation was deleted"}}"#.utf8))
    XCTAssertNil(payload.code)
    XCTAssertEqual(payload.detail, "Conversation was deleted")
  }

  private func makeClient() async -> APIClient {
    let config = URLSessionConfiguration.ephemeral
    config.protocolClasses = [SegmentUploadErrorURLStub.self]
    let client = APIClient(session: URLSession(configuration: config))
    await client.setTestAuthHeader("Bearer synthetic-token")
    return client
  }

  private func upload() -> APIClient.CreateConversationFromSegmentsRequest {
    .init(
      transcript_segments: [
        .init(
          text: "Synthetic local copy", speaker: "SPEAKER_00", speaker_id: 0, is_user: false, person_id: nil,
          start: 0, end: 1)
      ], source: "desktop", started_at: nil, finished_at: nil, language: "en",
      client_conversation_id: "synthetic-session",
      conversation_role: "ambient", conversation_finalization_reason: nil, client_processing: nil, captureEvidence: nil)
  }
}
