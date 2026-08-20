import XCTest

@testable import Omi_Computer

private final class KnowledgeGraphURLStub: URLProtocol, @unchecked Sendable {
  private static let lock = NSLock()
  private nonisolated(unsafe) static var responses: [(Int, Data)] = []
  private nonisolated(unsafe) static var capturedRequests: [URLRequest] = []

  static func reset() {
    lock.lock()
    responses = []
    capturedRequests = []
    lock.unlock()
  }

  static func setResponses(_ values: [(Int, Data)]) {
    lock.lock()
    responses = values
    lock.unlock()
  }

  static func requests() -> [URLRequest] {
    lock.lock()
    defer { lock.unlock() }
    return capturedRequests
  }

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    let responseSpec: (Int, Data) = {
      Self.lock.lock()
      defer { Self.lock.unlock() }
      Self.capturedRequests.append(request)
      if Self.responses.isEmpty {
        return (500, Data(#"{"detail":"stub ran out of responses"}"#.utf8))
      }
      return Self.responses.removeFirst()
    }()

    guard let url = request.url,
      let response = HTTPURLResponse(
        url: url,
        statusCode: responseSpec.0,
        httpVersion: nil,
        headerFields: nil
      )
    else { return }
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: responseSpec.1)
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}
}

private final class SuspendedKnowledgeGraphURLStub: URLProtocol, @unchecked Sendable {
  private static let lock = NSLock()
  private nonisolated(unsafe) static var pending: SuspendedKnowledgeGraphURLStub?
  private nonisolated(unsafe) static var started = false

  static func reset() {
    lock.lock()
    pending = nil
    started = false
    lock.unlock()
  }

  static func waitUntilStarted() async {
    while true {
      let value = lock.withLock { started }
      if value { return }
      await Task.yield()
    }
  }

  static func release(with body: Data) {
    lock.lock()
    let request = pending
    pending = nil
    lock.unlock()
    request?.respond(with: body)
  }

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    Self.lock.lock()
    Self.pending = self
    Self.started = true
    Self.lock.unlock()
  }

  override func stopLoading() {}

  private func respond(with body: Data) {
    guard let url = request.url,
      let response = HTTPURLResponse(
        url: url,
        statusCode: 200,
        httpVersion: nil,
        headerFields: nil
      )
    else { return }
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: body)
    client?.urlProtocolDidFinishLoading(self)
  }
}

private final class OwnerTransitionPause: @unchecked Sendable {
  private let lock = NSLock()
  private var continuation: CheckedContinuation<Void, Never>?
  private var isSuspended = false

  func suspend() async {
    await withCheckedContinuation { continuation in
      lock.withLock {
        self.continuation = continuation
        isSuspended = true
      }
    }
  }

  func waitUntilSuspended() async {
    while !lock.withLock({ isSuspended }) {
      await Task.yield()
    }
  }

  func release() {
    let continuation = lock.withLock {
      let continuation = self.continuation
      self.continuation = nil
      isSuspended = false
      return continuation
    }
    continuation?.resume()
  }
}

private final class LockedCounter: @unchecked Sendable {
  private let lock = NSLock()
  private var value = 0

  func increment() {
    lock.withLock { value += 1 }
  }

  func read() -> Int {
    lock.withLock { value }
  }
}

@MainActor
final class KnowledgeGraphPaginationTests: XCTestCase {
  override func setUp() async throws {
    setenv("OMI_PYTHON_API_URL", "http://python-test:9001", 1)
    KnowledgeGraphURLStub.reset()
    SuspendedKnowledgeGraphURLStub.reset()
    try await transitionOwner(to: "graph-test-owner")
  }

  override func tearDown() async throws {
    SuspendedKnowledgeGraphURLStub.release(with: pageData())
    SuspendedKnowledgeGraphURLStub.reset()
    KnowledgeGraphURLStub.reset()
    try? await transitionOwner(to: nil)
    unsetenv("OMI_PYTHON_API_URL")
  }

  func testFetchesEveryCanonicalPageSequentiallyAndAccumulatesTheCompleteGraph() async throws {
    KnowledgeGraphURLStub.setResponses([
      (
        200,
        pageData(
          nodes: [nodeData(id: "node-a", memoryIDs: ["memory-a"])],
          edges: [],
          hasMore: true,
          nextCursor: "cursor-1",
          processedItemCount: 200,
          catalogNodes: [nodeData(id: "memory:catalog-a", label: "Unlinked memory")])
      ),
      (
        200,
        pageData(
          nodes: [nodeData(id: "node-b", memoryIDs: ["memory-b"])],
          edges: [],
          hasMore: false,
          eligibleItemCount: 201,
          processedItemCount: 201,
          catalogNodes: [nodeData(id: "memory:catalog-b", label: "Another memory")])
      ),
    ])
    let client = await makeClient(urlProtocolClass: KnowledgeGraphURLStub.self)

    let graph = try await client.getKnowledgeGraph()

    XCTAssertEqual(graph.nodes.map(\.id), ["node-a", "node-b"])
    XCTAssertEqual(graph.nodes.flatMap(\.memoryIds), ["memory-a", "memory-b"])
    XCTAssertFalse(graph.hasMore)
    XCTAssertNil(graph.nextCursor)
    XCTAssertEqual(graph.eligibleItemCount, 201)
    XCTAssertEqual(graph.processedItemCount, 201)
    XCTAssertEqual(graph.catalogNodes?.map(\.id), ["memory:catalog-a", "memory:catalog-b"])

    let requests = KnowledgeGraphURLStub.requests()
    XCTAssertEqual(requests.count, 2)
    XCTAssertEqual(requests[0].url?.path, "/v1/knowledge-graph/canonical")
    XCTAssertEqual(requests[1].url?.path, "/v1/knowledge-graph/canonical")
    XCTAssertEqual(queryItems(in: requests[0].url)["limit"], "200")
    XCTAssertNil(queryItems(in: requests[0].url)["cursor"])
    XCTAssertEqual(queryItems(in: requests[1].url)["limit"], "200")
    XCTAssertEqual(queryItems(in: requests[1].url)["cursor"], "cursor-1")
  }

  func testLegacyPayloadDecodesWithoutCatalogNodesAndPreservesAtlasFallback() throws {
    let legacy = try JSONSerialization.data(
      withJSONObject: [
        "nodes": [nodeData(id: "entity-a"), nodeData(id: "memory:catalog-old", label: "Old catalog")],
        "edges": [],
      ])

    let response = try OmiHTTPTransport.makeDecoder().decode(KnowledgeGraphResponse.self, from: legacy)

    XCTAssertNil(response.catalogNodes)
    XCTAssertEqual(response.nodes.map(\.id), ["entity-a", "memory:catalog-old"])
    XCTAssertEqual(response.atlasNodes.map(\.id), ["entity-a"])
  }

  func testDuplicateNodesEdgesAndMemoryCitationsMergeDeterministicallyAndCleanDanglingEdges() {
    let first = KnowledgeGraphResponse(
      nodes: [
        KnowledgeGraphNode(
          id: "node-a",
          label: "Zeta",
          nodeType: .concept,
          aliases: ["z", "shared"],
          memoryIds: ["memory-2", "shared-memory"],
          createdAt: Date(timeIntervalSince1970: 20),
          updatedAt: Date(timeIntervalSince1970: 30)),
        KnowledgeGraphNode(id: "node-b", label: "Beta", nodeType: .person),
      ],
      edges: [
        KnowledgeGraphEdge(
          id: "edge-z",
          sourceId: "node-a",
          targetId: "node-b",
          label: "relates",
          memoryIds: ["memory-3"]),
        KnowledgeGraphEdge(
          id: "dangling",
          sourceId: "node-a",
          targetId: "missing",
          label: "ignored",
          memoryIds: ["memory-dangling"]),
      ])
    let second = KnowledgeGraphResponse(
      nodes: [
        KnowledgeGraphNode(
          id: "node-a",
          label: "Alpha",
          nodeType: .thing,
          aliases: ["a", "shared"],
          memoryIds: ["memory-1", "shared-memory"],
          createdAt: Date(timeIntervalSince1970: 10),
          updatedAt: Date(timeIntervalSince1970: 40)),
        KnowledgeGraphNode(id: "node-b", label: "Beta", nodeType: .person),
      ],
      edges: [
        KnowledgeGraphEdge(
          id: "edge-a",
          sourceId: "node-a",
          targetId: "node-b",
          label: "connects",
          memoryIds: ["memory-4"]),
        KnowledgeGraphEdge(
          id: "edge-z",
          sourceId: "node-a",
          targetId: "node-b",
          label: "relates",
          memoryIds: ["memory-5"]),
        KnowledgeGraphEdge(
          id: "edge-y",
          sourceId: "node-a",
          targetId: "node-b",
          label: "relates",
          memoryIds: ["memory-6"]),
      ])

    let merged = KnowledgeGraphResponse.merged(pages: [first, second])
    let reversed = KnowledgeGraphResponse.merged(pages: [second, first])

    XCTAssertEqual(merged, reversed)
    let node = merged.nodes.first { $0.id == "node-a" }
    XCTAssertEqual(node?.label, "Alpha")
    XCTAssertEqual(node?.aliases, ["a", "shared", "z"])
    XCTAssertEqual(node?.memoryIds, ["memory-1", "memory-2", "shared-memory"])
    XCTAssertEqual(node?.createdAt, Date(timeIntervalSince1970: 10))
    XCTAssertEqual(node?.updatedAt, Date(timeIntervalSince1970: 40))
    XCTAssertEqual(merged.edges.count, 2, "different relationship labels must remain distinct")
    let edgesByLabel = Dictionary(grouping: merged.edges, by: \.label)
    XCTAssertEqual(edgesByLabel["connects"]?.map(\.id), ["edge-a"])
    XCTAssertEqual(edgesByLabel["connects"]?.flatMap(\.memoryIds), ["memory-4"])
    XCTAssertEqual(edgesByLabel["relates"]?.map(\.id), ["edge-y"])
    XCTAssertEqual(
      edgesByLabel["relates"]?.flatMap(\.memoryIds),
      ["memory-3", "memory-5", "memory-6"])
  }

  func testCanonicalEndpoint404FallsBackToLegacyGraphAndOnlyThatErrorFallsBack() async throws {
    KnowledgeGraphURLStub.setResponses([
      (404, Data(#"{"detail":"not deployed"}"#.utf8)),
      (200, pageData(nodes: [nodeData(id: "legacy")])),
    ])
    let client = await makeClient(urlProtocolClass: KnowledgeGraphURLStub.self)

    let graph = try await client.getKnowledgeGraph()

    XCTAssertEqual(graph.nodes.map(\.id), ["legacy"])
    let requests = KnowledgeGraphURLStub.requests()
    XCTAssertEqual(
      requests.map { $0.url?.path },
      [
        "/v1/knowledge-graph/canonical",
        "/v1/knowledge-graph",
      ])

    KnowledgeGraphURLStub.reset()
    KnowledgeGraphURLStub.setResponses([
      (500, Data(#"{"detail":"backend failed"}"#.utf8)),
      (200, pageData(nodes: [nodeData(id: "must-not-be-used")])),
    ])
    do {
      _ = try await client.getKnowledgeGraph()
      XCTFail("500 must not be hidden by the legacy fallback")
    } catch APIError.httpError(let statusCode, _) {
      XCTAssertEqual(statusCode, 500)
    }
    XCTAssertEqual(KnowledgeGraphURLStub.requests().count, 1)
  }

  func testCanonicalEndpoint405FallsBackToLegacyGraph() async throws {
    KnowledgeGraphURLStub.setResponses([
      (405, Data(#"{"detail":"method not allowed"}"#.utf8)),
      (200, pageData(nodes: [nodeData(id: "legacy-405")])),
    ])
    let client = await makeClient(urlProtocolClass: KnowledgeGraphURLStub.self)

    let graph = try await client.getKnowledgeGraph()

    XCTAssertEqual(graph.nodes.map(\.id), ["legacy-405"])
    XCTAssertEqual(
      KnowledgeGraphURLStub.requests().map { $0.url?.path },
      [
        "/v1/knowledge-graph/canonical",
        "/v1/knowledge-graph",
      ])
  }

  func testCanonicalGraphUnavailable503FallsBackToLegacyGraph() async throws {
    // Production fences canonical intake, so accounts with no canonical state
    // get 503 `canonical_graph_unavailable` — their graph is in the legacy
    // store, which `/v1/knowledge-graph` serves. Failing here left the atlas
    // permanently empty for those accounts.
    KnowledgeGraphURLStub.setResponses([
      (503, Data(#"{"detail":"canonical_graph_unavailable"}"#.utf8)),
      (200, pageData(nodes: [nodeData(id: "legacy-503")])),
    ])
    let client = await makeClient(urlProtocolClass: KnowledgeGraphURLStub.self)

    let graph = try await client.getKnowledgeGraph()

    XCTAssertEqual(graph.nodes.map(\.id), ["legacy-503"])
    XCTAssertEqual(
      KnowledgeGraphURLStub.requests().map { $0.url?.path },
      [
        "/v1/knowledge-graph/canonical",
        "/v1/knowledge-graph",
      ])
  }

  func testTransient503DoesNotFallBackToLegacyGraph() async throws {
    // An outage is not a statement that this account has no canonical graph;
    // hiding it behind the legacy store would publish a stale graph as current.
    KnowledgeGraphURLStub.setResponses([
      (503, Data(#"{"detail":"temporarily unavailable"}"#.utf8)),
      (200, pageData(nodes: [nodeData(id: "must-not-be-used")])),
    ])
    let client = await makeClient(urlProtocolClass: KnowledgeGraphURLStub.self)

    do {
      _ = try await client.getKnowledgeGraph()
      XCTFail("A transient 503 must not be hidden by the legacy fallback")
    } catch APIError.httpError(let statusCode, _) {
      XCTAssertEqual(statusCode, 503)
    }
    XCTAssertEqual(KnowledgeGraphURLStub.requests().count, 1)
  }

  func testOwnerSwitchDiscardsAnInFlightCanonicalPage() async throws {
    try await transitionOwner(to: "graph-owner-a")
    let snapshot = try XCTUnwrap(
      RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: "graph-owner-a"))
    let client = await makeClient(urlProtocolClass: SuspendedKnowledgeGraphURLStub.self)

    let fetch = Task {
      do {
        return Result<KnowledgeGraphResponse, Error>.success(
          try await client.getKnowledgeGraph(authorizationSnapshot: snapshot))
      } catch {
        return Result<KnowledgeGraphResponse, Error>.failure(error)
      }
    }
    await SuspendedKnowledgeGraphURLStub.waitUntilStarted()
    try await transitionOwner(to: "graph-owner-b")
    SuspendedKnowledgeGraphURLStub.release(with: pageData(nodes: [nodeData(id: "owner-a")]))

    switch await fetch.value {
    case .success:
      XCTFail("A page from owner A must not be published after switching to owner B")
    case .failure(let error):
      guard case AuthError.userChangedDuringRequest = error else {
        return XCTFail("Expected owner-switch fencing, got \(error)")
      }
    }
  }

  func testOwnerTransitionWithoutSnapshotFailsBeforeCanonicalFetchOrRebuildRequest() async throws {
    let pause = OwnerTransitionPause()
    let transition = Task {
      try await RuntimeOwnerIdentity.performEffectiveOwnerTransition(
        plannedNextOwner: { _, _ in "graph-transition-owner" },
        quiesceVoice: { _, _ in await pause.suspend() },
        retargetLocalStorage: { _, _ in },
        prepareLocalStorageTransition: { _, _ in },
        ownerDidChange: {},
        { defaults in
          defaults.set("graph-transition-owner", forKey: .authUserId)
        }
      )
    }
    await pause.waitUntilSuspended()
    defer { pause.release() }
    XCTAssertNil(RuntimeOwnerIdentity.captureAuthorizationSnapshot())

    let client = await makeClient(urlProtocolClass: KnowledgeGraphURLStub.self)
    await assertOwnerFence {
      _ = try await client.getKnowledgeGraph()
    }
    await assertOwnerFence {
      _ = try await client.rebuildKnowledgeGraph()
    }
    XCTAssertTrue(KnowledgeGraphURLStub.requests().isEmpty)

    let viewModelFetches = LockedCounter()
    let viewModel = MemoryGraphViewModel(
      canonicalGraphFetcher: { _ in
        viewModelFetches.increment()
        return KnowledgeGraphResponse(nodes: [], edges: [])
      },
      initialGraphResponse: KnowledgeGraphResponse(nodes: [], edges: []))
    await viewModel.prepareCanonicalAtlas()
    let rebuilt = await viewModel.rebuildCanonicalAtlas()
    XCTAssertFalse(rebuilt)
    XCTAssertEqual(viewModelFetches.read(), 0)

    pause.release()
    _ = try await transition.value
  }

  func testCanonicalAtlas503DoesNotPublishNonemptyLocalProjection() async throws {
    let localProjection = KnowledgeGraphResponse(
      nodes: [KnowledgeGraphNode(id: "local-only", label: "Local", nodeType: .concept)],
      edges: [])
    let viewModel = MemoryGraphViewModel(
      canonicalGraphFetcher: { _ in
        throw APIError.httpError(statusCode: 503, detail: "temporarily unavailable")
      },
      initialGraphResponse: localProjection)

    await viewModel.prepareCanonicalAtlas()

    XCTAssertTrue(viewModel.graphResponse.nodes.isEmpty)
    XCTAssertTrue(viewModel.graphResponse.edges.isEmpty)
    XCTAssertNil(viewModel.canonicalAtlasProjection)
    XCTAssertTrue(viewModel.isEmpty)
  }

  func testCatalogOnlyCanonicalAtlasIsRenderableAndActivationCached() async throws {
    let fetches = LockedCounter()
    let response = KnowledgeGraphResponse(
      nodes: [],
      edges: [],
      catalogNodes: [KnowledgeGraphNode(id: "memory-only", label: "Canonical memory", nodeType: .concept)])
    let viewModel = MemoryGraphViewModel(
      canonicalGraphFetcher: { _ in
        fetches.increment()
        return response
      },
      initialGraphResponse: KnowledgeGraphResponse(nodes: [], edges: []))

    await viewModel.prepareCanonicalAtlas()
    await viewModel.prepareCanonicalAtlas()

    XCTAssertEqual(fetches.read(), 1, "A catalog-only atlas is a settled atlas, not an empty retry loop")
    XCTAssertFalse(viewModel.isEmpty)
    XCTAssertFalse(viewModel.isLoading)
    XCTAssertEqual(viewModel.canonicalAtlasProjection?.snapshot.nodes.map(\.id), ["memory-only"])
  }

  private func makeClient(urlProtocolClass: URLProtocol.Type) async -> APIClient {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [urlProtocolClass]
    let client = APIClient(session: URLSession(configuration: configuration))
    await client.setTestAuthHeader("Bearer graph-test-token")
    return client
  }

  private func queryItems(in url: URL?) -> [String: String] {
    var result: [String: String] = [:]
    let items =
      URLComponents(
        url: url ?? URL(string: "https://invalid")!,
        resolvingAgainstBaseURL: false
      )?.queryItems ?? []
    for item in items {
      if let value = item.value { result[item.name] = value }
    }
    return result
  }

  private func transitionOwner(to ownerID: String?) async throws {
    _ = try await RuntimeOwnerIdentity.performEffectiveOwnerTransition(
      plannedNextOwner: { _, _ in ownerID },
      quiesceVoice: { _, _ in },
      retargetLocalStorage: { _, _ in },
      prepareLocalStorageTransition: { _, _ in },
      ownerDidChange: {},
      { defaults in
        if let ownerID {
          defaults.set(ownerID, forKey: .authUserId)
        } else {
          defaults.removeObject(forKey: .authUserId)
        }
      }
    )
  }

  private func assertOwnerFence(
    operation: () async throws -> Void
  ) async {
    do {
      try await operation()
      XCTFail("Owner transition must fail closed")
    } catch {
      guard case AuthError.userChangedDuringRequest = error else {
        return XCTFail("Expected owner transition fence, got \(error)")
      }
    }
  }
}

private func nodeData(
  id: String,
  label: String? = nil,
  aliases: [String] = [],
  memoryIDs: [String] = []
) -> [String: Any] {
  [
    "id": id,
    "label": label ?? id,
    "node_type": "concept",
    "aliases": aliases,
    "memory_ids": memoryIDs,
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z",
  ]
}

private func pageData(
  nodes: [[String: Any]] = [],
  edges: [[String: Any]] = [],
  hasMore: Bool = false,
  nextCursor: String? = nil,
  eligibleItemCount: Int? = nil,
  processedItemCount: Int? = nil,
  catalogNodes: [[String: Any]]? = nil
) -> Data {
  var object: [String: Any] = [
    "nodes": nodes,
    "edges": edges,
    "has_more": hasMore,
  ]
  if let nextCursor { object["next_cursor"] = nextCursor }
  if let eligibleItemCount { object["eligible_item_count"] = eligibleItemCount }
  if let processedItemCount { object["processed_item_count"] = processedItemCount }
  if let catalogNodes { object["catalog_nodes"] = catalogNodes }
  return (try? JSONSerialization.data(withJSONObject: object)) ?? Data()
}
