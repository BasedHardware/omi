import Foundation
import VoiceTurnDomain
import XCTest

@testable import Omi_Computer

extension APIClient {
  fileprivate func setOwnerBoundTestAuthHeader(_ header: String) {
    testAuthHeader = header
  }
}

private actor AuthorizedToolRequestGate {
  private struct RequestWaiter {
    let path: String
    let continuation: CheckedContinuation<URLRequest, Never>
  }

  private var pendingProtocols: [AuthorizedToolOwnerURLProtocol] = []
  private var selectedProtocols: [String: AuthorizedToolOwnerURLProtocol] = [:]
  private var requestWaiters: [RequestWaiter] = []

  func reset() {
    pendingProtocols.removeAll()
    selectedProtocols.removeAll()
    requestWaiters.removeAll()
  }

  func receive(_ urlProtocol: AuthorizedToolOwnerURLProtocol) {
    pendingProtocols.append(urlProtocol)
    let path = urlProtocol.request.url?.path ?? ""
    if let index = requestWaiters.firstIndex(where: { $0.path == path }) {
      let waiter = requestWaiters.remove(at: index)
      selectedProtocols[path] = urlProtocol
      waiter.continuation.resume(returning: urlProtocol.request)
    }
  }

  func waitForRequest(path: String) async -> URLRequest {
    if let pendingProtocol = pendingProtocols.last(where: { $0.request.url?.path == path }) {
      selectedProtocols[path] = pendingProtocol
      return pendingProtocol.request
    }
    return await withCheckedContinuation { continuation in
      requestWaiters.append(RequestWaiter(path: path, continuation: continuation))
    }
  }

  func succeed(path: String, with body: String) {
    guard let pendingProtocol = selectedProtocols.removeValue(forKey: path) else { return }
    pendingProtocols.removeAll { $0 === pendingProtocol }
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

private actor AuthorizedToolPhysicalEffectGate {
  private var entered = false
  private var enteredWaiters: [CheckedContinuation<Void, Never>] = []
  private var releaseContinuation: CheckedContinuation<Void, Never>?

  func suspendEffectPreparation() async {
    entered = true
    enteredWaiters.forEach { $0.resume() }
    enteredWaiters.removeAll()
    await withCheckedContinuation { releaseContinuation = $0 }
  }

  func waitUntilEntered() async {
    if entered { return }
    await withCheckedContinuation { enteredWaiters.append($0) }
  }

  func release() {
    releaseContinuation?.resume()
    releaseContinuation = nil
  }
}

private actor PermissionCallbackBox<Value: Sendable> {
  private var callback: (@Sendable (Value) -> Void)?
  private var installWaiters: [CheckedContinuation<Void, Never>] = []

  func install(_ callback: @escaping @Sendable (Value) -> Void) {
    self.callback = callback
    installWaiters.forEach { $0.resume() }
    installWaiters.removeAll()
  }

  func waitUntilInstalled() async {
    if callback != nil { return }
    await withCheckedContinuation { installWaiters.append($0) }
  }

  func resolve(_ value: Value) {
    callback?(value)
  }
}

@MainActor
final class AuthorizedToolOwnerBoundAuthTests: XCTestCase {
  private var originalAuthOwner: String?
  private var originalOwnerOverride: String?
  private var originalOwnerBackup: String?

  override func setUp() {
    super.setUp()
    originalAuthOwner = UserDefaults.standard.string(forKey: .authUserId)
    originalOwnerOverride = UserDefaults.standard.string(forKey: .automationOwnerOverride)
    originalOwnerBackup = UserDefaults.standard.string(forKey: .automationOwnerABackup)
  }

  override func tearDown() async throws {
    await restoreOriginalOwnerDefaults()
    await AuthorizedToolOwnerURLProtocol.gate.reset()
    try await super.tearDown()
  }

  func testMemoryReadRejectsPrivateResponseAfterMidFlightAccountSwitch() async {
    let client = await makeClient()
    let operation = Task { @MainActor in
      await ChatToolExecutor.execute(
        ToolCall(name: "get_memories", arguments: [:], thoughtSignature: nil),
        expectedOwnerID: "owner-a",
        backendAPIClient: client)
    }

    let request = await AuthorizedToolOwnerURLProtocol.gate.waitForRequest(path: "/v1/tools/memories")
    XCTAssertEqual(request.httpMethod, "GET")
    XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer owner-a-token")

    UserDefaults.standard.set("owner-b", forKey: .authUserId)
    await AuthorizedToolOwnerURLProtocol.gate.succeed(
      path: "/v1/tools/memories",
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

    _ = await AuthorizedToolOwnerURLProtocol.gate.waitForRequest(path: "/v1/tools/memories")
    await AuthorizedToolOwnerURLProtocol.gate.succeed(
      path: "/v1/tools/memories",
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

    let request = await AuthorizedToolOwnerURLProtocol.gate.waitForRequest(path: "/v1/tools/action-items")
    XCTAssertEqual(request.httpMethod, "POST")
    XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer owner-a-token")
    let body = AuthorizedToolOwnerURLProtocol.bodyData(from: request).flatMap {
      try? JSONSerialization.jsonObject(with: $0) as? [String: Any]
    }
    XCTAssertEqual(body?["description"] as? String, "owner-a-private-task")

    UserDefaults.standard.set("owner-b", forKey: .authUserId)
    await AuthorizedToolOwnerURLProtocol.gate.succeed(
      path: "/v1/tools/action-items",
      with:
        #"{"tool_name":"create_action_item","result_text":"created-owner-a-task","is_error":false}"#)

    let result = await operation.value
    XCTAssertEqual(result, ChatToolExecutor.authorizedOwnerChangedResult())
    XCTAssertFalse(result.contains("created-owner-a-task"))
  }

  func testRealtimeHigherModelNeverReleasesOwnerAContextAfterMidFlightAccountSwitch() async {
    let client = await makeClient()
    let privateBody: [String: Any] = [
      "messages": [
        [
          "role": "user",
          "content": "owner-a-private-query\nowner-a-private-about-user",
        ]
      ]
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

    let request = await AuthorizedToolOwnerURLProtocol.gate.waitForRequest(path: "/v2/chat/completions")
    XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer owner-a-token")
    let body = AuthorizedToolOwnerURLProtocol.bodyData(from: request).flatMap {
      try? JSONSerialization.jsonObject(with: $0) as? [String: Any]
    }
    XCTAssertNotNil(body)

    UserDefaults.standard.set("owner-b", forKey: .authUserId)
    await AuthorizedToolOwnerURLProtocol.gate.succeed(
      path: "/v2/chat/completions",
      with: #"{"choices":[{"message":{"content":"owner-a-private-answer"}}]}"#)

    let rejectedLateResponse = await operation.value
    XCTAssertTrue(rejectedLateResponse)
  }

  func testRealtimeMintNeverReleasesOwnerATokenAfterMidFlightAccountSwitch() async {
    let client = await makeClient()
    let operation = Task { @MainActor in
      do {
        _ = try await client.mintRealtimeToken(
          provider: "openai",
          expectedOwnerID: "owner-a",
          customBaseURL: "https://owner-bound.invalid/")
        return false
      } catch AuthError.userChangedDuringRequest {
        return true
      } catch {
        return false
      }
    }

    let request = await AuthorizedToolOwnerURLProtocol.gate.waitForRequest(path: "/v2/realtime/session")
    XCTAssertEqual(request.url?.path, "/v2/realtime/session")
    XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer owner-a-token")

    UserDefaults.standard.set("owner-b", forKey: .authUserId)
    await AuthorizedToolOwnerURLProtocol.gate.succeed(
      path: "/v2/realtime/session",
      with: #"{"token":"owner-a-private-ephemeral-token"}"#)

    let rejectedLateToken = await operation.value
    XCTAssertTrue(rejectedLateToken)
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

  func testAutomationSettingsDoesNotOpenAfterOwnerChangesAtFinalEffectBoundary() {
    var opened = false

    let didOpen = ChatToolExecutor.openAutomationPrivacySettings(
      expectedOwnerID: "owner-a",
      ownerIsCurrent: { _ in false },
      open: { _ in
        opened = true
        return true
      })

    XCTAssertFalse(didOpen)
    XCTAssertFalse(opened)
  }

  func testDetachedPermissionEffectsStayRevokedAcrossSameOwnerSessionReplacement() async {
    await establishStandardOwner("owner-a")
    guard
      let authorization = RuntimeOwnerIdentity.captureAuthorizationSnapshot(
        expectedOwnerID: "owner-a")
    else {
      XCTFail("owner-a authorization snapshot was not available")
      return
    }
    await replaceStandardOwner(with: nil)
    await replaceStandardOwner(with: "owner-a")

    var opened = false
    let didOpen = ChatToolExecutor.openAutomationPrivacySettings(
      expectedOwnerID: "owner-a",
      authorizationSnapshot: authorization,
      open: { _ in
        opened = true
        return true
      })
    var pendingCallbacks: [String] = []
    ChatToolExecutor.publishPermissionPendingIfCurrent(
      "automation",
      expectedOwnerID: "owner-a",
      authorizationSnapshot: authorization,
      callback: { pendingCallbacks.append($0) })

    XCTAssertFalse(didOpen)
    XCTAssertFalse(opened)
    XCTAssertTrue(pendingCallbacks.isEmpty)
    XCTAssertFalse(RuntimeOwnerIdentity.isAuthorizationCurrent(authorization))
  }

  func testPermissionCallbackCancellationReturnsWithoutWaitingAndIgnoresLateCompletion() async {
    let callbackBox = PermissionCallbackBox<Bool>()
    let operation = Task {
      await ChatToolExecutor.awaitCancellablePermissionRequest { completion in
        Task { await callbackBox.install(completion) }
      }
    }

    await callbackBox.waitUntilInstalled()
    operation.cancel()
    let result = await operation.value

    XCTAssertNil(result, "cancellation must release the tracked owner-bound permission task")
    await callbackBox.resolve(true)
    await callbackBox.resolve(false)
    XCTAssertNil(
      result,
      "late or duplicate OS callbacks must not resume the revoked continuation again")
  }

  func testSignedOutPermissionPublicationIsRevokedWhenAnOwnerSignsIn() async {
    await replaceStandardOwner(with: nil)
    var pendingCallbacks: [String] = []
    await replaceStandardOwner(with: "owner-b")

    ChatToolExecutor.publishPermissionPendingIfCurrent(
      "microphone",
      expectedOwnerID: nil,
      authorizationSnapshot: nil,
      callback: { pendingCallbacks.append($0) })

    XCTAssertTrue(
      pendingCallbacks.isEmpty,
      "the narrow signed-out permission path must close as soon as an owner signs in")
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

  func testSuspendedPhysicalEffectStaysRevokedAcrossSameOwnerSessionReplacement() async {
    await establishStandardOwner("owner-a")
    guard
      let authorization = RuntimeOwnerIdentity.captureAuthorizationSnapshot(
        expectedOwnerID: "owner-a")
    else {
      XCTFail("owner-a authorization snapshot was not available")
      return
    }
    let gate = AuthorizedToolPhysicalEffectGate()
    var effectCount = 0
    let operation = Task { @MainActor in
      await ChatToolExecutor.performOwnerBoundAsyncPhysicalEffect(
        expectedOwnerID: "owner-a",
        authorizationSnapshot: authorization,
        prepare: { await gate.suspendEffectPreparation() },
        effect: {
          effectCount += 1
          return "owner-a-private-result"
        })
    }

    await gate.waitUntilEntered()
    await replaceStandardOwner(with: nil)
    await replaceStandardOwner(with: "owner-a")
    await gate.release()

    let result = await operation.value
    XCTAssertNil(result)
    XCTAssertEqual(effectCount, 0)
    XCTAssertFalse(RuntimeOwnerIdentity.isAuthorizationCurrent(authorization))
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
    await establishStandardOwner(nil)

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
    await establishStandardOwner("owner-a")
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [AuthorizedToolOwnerURLProtocol.self]
    let client = APIClient(session: URLSession(configuration: configuration))
    await client.setOwnerBoundTestAuthHeader("Bearer owner-a-token")
    return client
  }

  private func replaceStandardOwner(with ownerID: String?) async {
    await RuntimeOwnerIdentity.performEffectiveOwnerTransition(
      defaults: .standard,
      allowAutomationOverride: false,
      plannedNextOwner: { _, _ in ownerID },
      quiesceVoice: { _, _ in },
      revokeKernelOwner: { _, _ in },
      retargetLocalStorage: { _, _ in },
      ownerDidChange: {}
    ) { defaults in
      defaults.removeObject(forKey: .automationOwnerOverride)
      defaults.removeObject(forKey: .automationOwnerABackup)
      if let ownerID {
        defaults.set(ownerID, forKey: .authUserId)
      } else {
        defaults.removeObject(forKey: .authUserId)
      }
    }
  }

  private func establishStandardOwner(_ ownerID: String?) async {
    let bootstrapOwner = "authorized-tool-owner-bootstrap"
    if ownerID == bootstrapOwner {
      await replaceStandardOwner(with: nil)
    } else {
      await replaceStandardOwner(with: bootstrapOwner)
    }
    await replaceStandardOwner(with: ownerID)
  }

  private func restoreOriginalOwnerDefaults() async {
    let authOwner = originalAuthOwner
    let ownerOverride = originalOwnerOverride
    let ownerBackup = originalOwnerBackup
    let effectiveOwner =
      ownerOverride?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
      ? ownerOverride
      : authOwner
    // Force one distinct completed generation first so even an authority that
    // a mismatch test deliberately left revoked is quiescent before restore.
    await replaceStandardOwner(with: "authorized-tool-owner-restore")
    await RuntimeOwnerIdentity.performEffectiveOwnerTransition(
      defaults: .standard,
      allowAutomationOverride: true,
      plannedNextOwner: { _, _ in effectiveOwner },
      quiesceVoice: { _, _ in },
      revokeKernelOwner: { _, _ in },
      retargetLocalStorage: { _, _ in },
      ownerDidChange: {}
    ) { defaults in
      for (key, value) in [
        (DefaultsKey.authUserId, authOwner),
        (DefaultsKey.automationOwnerOverride, ownerOverride),
        (DefaultsKey.automationOwnerABackup, ownerBackup),
      ] {
        if let value {
          defaults.set(value, forKey: key.rawValue)
        } else {
          defaults.removeObject(forKey: key.rawValue)
        }
      }
    }
  }
}
