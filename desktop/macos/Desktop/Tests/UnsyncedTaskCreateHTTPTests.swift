import Foundation
import XCTest

@testable import Omi_Computer

extension APIClient {
  fileprivate func setUnsyncedCreateTestAuthorization(_ value: String) {
    testAuthHeader = value
  }
}

private struct UnsyncedCreateCapturedRequest {
  let method: String?
  let path: String?
  let body: Data?
  let authorization: String?
}

private final class UnsyncedCreateRequestCapture: @unchecked Sendable {
  private let lock = NSLock()
  private var requests: [UnsyncedCreateCapturedRequest] = []
  let statusCode: Int

  init(statusCode: Int) { self.statusCode = statusCode }

  func record(_ request: URLRequest, body: Data?) {
    lock.withLock {
      requests.append(
        UnsyncedCreateCapturedRequest(
          method: request.httpMethod,
          path: request.url?.path,
          body: body,
          authorization: request.value(forHTTPHeaderField: "Authorization")))
    }
  }

  var capturedRequests: [UnsyncedCreateCapturedRequest] {
    lock.withLock { requests }
  }
}

private final class UnsyncedCreateCaptureRegistry: @unchecked Sendable {
  private let lock = NSLock()
  private var captures: [String: UnsyncedCreateRequestCapture] = [:]

  func register(_ capture: UnsyncedCreateRequestCapture, id: String) {
    lock.withLock { captures[id] = capture }
  }

  func capture(id: String?) -> UnsyncedCreateRequestCapture? {
    guard let id else { return nil }
    return lock.withLock { captures[id] }
  }

  func remove(id: String) {
    _ = lock.withLock { captures.removeValue(forKey: id) }
  }
}

/// Every isolated URLSession request is intercepted. A unique additional
/// session header routes it to one test's capture; no process-global response
/// slot, live auth request, or destination network connection is involved.
private final class UnsyncedCreateURLProtocol: URLProtocol, @unchecked Sendable {
  static let captureHeader = "X-Omi-Unsynced-Create-Test"
  static let registry = UnsyncedCreateCaptureRegistry()

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    guard let capture = Self.registry.capture(id: request.value(forHTTPHeaderField: Self.captureHeader)),
      let url = request.url,
      let response = HTTPURLResponse(
        url: url, statusCode: capture.statusCode, httpVersion: nil,
        headerFields: ["Content-Type": "application/json"])
    else {
      client?.urlProtocol(self, didFailWithError: URLError(.badServerResponse))
      return
    }
    let requestBody = Self.bodyData(from: request)
    capture.record(request, body: requestBody)
    let responseBody: Data
    if capture.statusCode == 200 {
      guard let requestBody,
        let body = try? JSONSerialization.jsonObject(with: requestBody) as? [String: Any],
        let description = body["description"] as? String
      else {
        client?.urlProtocol(self, didFailWithError: URLError(.cannotParseResponse))
        return
      }
      let completed = (body["completed"] as? Bool) ?? (body["status"] as? String == "completed")
      let status = (body["status"] as? String) ?? (completed ? "completed" : "active")
      guard
        let data = try? JSONSerialization.data(
          withJSONObject: [
            "id": "created-task", "description": description, "completed": completed,
            "status": status, "created_at": "2026-10-08T00:00:00Z",
          ])
      else {
        client?.urlProtocol(self, didFailWithError: URLError(.cannotParseResponse))
        return
      }
      responseBody = data
    } else {
      responseBody = Data(#"{"detail":"Temporary task creation failure"}"#.utf8)
    }
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: responseBody)
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}

  private static func bodyData(from request: URLRequest) -> Data? {
    if let body = request.httpBody { return body }
    guard let stream = request.httpBodyStream else { return nil }
    stream.open()
    defer { stream.close() }
    var data = Data()
    let buffer = UnsafeMutablePointer<UInt8>.allocate(capacity: 4096)
    defer { buffer.deallocate() }
    while stream.hasBytesAvailable {
      let count = stream.read(buffer, maxLength: 4096)
      guard count > 0 else { break }
      data.append(buffer, count: count)
    }
    return data.isEmpty ? nil : data
  }
}

final class UnsyncedTaskCreateHTTPTests: XCTestCase {
  @MainActor
  func testActualRetryPostsLatestCompletedRecurringTaskOnceAndMarksItsReceipt() async throws {
    let (client, capture, authorization) = try await prepareClient()
    let dueAt = Date(timeIntervalSince1970: 1_800_000_000)
    let enumerated = ActionItemRecord(id: 7, description: "Outdated pending snapshot")
    let current = ActionItemRecord(
      id: 7,
      description: "Latest local description",
      completed: true,
      source: "manual",
      conversationId: "conversation-1",
      priority: "high",
      category: "work",
      dueAt: dueAt,
      recurrenceRule: "weekly",
      recurrenceParentId: "series-1",
      canonicalTaskId: "never-create-this-canonical-id",
      taskStatus: "active",
      taskOwner: "user",
      goalId: "goal-1",
      workstreamId: "workstream-1",
      dueConfidence: 0.95,
      provenanceJson: #"[{"id":"conversation-1","kind":"conversation","scope":"canonical","version":"revision-2"}]"#,
      supersededBy: "never-create-this-lineage-id",
      isLocked: true,
      screenshotId: 72,
      sourceApp: "Local-only app",
      windowTitle: "Local-only title",
      contextSummary: "Local-only summary",
      currentActivity: "Local-only activity",
      metadataJson: #"{"tags":["report"],"note":"latest metadata"}"#,
      sortOrder: 12,
      indentLevel: 2,
      relevanceScore: 83,
      agentStatus: "completed",
      agentSessionName: "local-session",
      agentPrompt: "Local agent prompt",
      agentPlan: "Local agent plan",
      chatSessionId: "local-chat",
      fromStaged: true)
    var marked: [(Int64, String)] = []
    var flushes = 0

    await TasksStore.shared.retryUnsyncedItems(
      includeRecent: true,
      authorizationSnapshot: authorization,
      operations: UnsyncedTaskSyncOperations(
        allowsUpload: { true },
        loadPending: { _ in [enumerated] },
        reloadCurrent: { id in
          XCTAssertEqual(id, 7)
          return current
        },
        createRemote: { projection, capturedAuthorization in
          XCTAssertEqual(capturedAuthorization, authorization)
          let created = try await projection.create(using: client, authorizationSnapshot: capturedAuthorization)
          XCTAssertEqual(created.description, current.description)
          XCTAssertTrue(created.completed)
          XCTAssertEqual(created.taskStatus, "completed")
          return created
        },
        markSynced: { id, backendID, capturedAuthorization in
          try capturedAuthorization.require()
          marked.append((id, backendID))
        },
        flushDeletions: { flushes += 1 }))

    let request = try XCTUnwrap(capture.capturedRequests.only)
    XCTAssertEqual(request.method, "POST")
    XCTAssertEqual(request.path, "/v1/action-items")
    XCTAssertEqual(request.authorization, "Bearer isolated-task-create-test")
    let body = try requestBody(request)
    XCTAssertEqual(body["description"] as? String, current.description)
    XCTAssertEqual(body["completed"] as? Bool, true)
    XCTAssertEqual(body["status"] as? String, "completed")
    XCTAssertEqual(body["source"] as? String, "manual")
    XCTAssertEqual(body["priority"] as? String, "high")
    XCTAssertEqual(body["category"] as? String, "work")
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    XCTAssertEqual(body["due_at"] as? String, formatter.string(from: dueAt))
    XCTAssertEqual(body["recurrence_rule"] as? String, "weekly")
    XCTAssertEqual(body["recurrence_parent_id"] as? String, "series-1")
    XCTAssertEqual(body["goal_id"] as? String, "goal-1")
    XCTAssertEqual(body["workstream_id"] as? String, "workstream-1")
    XCTAssertEqual(body["owner"] as? String, "user")
    XCTAssertEqual(body["due_confidence"] as? Double, 0.95)
    XCTAssertEqual(body["sort_order"] as? Int, 12)
    XCTAssertEqual(body["indent_level"] as? Int, 2)
    XCTAssertEqual(body["relevance_score"] as? Int, 83)
    XCTAssertEqual(body["conversation_id"] as? String, "conversation-1")
    XCTAssertEqual(body["is_locked"] as? Bool, true)
    let provenance = try XCTUnwrap(body["provenance"] as? [[String: Any]])
    XCTAssertEqual(provenance.count, 1)
    XCTAssertEqual(provenance.first?["id"] as? String, "conversation-1")
    XCTAssertEqual(provenance.first?["version"] as? String, "revision-2")
    let metadata = try XCTUnwrap(body["metadata"] as? String)
    let metadataObject = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(metadata.utf8)) as? [String: Any])
    XCTAssertEqual(metadataObject["tags"] as? [String], ["report"])
    XCTAssertEqual(metadataObject["note"] as? String, "latest metadata")
    for key in [
      "task_id", "canonical_task_id", "superseded_by", "screenshot_id", "source_app", "window_title",
      "context_summary", "current_activity", "agent_status", "agent_session_name", "agent_prompt", "agent_plan",
      "chat_session_id", "from_staged",
    ] {
      XCTAssertNil(body[key], "Local execution or server-owned identity must not be sent: \(key)")
    }
    XCTAssertEqual(marked.count, 1)
    XCTAssertEqual(marked.first?.0, 7)
    XCTAssertEqual(marked.first?.1, "created-task")
    XCTAssertEqual(flushes, 1)
  }

  @MainActor
  func testActualRetryKeepsAbsentAndFalseDefaultsOutOfTheCreateBody() async throws {
    let (client, capture, authorization) = try await prepareClient()
    let record = ActionItemRecord(id: 8, description: "Plain local task")
    var marked: [String] = []

    await TasksStore.shared.retryUnsyncedItems(
      authorizationSnapshot: authorization,
      operations: UnsyncedTaskSyncOperations(
        allowsUpload: { true },
        loadPending: { _ in [record] },
        reloadCurrent: { _ in record },
        createRemote: { projection, capturedAuthorization in
          try await projection.create(using: client, authorizationSnapshot: capturedAuthorization)
        },
        markSynced: { _, backendID, capturedAuthorization in
          try capturedAuthorization.require()
          marked.append(backendID)
        },
        flushDeletions: {}))

    let request = try XCTUnwrap(capture.capturedRequests.only)
    XCTAssertEqual(request.method, "POST")
    let body = try requestBody(request)
    XCTAssertEqual(Set(body.keys), ["description"])
    XCTAssertEqual(body["description"] as? String, "Plain local task")
    XCTAssertEqual(marked, ["created-task"])
  }

  @MainActor
  func testHTTPFailureLeavesTheActualRetryUnmarked() async throws {
    let (client, capture, authorization) = try await prepareClient(statusCode: 503)
    let record = ActionItemRecord(id: 9, description: "Still pending", recurrenceRule: "daily")
    var marks = 0
    var flushes = 0

    await TasksStore.shared.retryUnsyncedItems(
      authorizationSnapshot: authorization,
      operations: UnsyncedTaskSyncOperations(
        allowsUpload: { true },
        loadPending: { _ in [record] },
        reloadCurrent: { _ in record },
        createRemote: { projection, capturedAuthorization in
          try await projection.create(using: client, authorizationSnapshot: capturedAuthorization)
        },
        markSynced: { _, _, capturedAuthorization in
          try capturedAuthorization.require()
          marks += 1
        },
        flushDeletions: { flushes += 1 }))

    let request = try XCTUnwrap(capture.capturedRequests.only)
    XCTAssertEqual(request.method, "POST")
    XCTAssertEqual(try requestBody(request)["recurrence_rule"] as? String, "daily")
    XCTAssertEqual(marks, 0, "A rejected create cannot acknowledge a pending local row")
    XCTAssertEqual(flushes, 1)
  }

  @MainActor
  private func prepareClient(statusCode: Int = 200) async throws
    -> (APIClient, UnsyncedCreateRequestCapture, RuntimeOwnerAuthorizationSnapshot)
  {
    let ownerFixture = TaskSyncOwnerTestFixture()
    addTeardownBlock { @MainActor in
      try await ownerFixture.restore()
      TasksStore.shared.resetSessionState()
    }
    try await ownerFixture.establish(ownerID: "task-create-http-\(UUID().uuidString)")
    TasksStore.shared.resetSessionState()
    let authorization = try XCTUnwrap(RuntimeOwnerIdentity.captureAuthorizationSnapshot())
    let capture = UnsyncedCreateRequestCapture(statusCode: statusCode)
    let captureID = UUID().uuidString
    UnsyncedCreateURLProtocol.registry.register(capture, id: captureID)
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [UnsyncedCreateURLProtocol.self]
    configuration.httpAdditionalHeaders = [UnsyncedCreateURLProtocol.captureHeader: captureID]
    let session = URLSession(configuration: configuration)
    addTeardownBlock {
      session.invalidateAndCancel()
      UnsyncedCreateURLProtocol.registry.remove(id: captureID)
    }
    let client = APIClient(session: session)
    await client.setUnsyncedCreateTestAuthorization("Bearer isolated-task-create-test")
    return (client, capture, authorization)
  }

  private func requestBody(_ request: UnsyncedCreateCapturedRequest) throws -> [String: Any] {
    let data = try XCTUnwrap(request.body)
    return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
  }
}

extension Array where Element == UnsyncedCreateCapturedRequest {
  fileprivate var only: UnsyncedCreateCapturedRequest? { count == 1 ? first : nil }
}
