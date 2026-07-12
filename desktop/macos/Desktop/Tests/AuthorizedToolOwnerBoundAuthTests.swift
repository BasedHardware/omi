import Foundation
import XCTest

@testable import Omi_Computer

private extension APIClient {
  func setOwnerBoundTestAuthHeader(_ header: String) {
    testAuthHeader = header
  }
}

private actor AuthorizedToolRequestGate {
  private var pendingProtocol: AuthorizedToolOwnerURLProtocol?
  private var requestWaiters: [CheckedContinuation<URLRequest, Never>] = []

  func reset() {
    pendingProtocol = nil
    requestWaiters.removeAll()
  }

  func receive(_ urlProtocol: AuthorizedToolOwnerURLProtocol) {
    pendingProtocol = urlProtocol
    let waiters = requestWaiters
    requestWaiters.removeAll()
    for waiter in waiters {
      waiter.resume(returning: urlProtocol.request)
    }
  }

  func waitForRequest() async -> URLRequest {
    if let pendingProtocol {
      return pendingProtocol.request
    }
    return await withCheckedContinuation { continuation in
      requestWaiters.append(continuation)
    }
  }

  func succeed(with body: String) {
    guard let pendingProtocol else { return }
    self.pendingProtocol = nil
    let response = HTTPURLResponse(
      url: pendingProtocol.request.url!,
      statusCode: 200,
      httpVersion: nil,
      headerFields: ["Content-Type": "application/json"]
    )!
    pendingProtocol.client?.urlProtocol(
      pendingProtocol,
      didReceive: response,
      cacheStoragePolicy: .notAllowed)
    pendingProtocol.client?.urlProtocol(pendingProtocol, didLoad: Data(body.utf8))
    pendingProtocol.client?.urlProtocolDidFinishLoading(pendingProtocol)
  }
}

private final class AuthorizedToolOwnerURLProtocol: URLProtocol, @unchecked Sendable {
  static let gate = AuthorizedToolRequestGate()

  static func bodyData(from request: URLRequest) -> Data? {
    if let body = request.httpBody { return body }
    guard let stream = request.httpBodyStream else { return nil }
    stream.open()
    defer { stream.close() }
    var data = Data()
    let buffer = UnsafeMutablePointer<UInt8>.allocate(capacity: 4_096)
    defer { buffer.deallocate() }
    while stream.hasBytesAvailable {
      let readCount = stream.read(buffer, maxLength: 4_096)
      if readCount > 0 {
        data.append(buffer, count: readCount)
      } else {
        break
      }
    }
    return data.isEmpty ? nil : data
  }

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    Task {
      await Self.gate.receive(self)
    }
  }

  override func stopLoading() {}
}

@MainActor
final class AuthorizedToolOwnerBoundAuthTests: XCTestCase {
  private var originalAuthOwner: Any?
  private var originalOwnerOverride: Any?
  private var originalOwnerBackup: Any?

  override func setUp() {
    super.setUp()
    originalAuthOwner = UserDefaults.standard.object(forKey: .authUserId)
    originalOwnerOverride = UserDefaults.standard.object(forKey: .automationOwnerOverride)
    originalOwnerBackup = UserDefaults.standard.object(forKey: .automationOwnerABackup)
  }

  override func tearDown() {
    restoreDefault(originalAuthOwner, forKey: .authUserId)
    restoreDefault(originalOwnerOverride, forKey: .automationOwnerOverride)
    restoreDefault(originalOwnerBackup, forKey: .automationOwnerABackup)
    super.tearDown()
  }

  func testMemoryReadRejectsPrivateResponseAfterMidFlightAccountSwitch() async {
    let client = await makeClient()
    let operation = Task { @MainActor in
      await ChatToolExecutor.execute(
        ToolCall(name: "get_memories", arguments: [:], thoughtSignature: nil),
        expectedOwnerID: "owner-a",
        backendAPIClient: client)
    }

    let request = await AuthorizedToolOwnerURLProtocol.gate.waitForRequest()
    XCTAssertEqual(request.httpMethod, "GET")
    XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer owner-a-token")

    UserDefaults.standard.set("owner-b", forKey: .authUserId)
    await AuthorizedToolOwnerURLProtocol.gate.succeed(
      with:
        #"{"tool_name":"get_memories","result_text":"owner-a-private-memory","is_error":false}"#)

    let result = await operation.value
    XCTAssertEqual(result, ChatToolExecutor.authorizedOwnerChangedResult())
    XCTAssertFalse(result.contains("owner-a-private-memory"))
  }

  func testMemoryReadReturnsResponseWhileOriginalOwnerRemainsCurrent() async {
    let client = await makeClient()
    let operation = Task { @MainActor in
      await ChatToolExecutor.execute(
        ToolCall(name: "get_memories", arguments: [:], thoughtSignature: nil),
        expectedOwnerID: "owner-a",
        backendAPIClient: client)
    }

    _ = await AuthorizedToolOwnerURLProtocol.gate.waitForRequest()
    await AuthorizedToolOwnerURLProtocol.gate.succeed(
      with:
        #"{"tool_name":"get_memories","result_text":"owner-a-memory","is_error":false}"#)

    let result = await operation.value
    XCTAssertEqual(result, "owner-a-memory")
  }

  func testActionItemWriteKeepsOriginalCredentialAndRejectsResultAfterMidFlightAccountSwitch() async {
    let client = await makeClient()
    let operation = Task { @MainActor in
      await ChatToolExecutor.execute(
        ToolCall(
          name: "create_action_item",
          arguments: ["description": "owner-a-private-task"],
          thoughtSignature: nil),
        expectedOwnerID: "owner-a",
        backendAPIClient: client)
    }

    let request = await AuthorizedToolOwnerURLProtocol.gate.waitForRequest()
    XCTAssertEqual(request.httpMethod, "POST")
    XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer owner-a-token")
    let body = AuthorizedToolOwnerURLProtocol.bodyData(from: request).flatMap {
      try? JSONSerialization.jsonObject(with: $0) as? [String: Any]
    }
    XCTAssertEqual(body?["description"] as? String, "owner-a-private-task")

    UserDefaults.standard.set("owner-b", forKey: .authUserId)
    await AuthorizedToolOwnerURLProtocol.gate.succeed(
      with:
        #"{"tool_name":"create_action_item","result_text":"created-owner-a-task","is_error":false}"#)

    let result = await operation.value
    XCTAssertEqual(result, ChatToolExecutor.authorizedOwnerChangedResult())
    XCTAssertFalse(result.contains("created-owner-a-task"))
  }

  func testRealtimeHigherModelNeverReleasesOwnerAContextAfterMidFlightAccountSwitch() async {
    let client = await makeClient()
    let privateBody: [String: Any] = [
      "messages": [[
        "role": "user",
        "content": "owner-a-private-query\nowner-a-private-about-user",
      ]]
    ]
    let operation = Task { @MainActor in
      do {
        _ = try await client.askHigherModel(
          body: privateBody,
          expectedOwnerID: "owner-a",
          customBaseURL: "https://owner-bound.invalid/")
        return false
      } catch AuthError.userChangedDuringRequest {
        return true
      } catch {
        return false
      }
    }

    let request = await AuthorizedToolOwnerURLProtocol.gate.waitForRequest()
    XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer owner-a-token")
    let body = AuthorizedToolOwnerURLProtocol.bodyData(from: request).flatMap {
      try? JSONSerialization.jsonObject(with: $0) as? [String: Any]
    }
    XCTAssertNotNil(body)

    UserDefaults.standard.set("owner-b", forKey: .authUserId)
    await AuthorizedToolOwnerURLProtocol.gate.succeed(
      with: #"{"choices":[{"message":{"content":"owner-a-private-answer"}}]}"#)

    let rejectedLateResponse = await operation.value
    XCTAssertTrue(rejectedLateResponse)
  }

  func testRealtimePointClickDoesNotPostEventsForStaleOwner() {
    var posted = false
    let clicked = RealtimeHubController.click(
      at: CGPoint(x: 10, y: 20),
      expectedOwnerID: "owner-a",
      ownerIsCurrent: { _ in false },
      postEvents: { _ in
        posted = true
        return true
      })

    XCTAssertFalse(clicked)
    XCTAssertFalse(posted)
  }

  func testPermissionAndConnectorEffectsAreNotInvokedAfterOwnerSwap() async {
    for effectName in ["permission", "connector_form"] {
      var currentOwner = "owner-a"
      var invoked = false
      let result = await ChatToolExecutor.performOwnerBoundAsyncPhysicalEffect(
        expectedOwnerID: "owner-a",
        ownerIsCurrent: { $0 == currentOwner },
        prepare: {
          currentOwner = "owner-b"
        },
        effect: {
          invoked = true
          return effectName
        })

      XCTAssertNil(result)
      XCTAssertFalse(invoked, "\(effectName) physical effect must fail closed")
    }
  }

  func testSQLPostCommitDoesNotRetryUnderReplacementOwner() async {
    var currentOwner = "owner-a"
    var reloadCount = 0
    var retryCount = 0

    let completed = await ChatToolExecutor.executeOwnerBoundSQLPostCommitEffects(
      changes: 1,
      query: "INSERT INTO action_items (description) VALUES ('owner-a-private-task')",
      expectedOwnerID: "owner-a",
      ownerIsCurrent: { $0 == currentOwner },
      reloadTasks: {
        reloadCount += 1
        currentOwner = "owner-b"
      },
      retryUnsyncedTasks: {
        retryCount += 1
      })

    XCTAssertFalse(completed)
    XCTAssertEqual(reloadCount, 1)
    XCTAssertEqual(retryCount, 0)
  }

  func testNonHubProviderDispatchIsNotCalledAfterOwnerChangesDuringPreparation() async {
    var currentOwner = "owner-a"
    let coordinator = VoiceTurnCoordinator(
      ownerIDProvider: { "owner-a" },
      ownerIsCurrent: { $0 == currentOwner })
    let turnID = coordinator.begin(intent: .hold)
    var providerDispatchCount = 0

    let outcome = await FloatingControlBarManager.performOwnerBoundVoiceDispatch(
      turnID: turnID,
      coordinator: coordinator,
      prepare: {
        currentOwner = "owner-b"
      },
      dispatch: {
        providerDispatchCount += 1
        return "sent"
      })

    if case .rejectedOwnerChange = outcome {
      // Expected.
    } else {
      XCTFail("stale non-hub voice owner must reject provider dispatch")
    }
    XCTAssertEqual(providerDispatchCount, 0)
    XCTAssertEqual(coordinator.model.lastTerminal?.turnID, turnID)
    XCTAssertEqual(coordinator.model.lastTerminal?.reason, .cancelled)
  }

  func testSignedOutOnboardingPermissionStatusIsTheOnlyNarrowNilOwnerPath() async {
    UserDefaults.standard.removeObject(forKey: .authUserId)
    UserDefaults.standard.removeObject(forKey: .automationOwnerOverride)
    UserDefaults.standard.removeObject(forKey: .automationOwnerABackup)

    let permissionResult = await ChatToolExecutor.execute(
      ToolCall(
        name: "request_permission",
        arguments: [:],
        thoughtSignature: nil),
      isOnboardingSurface: true)
    XCTAssertFalse(permissionResult.contains("authorized_execution_owner_changed"))

    let authenticatedDataResult = await ChatToolExecutor.execute(
      ToolCall(
        name: "execute_sql",
        arguments: ["query": "SELECT 1", "read_only": true],
        thoughtSignature: nil))
    XCTAssertEqual(authenticatedDataResult, ChatToolExecutor.authorizedOwnerChangedResult())
  }

  private func makeClient() async -> APIClient {
    await AuthorizedToolOwnerURLProtocol.gate.reset()
    UserDefaults.standard.removeObject(forKey: .automationOwnerOverride)
    UserDefaults.standard.removeObject(forKey: .automationOwnerABackup)
    UserDefaults.standard.set("owner-a", forKey: .authUserId)
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [AuthorizedToolOwnerURLProtocol.self]
    let client = APIClient(session: URLSession(configuration: configuration))
    await client.setOwnerBoundTestAuthHeader("Bearer owner-a-token")
    return client
  }

  private func restoreDefault(_ value: Any?, forKey key: DefaultsKey) {
    if let value {
      UserDefaults.standard.set(value, forKey: key.rawValue)
    } else {
      UserDefaults.standard.removeObject(forKey: key.rawValue)
    }
  }
}
