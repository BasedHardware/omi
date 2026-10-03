@preconcurrency import GRDB
import XCTest

@testable import Omi_Computer

final class JITRolloutClientTests: XCTestCase {
  private var priorAuthUserID: String?

  override func setUp() {
    super.setUp()
    priorAuthUserID = UserDefaults.standard.string(forKey: .authUserId)
  }

  override func tearDown() {
    // The JIT authority routes re-validate the runtime owner against the
    // shared authorization authority; restore the durable auth user and the
    // authority owner the rest of the suite expects.
    let authority = RuntimeOwnerAuthorizationAuthority.shared
    authority.beginTransition()
    if let priorAuthUserID {
      UserDefaults.standard.set(priorAuthUserID, forKey: .authUserId)
      authority.endTransition(ownerID: priorAuthUserID)
    } else {
      UserDefaults.standard.removeObject(forKey: .authUserId)
      authority.endTransition(ownerID: nil)
    }
    super.tearDown()
  }

  func testRolloutDecisionEffectiveEnabledAdmitsEvenWhenRawFlagsAreNotAKnownGoodPair() async throws {
    JITRolloutURLStub.reset()
    JITRolloutURLStub.enqueue(
      statusCode: 200,
      body: try rolloutDecisionBody(rollout: "unknown", killSwitch: "disabled", effective: "enabled"))
    let client = makeJITAuthorityClient()

    let flags = await client.jitProactivityFlags(
      authorizationSnapshot: try jitAuthorizationSnapshot())

    XCTAssertEqual(flags.effective, .enabled)
    XCTAssertTrue(flags.permitsNewLane)
  }

  func testRolloutDecisionToleratesMissingKillSwitchWhenEffectiveEnabled() async throws {
    JITRolloutURLStub.reset()
    JITRolloutURLStub.enqueue(
      statusCode: 200,
      body: try rolloutDecisionBody(rollout: "enabled", killSwitch: nil, effective: "enabled"))
    let client = makeJITAuthorityClient()

    let flags = await client.jitProactivityFlags(
      authorizationSnapshot: try jitAuthorizationSnapshot())

    XCTAssertFalse(flags.killSwitchPresent)
    XCTAssertEqual(flags.killSwitch, .unknown)
    XCTAssertTrue(flags.permitsNewLane)
  }

  func testRolloutDecisionUnknownStatesStillFailClosed() async throws {
    JITRolloutURLStub.reset()
    JITRolloutURLStub.enqueue(
      statusCode: 200,
      body: try rolloutDecisionBody(rollout: "unknown", killSwitch: "unknown", effective: "unknown"))
    let client = makeJITAuthorityClient()

    let flags = await client.jitProactivityFlags(
      authorizationSnapshot: try jitAuthorizationSnapshot())

    XCTAssertFalse(flags.permitsNewLane)
  }

  func testRolloutDecisionPresentUnknownKillSwitchWithoutEffectiveFailsClosed() async throws {
    JITRolloutURLStub.reset()
    JITRolloutURLStub.enqueue(
      statusCode: 200,
      body: try rolloutDecisionBody(rollout: "enabled", killSwitch: "unknown", effective: nil))
    let client = makeJITAuthorityClient()

    let flags = await client.jitProactivityFlags(
      authorizationSnapshot: try jitAuthorizationSnapshot())

    XCTAssertTrue(flags.killSwitchPresent)
    XCTAssertFalse(flags.permitsNewLane)
  }

  private func jitAuthorizationSnapshot(ownerID: String = "owner") throws
    -> RuntimeOwnerAuthorizationSnapshot
  {
    UserDefaults.standard.set(ownerID, forKey: .authUserId)
    let authority = RuntimeOwnerAuthorizationAuthority.shared
    authority.beginTransition()
    authority.endTransition(ownerID: ownerID)
    return try XCTUnwrap(authority.capture(ownerID: ownerID, expectedOwnerID: ownerID))
  }

  private func rolloutDecisionBody(
    rollout: String?, killSwitch: String?, effective: String?
  ) throws -> Data {
    var object: [String: Any] = [
      "reason": "rollout_enabled",
      "error_class": "none",
      "cache_hit": false,
      "cache_ttl_seconds": 30,
    ]
    object["rollout"] = rollout
    object["kill_switch"] = killSwitch
    object["effective"] = effective
    return try JSONSerialization.data(withJSONObject: object)
  }

  private func makeStubSession() -> URLSession {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [JITRolloutURLStub.self]
    configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
    return URLSession(configuration: configuration)
  }

  private func makeJITAuthorityClient() -> JITRolloutClient {
    JITRolloutClient(
      session: makeStubSession(), baseURL: { "https://jit-authority.test" },
      jitAuthorization: { ownerID in "Bearer test-\(ownerID)" })
  }
}

private final class JITRolloutURLStub: URLProtocol, @unchecked Sendable {
  struct StubResponse {
    let statusCode: Int
    let body: Data
    let headers: [String: String]
  }

  private static let lock = NSLock()
  private nonisolated(unsafe) static var responses: [StubResponse] = []
  private nonisolated(unsafe) static var served = 0
  private nonisolated(unsafe) static var operations: [String] = []
  private nonisolated(unsafe) static var maxCompletionTokenBudgets: [Int] = []
  private nonisolated(unsafe) static var paths: [String] = []
  /// How many requests must be in flight before any of them is answered, if the caller asked for
  /// that. Nil is the ordinary case: answer each request as it arrives.
  private nonisolated(unsafe) static var holdThreshold: Int?
  private nonisolated(unsafe) static var holdReached: XCTestExpectation?
  private nonisolated(unsafe) static var held: [() -> Void] = []

  static var requestCount: Int {
    lock.lock()
    defer { lock.unlock() }
    return served
  }

  static var requestedOperations: [String] {
    lock.lock()
    defer { lock.unlock() }
    return operations
  }

  static var requestedMaxCompletionTokens: [Int] {
    lock.lock()
    defer { lock.unlock() }
    return maxCompletionTokenBudgets
  }

  /// Request URL paths in issue order, for asserting which authority routes a
  /// caller actually reached.
  static var requestedPaths: [String] {
    lock.lock()
    defer { lock.unlock() }
    return paths
  }

  static func reset() {
    lock.lock()
    responses = []
    served = 0
    operations = []
    maxCompletionTokenBudgets = []
    paths = []
    holdThreshold = nil
    holdReached = nil
    held = []
    lock.unlock()
  }

  /// Park every request instead of answering it until `count` of them have been issued, then
  /// fulfill `expectation`. This is a synchronisation point, not a wait: it makes "these calls
  /// overlapped" a fact the test establishes rather than one it hopes for.
  static func holdRequests(until count: Int, reaching expectation: XCTestExpectation) {
    lock.lock()
    holdThreshold = count
    holdReached = expectation
    held = []
    lock.unlock()
  }

  /// Answer everything parked by `holdRequests`, and stop parking.
  static func releaseHeldRequests() {
    lock.lock()
    let pending = held
    held = []
    holdThreshold = nil
    holdReached = nil
    lock.unlock()
    for deliver in pending { deliver() }
  }

  static func enqueue(statusCode: Int, body: Data, headers: [String: String] = [:]) {
    lock.lock()
    responses.append(StubResponse(statusCode: statusCode, body: body, headers: headers))
    lock.unlock()
  }

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    guard let url = request.url else {
      client?.urlProtocol(self, didFailWithError: URLError(.badURL))
      return
    }
    let operation = Self.operation(from: request)
    let maxCompletionTokens = Self.maxCompletionTokens(from: request)
    Self.lock.lock()
    Self.operations.append(operation)
    if let maxCompletionTokens { Self.maxCompletionTokenBudgets.append(maxCompletionTokens) }
    Self.paths.append(url.path)
    let stub = Self.responses.isEmpty ? nil : Self.responses.removeFirst()
    Self.served += 1
    let deliver = { self.deliver(stub, for: url) }
    let isHeld = Self.holdThreshold != nil
    if isHeld { Self.held.append(deliver) }
    let reached = Self.holdThreshold.map { Self.served >= $0 } ?? false
    let holdReached = reached ? Self.holdReached : nil
    if reached { Self.holdReached = nil }
    Self.lock.unlock()

    holdReached?.fulfill()
    if !isHeld { deliver() }
  }

  private func deliver(_ stub: StubResponse?, for url: URL) {
    guard let stub else {
      client?.urlProtocol(self, didFailWithError: URLError(.cannotConnectToHost))
      return
    }
    guard
      let response = HTTPURLResponse(
        url: url, statusCode: stub.statusCode, httpVersion: nil, headerFields: stub.headers)
    else {
      client?.urlProtocol(self, didFailWithError: URLError(.badServerResponse))
      return
    }
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: stub.body)
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}

  private static func operation(from request: URLRequest) -> String {
    guard let data = bodyData(from: request),
      let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
      let operation = object["operation"] as? String
    else { return "" }
    return operation
  }

  private static func maxCompletionTokens(from request: URLRequest) -> Int? {
    guard let data = bodyData(from: request),
      let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    else { return nil }
    return object["max_completion_tokens"] as? Int
  }

  private static func bodyData(from request: URLRequest) -> Data? {
    if let body = request.httpBody { return body }
    guard let stream = request.httpBodyStream else { return nil }
    stream.open()
    defer { stream.close() }
    var data = Data()
    let buffer = UnsafeMutablePointer<UInt8>.allocate(capacity: 4_096)
    defer { buffer.deallocate() }
    while stream.hasBytesAvailable {
      let count = stream.read(buffer, maxLength: 4_096)
      guard count > 0 else { break }
      data.append(buffer, count: count)
    }
    return data.isEmpty ? nil : data
  }
}
