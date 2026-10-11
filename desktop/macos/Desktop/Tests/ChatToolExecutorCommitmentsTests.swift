import Foundation
import XCTest

@testable import Omi_Computer

private let commitmentsFixture = #"""
  {
    "tool_name": "get_commitments",
    "result_text": "Open commitments you made to other people since 2026-09-11:",
    "is_error": false,
    "sources": [
      {"kind": "conversation", "source_id": "conv-priya", "title": "Pricing call",
       "preview": "Sure, I'll send it Friday.", "created_at": "2026-10-09T17:00:00+00:00"},
      {"kind": "conversation", "source_id": "conv-standup", "title": "Standup",
       "preview": "I'll write it up.", "created_at": "2026-10-08T16:00:00+00:00"}
    ],
    "since": "2026-09-11T12:00:00+00:00",
    "groups": [
      {"names": ["Priya"], "person_ids": ["p-priya"], "basis": "speaker", "likely": false, "open_count": 7,
       "commitments": [
         {"task_id": "task-1", "description": "Send Priya the pricing sheet",
          "due_at": "2026-10-17T00:00:00+00:00", "due_certainty": "confirmed",
          "created_at": "2026-10-09T17:05:00+00:00", "conversation_id": "conv-priya",
          "conversation_title": "Pricing call", "conversation_started_at": "2026-10-09T17:00:00+00:00",
          "excerpt": "Sure, I'll send it Friday.", "context": "Needed for the board meeting.",
          "attribution": {"names": ["Priya"], "person_ids": ["p-priya"], "basis": "speaker", "likely": false}}
       ]},
      {"names": ["Dana Lee"], "person_ids": ["p-dana"], "basis": "conversation", "likely": true,
       "partial_match": true, "open_count": 1,
       "commitments": [
         {"task_id": "task-3", "description": "Share the notes", "conversation_id": "conv-standup",
          "partial_match": true,
          "attribution": {"names": ["Dana Lee"], "person_ids": ["p-dana"], "basis": "conversation", "likely": true}}
       ]}
    ],
    "unattributed": [
      {"task_id": "task-2", "description": "Write up the standup notes",
       "created_at": "2026-10-08T16:05:00+00:00", "conversation_id": "conv-standup",
       "attribution": {"names": [], "person_ids": [], "basis": "none"}, "future_field": true}
    ],
    "totals": {"people": 3, "commitments": 9, "unattributed": 1, "excluded_unknown_owner": 2, "not_checked": 4},
    "truncated": true,
    "a_newer_backend_field": {"ignored": true}
  }
  """#

/// Serves one canned response and records the request, so the real APIClient path
/// (route, query encoding, decoding, HTTP errors) runs without a network.
private final class CommitmentsURLProtocol: URLProtocol, @unchecked Sendable {
  private static let lock = NSLock()
  nonisolated(unsafe) private static var status = 200
  nonisolated(unsafe) private static var recorded: URLRequest?

  static func serve(status: Int) {
    lock.withLock {
      Self.status = status
      recorded = nil
    }
  }

  static var lastRequest: URLRequest? { lock.withLock { recorded } }

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    let status = Self.lock.withLock {
      Self.recorded = request
      return Self.status
    }
    guard let url = request.url,
      let response = HTTPURLResponse(
        url: url, statusCode: status, httpVersion: nil,
        headerFields: ["Content-Type": "application/json"])
    else {
      client?.urlProtocol(self, didFailWithError: URLError(.badURL))
      return
    }
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: Data((status == 200 ? commitmentsFixture : #"{"detail":"Not Found"}"#).utf8))
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}
}

@MainActor
final class ChatToolExecutorCommitmentsTests: XCTestCase {
  private final class CallLog: @unchecked Sendable {
    private let lock = NSLock()
    private var calls: [(since: String?, person: String?, limitPeople: Int)] = []

    func record(_ since: String?, _ person: String?, _ limitPeople: Int) {
      lock.withLock { calls.append((since, person, limitPeople)) }
    }

    var all: [(since: String?, person: String?, limitPeople: Int)] { lock.withLock { calls } }
  }

  private func fixtureResponse(_ json: String = commitmentsFixture) throws -> APIClient.CommitmentsToolResponse {
    try JSONDecoder().decode(APIClient.CommitmentsToolResponse.self, from: Data(json.utf8))
  }

  private func object(_ result: String) throws -> [String: Any] {
    try XCTUnwrap(JSONSerialization.jsonObject(with: Data(result.utf8)) as? [String: Any])
  }

  private func section(_ name: String, in result: [String: Any]) throws -> [String: Any] {
    let sections = try XCTUnwrap(result["sections"] as? [[String: Any]])
    return try XCTUnwrap(sections.first { $0["name"] as? String == name })
  }

  private func run(
    _ arguments: [String: Any] = [:],
    runID: String? = nil,
    ownerIsCurrent: @escaping (String?) -> Bool = { _ in true },
    log: CallLog = CallLog(),
    fetch: (@Sendable () throws -> APIClient.CommitmentsToolResponse)? = nil
  ) async throws -> String {
    let response = try fixtureResponse()
    return await ChatToolExecutor.executeGetCommitments(
      arguments,
      runID: runID ?? "run-\(UUID().uuidString)",
      attemptID: "attempt-1",
      expectedOwnerID: "owner-a",
      ownerIsCurrent: ownerIsCurrent,
      fetch: { since, person, limitPeople in
        log.record(since, person, limitPeople)
        return try fetch?() ?? response
      })
  }

  func testDecodesTheBackendFixtureIntoPeopleCommitmentsAndUnattributedSections() async throws {
    let result = try object(try await run())

    XCTAssertEqual(result["ok"] as? Bool, true)
    XCTAssertEqual(result["tool"] as? String, "get_commitments")
    XCTAssertEqual(
      result["totals"] as? [String: Int],
      ["people": 3, "commitments": 9, "unattributed": 1, "excludedUnknownOwner": 2, "notChecked": 4, "truncated": 1])

    let window = try section("window", in: result)
    XCTAssertEqual(
      (window["items"] as? [[String: Any]])?.first?["since"] as? String, "2026-09-11T12:00:00+00:00")

    let people = try section("people", in: result)
    XCTAssertEqual(people["total"] as? Int, 3)
    let person = try XCTUnwrap((people["items"] as? [[String: Any]])?.first)
    XCTAssertEqual(person["person"] as? String, "Priya")
    XCTAssertEqual(person["basis"] as? String, "speaker")
    XCTAssertEqual(person["likely"] as? Bool, false)
    XCTAssertEqual(person["openCount"] as? Int, 7)
    let hedged = try XCTUnwrap((people["items"] as? [[String: Any]])?.last)
    XCTAssertEqual(hedged["person"] as? String, "Dana Lee")
    XCTAssertEqual(hedged["likely"] as? Bool, true)
    XCTAssertEqual(hedged["partialMatch"] as? Bool, true)
    XCTAssertEqual(person["partialMatch"] as? Bool, false)
    XCTAssertEqual(person["shown"] as? Int, 1)

    let commitments = try section("commitments", in: result)
    XCTAssertEqual(commitments["total"] as? Int, 9)
    let item = try XCTUnwrap((commitments["items"] as? [[String: Any]])?.first)
    XCTAssertEqual(item["taskId"] as? String, "task-1")
    XCTAssertEqual(item["title"] as? String, "Send Priya the pricing sheet")
    XCTAssertEqual(item["person"] as? String, "Priya")
    XCTAssertEqual(item["dueAt"] as? String, "2026-10-17T00:00:00+00:00")
    XCTAssertEqual(item["dueCertainty"] as? String, "confirmed")
    XCTAssertEqual(item["excerpt"] as? String, "Sure, I'll send it Friday.")
    XCTAssertEqual(item["context"] as? String, "Needed for the board meeting.")
    XCTAssertEqual(item["conversationId"] as? String, "conv-priya")
    XCTAssertEqual(item["likely"] as? Bool, false)
    let hedgedItem = try XCTUnwrap((commitments["items"] as? [[String: Any]])?.last)
    XCTAssertEqual(hedgedItem["taskId"] as? String, "task-3")
    XCTAssertEqual(hedgedItem["likely"] as? Bool, true)
    XCTAssertEqual(hedgedItem["partialMatch"] as? Bool, true)
    XCTAssertEqual(item["partialMatch"] as? Bool, false)

    let unattributed = try section("unattributed", in: result)
    let loose = try XCTUnwrap((unattributed["items"] as? [[String: Any]])?.first)
    XCTAssertEqual(loose["taskId"] as? String, "task-2")
    XCTAssertEqual(loose["basis"] as? String, "none")
    XCTAssertNil(loose["person"])
    XCTAssertNil(loose["excerpt"])
  }

  func testEachCommitmentCarriesTheCitationMarkerOfItsConversation() async throws {
    let runID = "run-\(UUID().uuidString)"
    let result = try object(try await run(runID: runID))

    let references = await ChatCitationProvenanceRegistry.shared.consume(runID: runID, attemptID: "attempt-1")
    let ordinals = Dictionary(references.map { ($0.sourceID, $0.ordinal) }, uniquingKeysWith: { first, _ in first })
    XCTAssertEqual(Set(references.map(\.kind)), [.conversation])
    let priya = try XCTUnwrap(ordinals["conv-priya"])
    let standup = try XCTUnwrap(ordinals["conv-standup"])

    let item = try XCTUnwrap((try section("commitments", in: result)["items"] as? [[String: Any]])?.first)
    XCTAssertEqual(item["citationMarker"] as? String, "[\(priya)]")
    let loose = try XCTUnwrap((try section("unattributed", in: result)["items"] as? [[String: Any]])?.first)
    XCTAssertEqual(loose["citationMarker"] as? String, "[\(standup)]")
  }

  func testOwnerSwitchDuringTheCallDropsTheResult() async throws {
    final class Owner: @unchecked Sendable { var current = true }
    let owner = Owner()
    let response = try fixtureResponse()

    let result = try await run(
      ownerIsCurrent: { _ in owner.current },
      fetch: {
        owner.current = false
        return response
      })

    XCTAssertEqual(result, ChatToolExecutor.authorizedOwnerChangedResult())
    XCTAssertFalse(result.contains("Priya"))
  }

  func testBackendErrorBecomesAFailureEnvelope() async throws {
    let failed = try fixtureResponse(
      #"{"tool_name":"get_commitments","result_text":"Error: Could not load commitments right now.","is_error":true,"sources":[]}"#
    )
    XCTAssertTrue(failed.groups.isEmpty)
    XCTAssertEqual(failed.totals.people, 0)

    let result = try object(try await run(fetch: { failed }))

    XCTAssertEqual(result["ok"] as? Bool, false)
    let error = try XCTUnwrap(result["error"] as? [String: Any])
    XCTAssertEqual(error["code"] as? String, "backend_tool_failed")
    XCTAssertEqual(error["message"] as? String, "Error: Could not load commitments right now.")
  }

  func testOlderBackendWithoutTheRouteReturnsCommitmentsUnavailable() async throws {
    let result = try object(try await run(fetch: { throw APIError.httpError(statusCode: 404) }))

    XCTAssertEqual(result["ok"] as? Bool, false)
    let error = try XCTUnwrap(result["error"] as? [String: Any])
    XCTAssertEqual(error["code"] as? String, "commitments_unavailable")
    XCTAssertTrue((error["message"] as? String ?? "").contains("get_action_items"))
  }

  func testOtherTransportFailuresAreReportedAsUnreachable() async throws {
    let result = try object(
      try await run(fetch: { throw APIError.httpError(statusCode: 503, detail: "upstream said Send Priya the deck") }))

    let error = try XCTUnwrap(result["error"] as? [String: Any])
    XCTAssertEqual(error["code"] as? String, "backend_tool_unreachable")
    // A fixed message: transport error text never reaches the model.
    XCTAssertFalse((error["message"] as? String ?? "").contains("Priya"))
  }

  func testOwnerSwitchDuringCitationRegistrationDropsTheResult() async throws {
    final class Checks: @unchecked Sendable { var count = 0 }
    let checks = Checks()

    // The first owner check (after the fetch) passes; the second (after the
    // citations were registered) sees another account.
    let result = try await run(ownerIsCurrent: { _ in
      checks.count += 1
      return checks.count < 2
    })

    XCTAssertEqual(checks.count, 2)
    XCTAssertEqual(result, ChatToolExecutor.authorizedOwnerChangedResult())
    XCTAssertFalse(result.contains("Priya"))
  }

  func testPersonFilterIsCutOnUnicodeScalarsToMatchTheServerLimit() {
    // "é" written as e + combining acute: 2 scalars, 1 grapheme cluster.
    let decomposed = String(repeating: "e\u{301}", count: 100)
    let bounded = ChatToolExecutor.boundedPersonFilter(decomposed)
    XCTAssertEqual(bounded.unicodeScalars.count, ChatToolExecutor.commitmentsMaxPersonCharacters)
    XCTAssertEqual(ChatToolExecutor.boundedPersonFilter("Priya"), "Priya")
  }

  func testInvalidSinceIsRejectedBeforeAnyNetworkCall() async throws {
    let log = CallLog()
    for since in ["last week", "2026-10-04", "2026-10-04T00:00:00"] {
      let result = try object(try await run(["since": since], log: log))
      XCTAssertEqual(result["ok"] as? Bool, false, since)
      let error = try XCTUnwrap(result["error"] as? [String: Any])
      XCTAssertEqual(error["code"] as? String, "invalid_argument", since)
    }
    XCTAssertTrue(log.all.isEmpty)
  }

  func testArgumentsAreNormalizedBeforeTheRequest() async throws {
    let log = CallLog()
    _ = try await run([:], log: log)
    _ = try await run(["limit_people": 0, "person": "   "], log: log)
    _ = try await run(["limit_people": 50.0, "since": "2026-10-04T00:00:00-07:00"], log: log)
    _ = try await run(["person": "  Priya  ", "limit_people": 3], log: log)
    _ = try await run(["person": String(repeating: "x", count: 300)], log: log)

    let calls = log.all
    XCTAssertEqual(calls.count, 5)
    XCTAssertEqual(calls[0].limitPeople, 10)
    XCTAssertNil(calls[0].since)
    XCTAssertNil(calls[0].person)
    XCTAssertEqual(calls[1].limitPeople, 1)
    XCTAssertNil(calls[1].person)
    XCTAssertEqual(calls[2].limitPeople, 20)
    XCTAssertEqual(calls[2].since, "2026-10-04T00:00:00-07:00")
    XCTAssertEqual(calls[3].person, "Priya")
    XCTAssertEqual(calls[3].limitPeople, 3)
    XCTAssertEqual(calls[4].person?.count, ChatToolExecutor.commitmentsMaxPersonCharacters)
  }

  func testEmptyReadIsASuccessfulEmptyResult() async throws {
    let empty = try fixtureResponse(
      #"{"tool_name":"get_commitments","result_text":"No open commitments to other people found since 2026-09-11.","is_error":false,"sources":[],"groups":[],"unattributed":[],"totals":{"people":0,"commitments":0,"unattributed":0,"excluded_unknown_owner":0},"truncated":false}"#
    )

    let result = try object(try await run(fetch: { empty }))

    XCTAssertEqual(result["ok"] as? Bool, true)
    XCTAssertEqual(
      result["totals"] as? [String: Int],
      ["people": 0, "commitments": 0, "unattributed": 0, "excludedUnknownOwner": 0, "notChecked": 0, "truncated": 0])
    XCTAssertEqual((try section("commitments", in: result)["items"] as? [Any])?.count, 0)
  }

  private func stubClient(status: Int) async -> APIClient {
    CommitmentsURLProtocol.serve(status: status)
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [CommitmentsURLProtocol.self]
    let client = APIClient(session: URLSession(configuration: configuration))
    await client.setCommitmentsTestAuthHeader("Bearer test-token")
    return client
  }

  func testAPIClientCallsTheReadOnlyRouteWithAnEncodedQuery() async throws {
    let client = await stubClient(status: 200)

    let response = try await client.toolGetCommitments(
      since: "2026-10-04T00:00:00+07:00", person: "Ana & Bo=1#x", limitPeople: 4)

    XCTAssertEqual(response.groups.first?.names, ["Priya"])
    XCTAssertEqual(response.totals.excludedUnknownOwner, 2)
    XCTAssertTrue(response.truncated)
    let request = try XCTUnwrap(CommitmentsURLProtocol.lastRequest)
    XCTAssertEqual(request.httpMethod, "GET")
    let url = try XCTUnwrap(request.url?.absoluteString)
    XCTAssertTrue(url.contains("v1/tools/commitments?limit_people=4"), url)
    XCTAssertTrue(url.contains("&since=2026-10-04T00:00:00%2B07:00"), url)
    XCTAssertTrue(url.contains("&person=Ana%20%26%20Bo%3D1%23x"), url)
    XCTAssertFalse(url.contains("owner"), url)
  }

  func testAPIClientSurfacesA404AsAnHTTPError() async throws {
    let client = await stubClient(status: 404)

    do {
      _ = try await client.toolGetCommitments()
      XCTFail("expected a 404")
    } catch APIError.httpError(statusCode: 404, _) {
      // expected: the executor maps this to commitments_unavailable
    }
  }
}

extension APIClient {
  fileprivate func setCommitmentsTestAuthHeader(_ header: String) {
    testAuthHeader = header
  }
}
