import AppKit
import XCTest

@testable import Omi_Computer

private final class ProjectionClientFake: ProjectionClient, @unchecked Sendable {
  private let lock = NSLock()
  private var listContinuation: CheckedContinuation<[Projection], Error>?
  private var listStarted = false

  var projections: [Projection] = []
  var generatedProjection: Projection?
  var imageData: Data = Data()
  var listError: Error?
  var imageError: Error?
  var suspendList = false
  var invalidateAuthorizationOnFeedback = false

  var listCallCount: Int {
    lock.withLock { requestedOwnerIDs.count }
  }

  private(set) var requestedOwnerIDs: [String] = []
  private(set) var imageOwnerIDs: [String] = []
  private(set) var imageProjectionIDs: [String] = []
  private(set) var feedbackOwnerIDs: [String] = []
  private var authorizationInvalidated = false

  var authorizationIsCurrent: Bool {
    lock.withLock { !authorizationInvalidated }
  }

  func getProjections(
    limit: Int,
    expectedOwnerId: String?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?
  ) async throws -> [Projection] {
    lock.withLock {
      if let expectedOwnerId { requestedOwnerIDs.append(expectedOwnerId) }
      listStarted = true
    }
    if suspendList {
      return try await withCheckedThrowingContinuation { continuation in
        lock.withLock { listContinuation = continuation }
      }
    }
    if let listError { throw listError }
    return Array(projections.prefix(limit))
  }

  func generateProjection(
    expectedOwnerId: String?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?
  ) async throws -> Projection? {
    if let expectedOwnerId {
      lock.withLock { requestedOwnerIDs.append(expectedOwnerId) }
    }
    return generatedProjection
  }

  func getProjectionImage(
    projectionID: String,
    expectedOwnerId: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> Data {
    lock.withLock {
      imageOwnerIDs.append(expectedOwnerId)
      imageProjectionIDs.append(projectionID)
    }
    if let imageError { throw imageError }
    return imageData
  }

  func recordProjectionFeedback(
    projectionID: String,
    rating: ProjectionFeedbackRating,
    expectedOwnerId: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> ProjectionFeedbackRating {
    lock.withLock {
      feedbackOwnerIDs.append(expectedOwnerId)
      if invalidateAuthorizationOnFeedback {
        authorizationInvalidated = true
      }
    }
    return rating
  }

  func waitUntilListStarted() async {
    while !lock.withLock({ listStarted }) { await Task.yield() }
  }

  func releaseList(with projections: [Projection]) {
    let continuation = lock.withLock { () -> CheckedContinuation<[Projection], Error>? in
      defer { listContinuation = nil }
      return listContinuation
    }
    continuation?.resume(returning: projections)
  }
}

private final class ProjectionImageURLProtocol: URLProtocol, @unchecked Sendable {
  private static let lock = NSLock()
  private nonisolated(unsafe) static var capturedAuthorization: String?
  private nonisolated(unsafe) static var capturedURL: URL?
  private nonisolated(unsafe) static var capturedTimeoutInterval: TimeInterval?
  private nonisolated(unsafe) static var responseData = Data()

  static func reset(data: Data = Data()) {
    lock.withLock {
      capturedAuthorization = nil
      capturedURL = nil
      capturedTimeoutInterval = nil
      responseData = data
    }
  }

  static var authorization: String? {
    lock.withLock { capturedAuthorization }
  }

  static var url: URL? {
    lock.withLock { capturedURL }
  }

  static var timeoutInterval: TimeInterval? {
    lock.withLock { capturedTimeoutInterval }
  }

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    let data = Self.lock.withLock { () -> Data in
      Self.capturedAuthorization = request.value(forHTTPHeaderField: "Authorization")
      Self.capturedURL = request.url
      Self.capturedTimeoutInterval = request.timeoutInterval
      return Self.responseData
    }
    guard let url = request.url,
      let response = HTTPURLResponse(
        url: url,
        statusCode: 200,
        httpVersion: nil,
        headerFields: ["Content-Type": "image/png"])
    else { return }
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: data)
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}
}

@MainActor
final class ProjectionPageTests: XCTestCase {
  override func setUp() async throws {
    await establishOwner("projection-owner-a")
    ProjectionImageURLProtocol.reset()
  }

  override func tearDown() async throws {
    await establishOwner(nil)
    ProjectionImageURLProtocol.reset()
  }

  func testValidOwnerLoadsDocumentAndAuthenticatedImage() async throws {
    let fake = ProjectionClientFake()
    fake.projections = [projection(id: "projection-a")]
    fake.imageData = imageData()
    let viewModel = ProjectionViewModel(client: fake)

    await viewModel.load()

    XCTAssertEqual(viewModel.projection?.id, "projection-a")
    XCTAssertNotNil(viewModel.image)
    XCTAssertFalse(viewModel.imageLoadFailed)
    XCTAssertEqual(fake.requestedOwnerIDs, ["projection-owner-a"])
    XCTAssertEqual(fake.imageOwnerIDs, ["projection-owner-a"])
    XCTAssertEqual(fake.imageProjectionIDs, ["projection-a"])
  }

  func testPersistedImageHostIsNotPassedToTheAuthenticatedImageClient() async throws {
    let fake = ProjectionClientFake()
    fake.projections = [
      Projection(
        id: "projection-a",
        imperative: "Cross the threshold.",
        imageURL: URL(string: "https://attacker.invalid/token-collector"))
    ]
    fake.imageData = imageData()
    let viewModel = ProjectionViewModel(client: fake)

    await viewModel.load()

    XCTAssertEqual(fake.imageProjectionIDs, ["projection-a"])
    XCTAssertNotNil(viewModel.image)
  }

  func testLateOwnerAResponseCannotPopulateOwnerBPage() async throws {
    let fake = ProjectionClientFake()
    fake.suspendList = true
    fake.imageData = imageData()
    let viewModel = ProjectionViewModel(client: fake)

    let load = Task { await viewModel.load() }
    await fake.waitUntilListStarted()
    await transitionOwner(to: "projection-owner-b")
    fake.releaseList(with: [projection(id: "projection-a")])
    await load.value

    XCTAssertNil(viewModel.projection)
    XCTAssertNil(viewModel.image)
    XCTAssertNil(viewModel.errorMessage)
    XCTAssertTrue(fake.imageOwnerIDs.isEmpty)
  }

  func testOwnerChangeImmediatelyClearsRenderedArtifact() async throws {
    let fake = ProjectionClientFake()
    fake.projections = [projection(id: "projection-a")]
    fake.imageData = imageData()
    let viewModel = ProjectionViewModel(client: fake)
    await viewModel.load()
    XCTAssertNotNil(viewModel.projection)

    viewModel.ownerDidChange()

    XCTAssertNil(viewModel.projection)
    XCTAssertNil(viewModel.image)
    XCTAssertNil(viewModel.errorMessage)
  }

  func testActivationRefreshUsesSharedCooldown() async throws {
    let fake = ProjectionClientFake()
    let viewModel = ProjectionViewModel(client: fake)
    let start = Date(timeIntervalSince1970: 1_000)

    await viewModel.load(now: start)
    await viewModel.refreshOnActivation(
      now: start.addingTimeInterval(PollingConfig.activationCooldown - 1))
    XCTAssertEqual(fake.listCallCount, 1)

    await viewModel.refreshOnActivation(
      now: start.addingTimeInterval(PollingConfig.activationCooldown))
    XCTAssertEqual(fake.listCallCount, 2)
  }

  func testHarnessActivationPolicyRetainsThePresentedProjection() async throws {
    let fake = ProjectionClientFake()
    fake.projections = [projection(id: "projection-a")]
    fake.imageData = imageData()
    let viewModel = ProjectionViewModel(
      client: fake,
      refreshesOnActivation: false)
    let start = Date(timeIntervalSince1970: 1_000)

    await viewModel.load(now: start)
    fake.projections = []
    await viewModel.refreshOnActivation(
      now: start.addingTimeInterval(PollingConfig.activationCooldown))

    XCTAssertEqual(viewModel.projection?.id, "projection-a")
    XCTAssertNotNil(viewModel.image)
    XCTAssertEqual(fake.listCallCount, 1)
  }

  func testFeedbackCarriesOwnerAndUpdatesTheRenderedSignal() async throws {
    let fake = ProjectionClientFake()
    fake.projections = [projection(id: "projection-a")]
    fake.imageData = imageData()
    let viewModel = ProjectionViewModel(client: fake)
    await viewModel.load()

    await viewModel.submitFeedback(.up)

    XCTAssertEqual(viewModel.feedbackRating, .up)
    XCTAssertEqual(fake.feedbackOwnerIDs, ["projection-owner-a"])
  }

  func testFeedbackResultIsRejectedWhenAuthorizationBecomesStale() async throws {
    let fake = ProjectionClientFake()
    fake.projections = [projection(id: "projection-a")]
    fake.imageData = imageData()
    fake.invalidateAuthorizationOnFeedback = true
    let viewModel = ProjectionViewModel(
      client: fake,
      authorizationIsCurrent: { _ in fake.authorizationIsCurrent })
    await viewModel.load()

    await viewModel.submitFeedback(.down)

    XCTAssertNil(viewModel.feedbackRating)
  }

  func testAPIClientAttachesFirebaseAuthorizationToImageRequest() async throws {
    let data = imageData()
    ProjectionImageURLProtocol.reset(data: data)
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [ProjectionImageURLProtocol.self]
    let client = APIClient(session: URLSession(configuration: configuration))
    await client.setTestAuthHeader("Bearer projection-token")
    let clientBaseURL = await client.baseURL
    let authorization = try XCTUnwrap(
      RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: "projection-owner-a"))
    let projectionID = "00000000-0000-0000-0000-000000000001"

    let loaded = try await client.getProjectionImage(
      projectionID: projectionID,
      expectedOwnerId: authorization.ownerID,
      authorizationSnapshot: authorization)

    XCTAssertEqual(loaded, data)
    XCTAssertEqual(ProjectionImageURLProtocol.authorization, "Bearer projection-token")
    XCTAssertEqual(
      ProjectionImageURLProtocol.url,
      URL(string: "\(clientBaseURL)v1/projection-images/\(projectionID).png"))
  }

  func testAPIClientRejectsMalformedProjectionIDBeforeAttachingAuthorization() async throws {
    ProjectionImageURLProtocol.reset(data: imageData())
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [ProjectionImageURLProtocol.self]
    let client = APIClient(session: URLSession(configuration: configuration))
    await client.setTestAuthHeader("Bearer projection-token")
    let authorization = try XCTUnwrap(
      RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: "projection-owner-a"))

    do {
      _ = try await client.getProjectionImage(
        projectionID: "../attacker.invalid/token-collector",
        expectedOwnerId: authorization.ownerID,
        authorizationSnapshot: authorization)
      XCTFail("Malformed projection identifiers must be rejected")
    } catch {
      XCTAssertTrue(error is APIError)
    }

    XCTAssertNil(ProjectionImageURLProtocol.authorization)
    XCTAssertNil(ProjectionImageURLProtocol.url)
  }

  func testAPIClientAllowsTheManualGenerationPipelineToFinish() async throws {
    ProjectionImageURLProtocol.reset(
      data: Data(
        """
        {"id":"projection-generated","imperative":"Cross the threshold."}
        """.utf8))
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [ProjectionImageURLProtocol.self]
    let client = APIClient(session: URLSession(configuration: configuration))
    await client.setTestAuthHeader("Bearer projection-token")
    let authorization = try XCTUnwrap(
      RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: "projection-owner-a"))

    let generated = try await client.generateProjection(
      expectedOwnerId: authorization.ownerID,
      authorizationSnapshot: authorization)

    XCTAssertEqual(generated?.id, "projection-generated")
    XCTAssertEqual(ProjectionImageURLProtocol.timeoutInterval, 120)
  }

  private func projection(id: String) -> Projection {
    Projection(
      id: id,
      imperative: "Cross the threshold.",
      imageURL: URL(string: "https://projection.test/v1/projection-images/\(id).png"))
  }

  private func imageData() -> Data {
    let image = NSImage(size: NSSize(width: 2, height: 2))
    image.lockFocus()
    NSColor.black.setFill()
    NSRect(x: 0, y: 0, width: 2, height: 2).fill()
    image.unlockFocus()
    return image.tiffRepresentation ?? Data()
  }

  private func transitionOwner(to ownerID: String?) async {
    do {
      _ = try await RuntimeOwnerIdentity.performEffectiveOwnerTransition(
        plannedNextOwner: { _, _ in ownerID },
        quiesceVoice: { _, _ in },
        retargetLocalStorage: { _, _ in },
        ownerDidChange: {},
        { defaults in
          defaults.removeObject(forKey: .automationOwnerOverride)
          if let ownerID {
            defaults.set(ownerID, forKey: .authUserId)
          } else {
            defaults.removeObject(forKey: .authUserId)
          }
        })
    } catch {
      XCTFail("owner transition failed: \(error)")
    }
  }

  private func establishOwner(_ ownerID: String?) async {
    await transitionOwner(to: "projection-owner-bootstrap")
    await transitionOwner(to: ownerID)
  }
}
