import XCTest

@testable import Omi_Computer

private struct CapturedCandidateRequest {
  let url: URL
  let method: String
  let headers: [String: String]
  let body: Data?
}

private final class CandidateURLCapture: URLProtocol, @unchecked Sendable {
  private static let lock = NSLock()
  private static var request: CapturedCandidateRequest?

  static func reset() {
    lock.lock()
    request = nil
    lock.unlock()
  }

  static func captured() -> CapturedCandidateRequest? {
    lock.lock()
    defer { lock.unlock() }
    return request
  }

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    Self.lock.lock()
    Self.request = CapturedCandidateRequest(
      url: request.url!,
      method: request.httpMethod ?? "GET",
      headers: request.allHTTPHeaderFields ?? [:],
      body: Self.bodyData(from: request)
    )
    Self.lock.unlock()

    let response = HTTPURLResponse(
      url: request.url!, statusCode: 503, httpVersion: nil, headerFields: nil)!
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: Data("{}".utf8))
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
      if count <= 0 { break }
      data.append(buffer, count: count)
    }
    return data
  }
}

final class APIClientCandidateTests: XCTestCase {
  override func setUp() {
    super.setUp()
    CandidateURLCapture.reset()
    setenv("OMI_PYTHON_API_URL", "http://python-test:9001", 1)
  }

  override func tearDown() {
    unsetenv("OMI_PYTHON_API_URL")
    CandidateURLCapture.reset()
    super.tearDown()
  }

  func testCreateCandidateSendsGenerationIdempotencyAndPrivacySafeEvidence() async throws {
    let config = URLSessionConfiguration.ephemeral
    config.protocolClasses = [CandidateURLCapture.self]
    let client = APIClient(session: URLSession(configuration: config))
    await client.setTestAuthHeader("Bearer test-token")
    let candidate = OmiAPI.CandidateCreate.taskCreate(
      OmiAPI.TaskCreateCandidate(
        captureConfidence: 0.95,
        evidenceRefs: [
          OmiAPI.EvidenceRef(
            deviceId: "device-hash",
            excerptHash: nil,
            id: "screen-42",
            kind: .local_screen,
            scope: .device_local,
            version: "capture.v1"
          )
        ],
        goalId: nil,
        ownershipConfidence: 0.95,
        proposedAction: "create",
        sourceSurface: "screen",
        subjectKind: "task",
        taskChange: OmiAPI.TaskCreatePayload(
          description_: "Send Sarah the revised budget",
          dueAt: nil,
          dueConfidence: nil,
          owner: .user,
          priority: .high,
          recurrenceParentId: nil,
          recurrenceRule: nil
        ),
        workstreamId: nil
      )
    )

    do {
      let _: OmiAPI.CandidateRecord = try await client.createCanonicalCandidate(
        candidate,
        idempotencyKey: "screen:device-hash:42",
        accountGeneration: 7
      )
      XCTFail("The stubbed service should fail after capturing the request")
    } catch {
      // The retryable transport failure is expected; request construction is the subject under test.
    }

    let request = try XCTUnwrap(CandidateURLCapture.captured())
    XCTAssertEqual(request.url.path, "/v1/candidates")
    XCTAssertEqual(request.method, "POST")
    XCTAssertEqual(request.headers["Idempotency-Key"], "screen:device-hash:42")
    XCTAssertEqual(request.headers["X-Account-Generation"], "7")
    XCTAssertEqual(request.headers["Authorization"], "Bearer test-token")
    let body = try XCTUnwrap(request.body)
    let json = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
    let evidence = try XCTUnwrap((json["evidence_refs"] as? [[String: Any]])?.first)
    XCTAssertEqual(evidence["kind"] as? String, "local_screen")
    XCTAssertEqual(evidence["scope"] as? String, "device_local")
    XCTAssertEqual(evidence["id"] as? String, "screen-42")
    XCTAssertNil(json["screenshot"])
    XCTAssertNil(json["window_title"])
    XCTAssertNil(json["source_app"])
  }

  func testSuggestedFeedbackSendsStableIdempotencyAndGenerationHeaders() async throws {
    let config = URLSessionConfiguration.ephemeral
    config.protocolClasses = [CandidateURLCapture.self]
    let client = APIClient(session: URLSession(configuration: config))
    await client.setTestAuthHeader("Bearer test-token")

    do {
      let _: OmiAPI.FeedbackRecord = try await client.recordTaskFeedback(
        OmiAPI.FeedbackCreate(
          action: .dismiss,
          contextSnapshotHash: nil,
          interventionId: "intervention-1",
          laterUntil: nil,
          reason: .not_mine,
          subjectId: "candidate-1",
          subjectKind: .candidate
        ),
        idempotencyKey: "suggested:candidate-1:not-mine",
        accountGeneration: 14
      )
      XCTFail("The stubbed service should fail after capturing the request")
    } catch {
      // Expected transport response from the capture protocol.
    }

    let request = try XCTUnwrap(CandidateURLCapture.captured())
    XCTAssertEqual(request.url.path, "/v1/task-intelligence/feedback")
    XCTAssertEqual(request.method, "POST")
    XCTAssertEqual(request.headers["Idempotency-Key"], "suggested:candidate-1:not-mine")
    XCTAssertEqual(request.headers["X-Account-Generation"], "14")
    let body = try XCTUnwrap(request.body)
    let json = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
    XCTAssertEqual(json["action"] as? String, "dismiss")
    XCTAssertEqual(json["reason"] as? String, "not_mine")
    XCTAssertEqual(json["subject_id"] as? String, "candidate-1")
  }

  func testRejectCandidateSendsGenerationAndReason() async throws {
    let config = URLSessionConfiguration.ephemeral
    config.protocolClasses = [CandidateURLCapture.self]
    let client = APIClient(session: URLSession(configuration: config))
    await client.setTestAuthHeader("Bearer test-token")

    do {
      let _: OmiAPI.CandidateResolutionReceipt = try await client.rejectCanonicalCandidate(
        candidateID: "candidate-1",
        reason: "already_handled",
        accountGeneration: 9
      )
      XCTFail("The stubbed service should fail after capturing the request")
    } catch {
      // Expected transport response from the capture protocol.
    }

    let request = try XCTUnwrap(CandidateURLCapture.captured())
    XCTAssertEqual(request.url.path, "/v1/candidates/candidate-1/reject")
    XCTAssertEqual(request.method, "POST")
    XCTAssertEqual(request.headers["X-Account-Generation"], "9")
    let body = try XCTUnwrap(request.body)
    let json = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
    XCTAssertEqual(json["reason"] as? String, "already_handled")
  }

  func testWhatMattersNowUsesCanonicalProjectionEndpoint() async throws {
    let config = URLSessionConfiguration.ephemeral
    config.protocolClasses = [CandidateURLCapture.self]
    let client = APIClient(session: URLSession(configuration: config))
    await client.setTestAuthHeader("Bearer test-token")

    _ = try? await client.getWhatMattersNow(deviceID: "device-hash")

    let request = try XCTUnwrap(CandidateURLCapture.captured())
    XCTAssertEqual(request.url.path, "/v1/what-matters-now")
    XCTAssertEqual(URLComponents(url: request.url, resolvingAgainstBaseURL: false)?.queryItems?.first?.value, "device-hash")
    XCTAssertEqual(request.method, "GET")
  }

  func testContextSnapshotUsesBoundedPutWithoutRawContext() async throws {
    let config = URLSessionConfiguration.ephemeral
    config.protocolClasses = [CandidateURLCapture.self]
    let client = APIClient(session: URLSession(configuration: config))
    await client.setTestAuthHeader("Bearer test-token")
    let snapshot = OmiAPI.NormalizedContextSnapshot(
      deviceId: "device-hash",
      expiresAt: "2027-01-15T08:05:00Z",
      generatedAt: "2027-01-15T08:00:00Z",
      matches: [
        OmiAPI.NormalizedContextMatch(
          signals: [.app, .person],
          subjectId: "workstream-1",
          subjectKind: .workstream
        )
      ],
      schemaVersion: 1,
      snapshotId: "context-1"
    )

    _ = try? await client.replaceTaskContextSnapshot(snapshot)

    let request = try XCTUnwrap(CandidateURLCapture.captured())
    XCTAssertEqual(request.url.path, "/v1/task-intelligence/context-snapshot")
    XCTAssertEqual(request.method, "PUT")
    let json = try XCTUnwrap(JSONSerialization.jsonObject(with: try XCTUnwrap(request.body)) as? [String: Any])
    XCTAssertEqual(json["snapshot_id"] as? String, "context-1")
    XCTAssertNil(json["window_title"])
    XCTAssertNil(json["raw_context"])
    XCTAssertNil(json["screenshot"])
  }

  func testContextReevaluationUsesMaterialHintWithoutMutationHeaders() async throws {
    let config = URLSessionConfiguration.ephemeral
    config.protocolClasses = [CandidateURLCapture.self]
    let client = APIClient(session: URLSession(configuration: config))
    await client.setTestAuthHeader("Bearer test-token")

    _ = try? await client.evaluateWhatMattersNow(
      OmiAPI.EvaluationRequest(deviceId: "device-hash", materialHint: "ctx:abc123")
    )

    let request = try XCTUnwrap(CandidateURLCapture.captured())
    XCTAssertEqual(request.url.path, "/v1/what-matters-now/evaluate")
    XCTAssertEqual(request.method, "POST")
    XCTAssertNil(request.headers["X-Account-Generation"])
    XCTAssertNil(request.headers["Idempotency-Key"])
    let json = try XCTUnwrap(JSONSerialization.jsonObject(with: try XCTUnwrap(request.body)) as? [String: Any])
    XCTAssertEqual(json["device_id"] as? String, "device-hash")
    XCTAssertEqual(json["material_hint"] as? String, "ctx:abc123")
  }

  func testGoalFocusSendsExplicitReplacementAndCanonicalMutationHeaders() async throws {
    let config = URLSessionConfiguration.ephemeral
    config.protocolClasses = [CandidateURLCapture.self]
    let client = APIClient(session: URLSession(configuration: config))
    await client.setTestAuthHeader("Bearer test-token")

    do {
      let _: OmiAPI.GoalResponse = try await client.focusCanonicalGoal(
        goalID: "goal-new",
        replacementGoalID: "goal-old",
        focusRank: 2,
        accountGeneration: 14,
        idempotencyKey: "goal-focus-occurrence"
      )
      XCTFail("The stubbed service should fail after capturing the request")
    } catch {
      // Expected transport response from the capture protocol.
    }

    let request = try XCTUnwrap(CandidateURLCapture.captured())
    XCTAssertEqual(request.url.path, "/v1/goals/goal-new/focus")
    XCTAssertEqual(request.method, "POST")
    XCTAssertEqual(request.headers["X-Account-Generation"], "14")
    XCTAssertEqual(request.headers["Idempotency-Key"], "goal-focus-occurrence")
    let body = try XCTUnwrap(request.body)
    let json = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
    XCTAssertEqual(json["replacement_goal_id"] as? String, "goal-old")
    XCTAssertEqual(json["focus_rank"] as? Int, 2)
  }

  func testCanonicalGoalCreateUsesQualitativeContractWithoutLegacyDescription() async throws {
    let config = URLSessionConfiguration.ephemeral
    config.protocolClasses = [CandidateURLCapture.self]
    let client = APIClient(session: URLSession(configuration: config))
    await client.setTestAuthHeader("Bearer test-token")

    _ = try? await client.createCanonicalGoal(
      title: "Investor pipeline",
      desiredOutcome: "Build a repeatable investor pipeline",
      whyItMatters: "Fund the next stage",
      successCriteria: ["Ten qualified conversations"],
      accountGeneration: 14,
      idempotencyKey: "goal-create-occurrence"
    )

    let request = try XCTUnwrap(CandidateURLCapture.captured())
    XCTAssertEqual(request.url.path, "/v1/goals/canonical")
    XCTAssertEqual(request.method, "POST")
    XCTAssertEqual(request.headers["X-Account-Generation"], "14")
    XCTAssertEqual(request.headers["Idempotency-Key"], "goal-create-occurrence")
    let body = try XCTUnwrap(request.body)
    let json = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
    XCTAssertEqual(json["desired_outcome"] as? String, "Build a repeatable investor pipeline")
    XCTAssertEqual(json["why_it_matters"] as? String, "Fund the next stage")
    XCTAssertEqual(json["success_criteria"] as? [String], ["Ten qualified conversations"])
    XCTAssertNil(json["description"])
  }

  func testResolveTaskWorkIntentUsesDurableIdentityHeadersAndTaskOrigin() async throws {
    let config = URLSessionConfiguration.ephemeral
    config.protocolClasses = [CandidateURLCapture.self]
    let client = APIClient(session: URLSession(configuration: config))
    await client.setTestAuthHeader("Bearer test-token")

    do {
      let _: OmiAPI.WorkIntentReceipt = try await client.resolveTaskWorkIntent(
        taskId: "task-42",
        title: "Draft launch email",
        objective: "Prepare the launch email",
        idempotencyKey: "work-intent:task:task-42",
        accountGeneration: 11
      )
      XCTFail("The stubbed service should fail after capturing the request")
    } catch {
      // Expected transport response from the capture protocol.
    }

    let request = try XCTUnwrap(CandidateURLCapture.captured())
    XCTAssertEqual(request.url.path, "/v1/work-intents")
    XCTAssertEqual(request.method, "POST")
    XCTAssertEqual(request.headers["Idempotency-Key"], "work-intent:task:task-42")
    XCTAssertEqual(request.headers["X-Account-Generation"], "11")
    let body = try XCTUnwrap(request.body)
    let json = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
    XCTAssertEqual(json["origin"] as? String, "task")
    XCTAssertEqual(json["task_id"] as? String, "task-42")
    XCTAssertEqual(json["title"] as? String, "Draft launch email")
    XCTAssertNil(json["goal_id"])
  }

  func testCreateWorkstreamArtifactUsesCanonicalVersionAndMutationHeaders() async throws {
    let config = URLSessionConfiguration.ephemeral
    config.protocolClasses = [CandidateURLCapture.self]
    let client = APIClient(session: URLSession(configuration: config))
    await client.setTestAuthHeader("Bearer test-token")
    let artifact = OmiAPI.ArtifactDescriptorCreate(
      contentHash: "sha256:1234567890abcdef",
      evidenceEventIds: ["event-friday"],
      evidenceRefs: [
        OmiAPI.EvidenceRef(
          deviceId: nil,
          excerptHash: nil,
          id: "conversation-friday",
          kind: .conversation,
          scope: .canonical,
          version: "conversation.v1"
        )
      ],
      kind: "email_draft",
      logicalKey: "launch-email",
      sourceRunId: "run-1",
      supersedesArtifactId: "artifact-v1",
      uri: "file:///tmp/launch-email-v2.md",
      version: 2
    )

    do {
      let _: OmiAPI.ArtifactDescriptor = try await client.createWorkstreamArtifact(
        workstreamId: "workstream-1",
        artifact: artifact,
        idempotencyKey: "workstream-artifact:workstream-1:source-v2",
        accountGeneration: 12
      )
      XCTFail("The stubbed service should fail after capturing the request")
    } catch {
      // Expected transport response from the capture protocol.
    }

    let request = try XCTUnwrap(CandidateURLCapture.captured())
    XCTAssertEqual(request.url.path, "/v1/workstreams/workstream-1/artifacts")
    XCTAssertEqual(request.method, "POST")
    XCTAssertEqual(request.headers["Idempotency-Key"], "workstream-artifact:workstream-1:source-v2")
    XCTAssertEqual(request.headers["X-Account-Generation"], "12")
    let body = try XCTUnwrap(request.body)
    let json = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
    XCTAssertEqual(json["logical_key"] as? String, "launch-email")
    XCTAssertEqual(json["version"] as? Int, 2)
    XCTAssertEqual(json["supersedes_artifact_id"] as? String, "artifact-v1")
    XCTAssertEqual(json["evidence_event_ids"] as? [String], ["event-friday"])
  }
}
