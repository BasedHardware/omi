import XCTest

@testable import Omi_Computer

/// The desktop-side Brain Map rebuild: what it reads, how it spends its
/// bounded extraction budget, what it cites, and how the result sits under
/// the server graph.
final class BrainMapLocalRebuildTests: XCTestCase {
  private func source(_ id: String, _ text: String) -> BrainMapRebuildSource {
    BrainMapRebuildSource(id: id, text: text)
  }

  private func node(_ id: String, _ label: String, aliases: [String] = [], memoryIds: [String] = [])
    -> KnowledgeGraphNode
  {
    KnowledgeGraphNode(id: id, label: label, nodeType: .concept, aliases: aliases, memoryIds: memoryIds)
  }

  // MARK: Batching

  func testBatchesPackSourcesByCharacterBudgetInOrder() {
    let sources = (0..<7).map { source("c\($0)", String(repeating: "x", count: 100)) }

    let batches = BrainMapExtractionBatches.make(sources, charBudget: 310, maxBatches: 24)

    // 102 chars per source: three fit under 310, so 3 + 3 + 1.
    XCTAssertEqual(batches.map { $0.map(\.id) }, [["c0", "c1", "c2"], ["c3", "c4", "c5"], ["c6"]])
  }

  func testBatchesStopAtTheCallBudgetAndLeaveTheRestForNextTime() {
    let sources = (0..<10).map { source("c\($0)", "text") }

    let batches = BrainMapExtractionBatches.make(sources, charBudget: 6, maxBatches: 3)

    XCTAssertEqual(batches.count, 3)
    XCTAssertEqual(batches.flatMap { $0.map(\.id) }, ["c0", "c1", "c2"])
  }

  func testTheDefaultBudgetStaysUnderTheServersHourlyExtractLimit() {
    XCTAssertLessThan(BrainMapExtractionBatches.maxBatches, 30)
    XCTAssertLessThan(BrainMapExtractionBatches.charBudget, 100_000)
  }

  // MARK: Citations

  func testAnEntityCitesTheSourcesThatNameIt() {
    let batch = [
      source("conversation:a", "Talked with Sarah about the launch."),
      source("conversation:b", "Ran along the river."),
      source("m1", "sarah prefers mornings."),
    ]

    let citations = BrainMapCitationAttribution.citations(for: node("n", "Sarah"), in: batch)

    XCTAssertEqual(citations, ["conversation:a", "m1"])
  }

  func testAnInferredEntityCitesTheWholeBatchRatherThanNothing() {
    let batch = [source("conversation:a", "Talked about the launch."), source("m1", "Runs daily.")]

    let citations = BrainMapCitationAttribution.citations(for: node("n", "Product launch"), in: batch)

    XCTAssertEqual(citations, ["conversation:a", "m1"])
  }

  // MARK: Assembly

  func testAssemblyMergesTheSameLabelAcrossBatchesAndPrefixesEveryID() {
    let batchA = [source("conversation:a", "Sarah joined Omi.")]
    let batchB = [source("conversation:b", "sarah moved to Tokyo.")]
    let graphA = KnowledgeGraphExtractResponse(
      nodes: [node("1", "Sarah"), node("2", "Omi")],
      edges: [KnowledgeGraphEdge(id: "e", sourceId: "1", targetId: "2", label: "joined")])
    let graphB = KnowledgeGraphExtractResponse(
      nodes: [node("9", "sarah", aliases: ["Sara"]), node("8", "Tokyo")],
      edges: [KnowledgeGraphEdge(id: "e", sourceId: "9", targetId: "8", label: "moved to")])

    let assembled = BrainMapLocalGraphAssembly.assemble([(batchA, graphA), (batchB, graphB)])

    let id = BrainMapLocalGraphAssembly.nodeID(for:)
    XCTAssertEqual(assembled.nodes.map(\.id), [id("Sarah"), id("Omi"), id("Tokyo")])
    let sarah = assembled.nodes[0]
    XCTAssertEqual(sarah.label, "Sarah", "the first spelling seen names the node")
    XCTAssertEqual(sarah.aliases, ["Sara"])
    XCTAssertEqual(sarah.memoryIds, ["conversation:a", "conversation:b"])
    XCTAssertEqual(
      assembled.edges.map { ($0.sourceId, $0.targetId, $0.label) }.map { "\($0.0)->\($0.1):\($0.2)" },
      ["\(id("Sarah"))->\(id("Omi")):joined", "\(id("Sarah"))->\(id("Tokyo")):moved to"])
    XCTAssertTrue(assembled.edges.allSatisfy { $0.id.hasPrefix(BrainMapLocalGraphAssembly.nodeIDPrefix) })
    XCTAssertEqual(assembled.edges[0].memoryIds, ["conversation:a"], "an edge cites what both ends cite")
  }

  func testNodeIDsAreStableReadableAndDistinctForDistinctLabels() {
    let id = BrainMapLocalGraphAssembly.nodeID(for:)

    XCTAssertEqual(id("Sarah"), id("  sarah "), "case and surrounding whitespace do not make a new entity")
    XCTAssertEqual(id("Sarah"), "brainmap:sarah-" + BrainMapLocalGraphAssembly.stableHash("sarah"))
    // These slug identically ("a-b"); they are not the same entity.
    XCTAssertEqual(Set([id("A-B"), id("A B"), id("a.b")]).count, 3)
    XCTAssertEqual(id("!!!"), "brainmap:entity-" + BrainMapLocalGraphAssembly.stableHash("!!!"))
    XCTAssertEqual(BrainMapLocalGraphAssembly.stableHash("omi"), BrainMapLocalGraphAssembly.stableHash("omi"))
    XCTAssertEqual(BrainMapLocalGraphAssembly.stableHash("omi").count, 8)
  }

  func testAssemblyDropsSelfLoopsAndEdgesToUnknownNodes() {
    let batch = [source("m1", "Omi is Omi.")]
    let graph = KnowledgeGraphExtractResponse(
      nodes: [node("1", "Omi")],
      edges: [
        KnowledgeGraphEdge(id: "a", sourceId: "1", targetId: "1", label: "is"),
        KnowledgeGraphEdge(id: "b", sourceId: "1", targetId: "missing", label: "knows"),
      ])

    let assembled = BrainMapLocalGraphAssembly.assemble([(batch, graph)])

    XCTAssertEqual(assembled.nodes.count, 1)
    XCTAssertTrue(assembled.edges.isEmpty)
  }

  // MARK: Merge under the server graph

  func testALocalEntityNamingAServerEntityLandsOnTheServerID() {
    let server = KnowledgeGraphResponse(
      nodes: [node("srv-nathan", "Nathan", memoryIds: ["m1"]), node("srv-omi", "Omi")],
      edges: [KnowledgeGraphEdge(id: "srv-e", sourceId: "srv-nathan", targetId: "srv-omi", label: "works at")])
    let local = KnowledgeGraphResponse(
      nodes: [
        node("brainmap:nathan", "nathan", memoryIds: ["conversation:a"]),
        node("brainmap:tokyo", "Tokyo", memoryIds: ["conversation:a"]),
      ],
      edges: [
        KnowledgeGraphEdge(
          id: "brainmap:edge:1", sourceId: "brainmap:nathan", targetId: "brainmap:tokyo", label: "visited",
          memoryIds: ["conversation:a"]),
        KnowledgeGraphEdge(
          id: "brainmap:edge:2", sourceId: "brainmap:nathan", targetId: "brainmap:omi-missing", label: "x"),
      ])

    let merged = BrainMapLocalGraphMerge.merge(server: server, local: local)

    XCTAssertEqual(merged.nodes.map(\.id), ["srv-nathan", "srv-omi", "brainmap:tokyo"])
    XCTAssertEqual(merged.nodes[0].label, "Nathan", "the server's spelling wins")
    XCTAssertEqual(merged.nodes[0].memoryIds, ["conversation:a", "m1"])
    XCTAssertEqual(merged.edges.map(\.id), ["srv-e", "brainmap:edge:1"])
    XCTAssertEqual(merged.edges[1].sourceId, "srv-nathan")
    XCTAssertEqual(merged.edges[1].targetId, "brainmap:tokyo")
  }

  func testMergeKeepsServerMetadataAndIsANoOpWithoutALocalGraph() {
    let status = KnowledgeGraphRebuildStatus(
      status: "complete", startedAt: nil, finishedAt: Date(), nodesCount: 1, edgesCount: 0)
    let server = KnowledgeGraphResponse(
      nodes: [node("a", "A")], edges: [], catalogNodes: [node("memory:x", "x")], rebuild: status)

    XCTAssertEqual(
      BrainMapLocalGraphMerge.merge(server: server, local: KnowledgeGraphResponse(nodes: [], edges: [])), server)
    let merged = BrainMapLocalGraphMerge.merge(
      server: server, local: KnowledgeGraphResponse(nodes: [node("brainmap:b", "B")], edges: []))
    XCTAssertEqual(merged.catalogNodes?.map(\.id), ["memory:x"])
    XCTAssertEqual(merged.rebuild, status)
  }

  // MARK: The run

  private struct Scripted {
    var conversations: [ServerConversation] = []
    var memories: [ServerMemory] = []
    var people: [Person] = []
    var goals: [Goal] = []
    var failingRead: String?
  }

  private final class StoreSpy: @unchecked Sendable {
    var writes = 0
  }

  private func reads(_ script: Scripted) -> BrainMapLocalRebuilder.Reads {
    BrainMapLocalRebuilder.Reads(
      conversations: { _, _ in
        if script.failingRead == "conversations" { throw APIError.httpError(statusCode: 500, detail: "down") }
        return script.conversations
      },
      memories: { _ in
        if script.failingRead == "memories" { throw APIError.httpError(statusCode: 500, detail: "down") }
        return script.memories
      },
      people: {
        if script.failingRead == "people" { throw APIError.httpError(statusCode: 500, detail: "down") }
        return script.people
      },
      goals: {
        if script.failingRead == "goals" { throw APIError.httpError(statusCode: 500, detail: "down") }
        return script.goals
      })
  }

  private func memory(_ id: String, _ content: String) -> ServerMemory {
    ServerMemory(
      id: id, content: content, category: .system, tier: .shortTerm,
      createdAt: Date(timeIntervalSince1970: 1), updatedAt: Date(timeIntervalSince1970: 2),
      conversationId: nil, reviewed: false, userReview: nil, visibility: "private", manuallyAdded: false,
      scoring: nil, source: "desktop", confidence: nil, sourceApp: nil, contextSummary: nil, isRead: false,
      isDismissed: false, tags: [], reasoning: nil, currentActivity: nil, inputDeviceName: nil,
      windowTitle: nil, headline: nil)
  }

  private func run(
    _ script: Scripted, store: StoreSpy,
    extract: @escaping BrainMapLocalRebuilder.Extract
  ) async throws -> BrainMapLocalRebuilder.Report {
    try await BrainMapLocalRebuilder.run(
      reads: reads(script),
      isAuthorizationCurrent: { true },
      progress: { _ in },
      extract: extract,
      store: { _, _, _ in store.writes += 1 },
      retryDelay: .zero)
  }

  func testARebuildThatCannotReadASourceChangesNothing() async {
    for source in ["conversations", "memories", "people", "goals"] {
      let store = StoreSpy()
      var script = Scripted(memories: [memory("m1", "Runs daily.")])
      script.failingRead = source

      do {
        _ = try await run(script, store: store) { _ in KnowledgeGraphExtractResponse(nodes: [], edges: []) }
        XCTFail("\(source) unreadable should fail the rebuild")
      } catch let failure as BrainMapLocalRebuilder.Failure {
        XCTAssertEqual(failure, .sourceUnreadable(source))
      } catch {
        XCTFail("unexpected \(error)")
      }
      XCTAssertEqual(store.writes, 0, "the previous map stays when \(source) cannot be read")
    }
  }

  func testABatchThatFailsTwiceLeavesThePreviousMapAndSaysSo() async {
    let store = StoreSpy()
    // Three memories too long to share a batch, so three batches; the middle one never extracts.
    let script = Scripted(
      memories: ["a", "b", "c"].map { memory("m-\($0)", String(repeating: $0, count: 20_000)) })
    let calls = StoreSpy()

    do {
      _ = try await run(script, store: store) { text in
        calls.writes += 1
        if text.hasPrefix("bbb") { throw APIError.httpError(statusCode: 429) }
        return KnowledgeGraphExtractResponse(
          nodes: [KnowledgeGraphNode(id: "1", label: "Omi", nodeType: .concept)], edges: [])
      }
      XCTFail("a batch that never extracts should fail the rebuild")
    } catch let failure as BrainMapLocalRebuilder.Failure {
      XCTAssertEqual(failure, .extractionIncomplete(failed: 1, of: 3))
    } catch {
      XCTFail("unexpected \(error)")
    }
    XCTAssertEqual(calls.writes, 4, "two good batches once, the failing one twice")
    XCTAssertEqual(store.writes, 0)
  }

  func testABatchThatFailsOnceIsRetriedAndTheRebuildCompletes() async throws {
    let store = StoreSpy()
    let script = Scripted(memories: [memory("m1", "Sarah joined Omi.")])
    let attempts = StoreSpy()

    let report = try await run(script, store: store) { _ in
      attempts.writes += 1
      if attempts.writes == 1 { throw APIError.httpError(statusCode: 502) }
      return KnowledgeGraphExtractResponse(
        nodes: [
          KnowledgeGraphNode(id: "1", label: "Sarah", nodeType: .concept),
          KnowledgeGraphNode(id: "2", label: "Omi", nodeType: .concept),
        ],
        edges: [KnowledgeGraphEdge(id: "e", sourceId: "1", targetId: "2", label: "joined")])
    }

    XCTAssertEqual(report.batches, 1)
    XCTAssertEqual(report.retriedBatches, 1)
    XCTAssertEqual(report.nodes, 2)
    XCTAssertEqual(store.writes, 1)
  }

  // MARK: The local store

  func testRowsSavedOutsideTheRebuildAreMovedOffItsPrefix() {
    let now = Date()
    let nodes = [
      LocalKGNodeRecord(nodeId: "brainmap:x", label: "X", nodeType: "concept", createdAt: now, updatedAt: now),
      LocalKGNodeRecord(nodeId: "file:y", label: "Y", nodeType: "concept", createdAt: now, updatedAt: now),
    ]
    let edges = [
      LocalKGEdgeRecord(
        edgeId: "brainmap:e", sourceNodeId: "brainmap:x", targetNodeId: "file:y", label: "l", createdAt: now)
    ]

    let relocated = LocalKGReservedIdentifiers.relocating(nodes: nodes, edges: edges)

    XCTAssertEqual(relocated.nodes.map(\.nodeId), ["local:brainmap:x", "file:y"])
    XCTAssertEqual(relocated.edges[0].edgeId, "local:brainmap:e")
    XCTAssertEqual(relocated.edges[0].sourceNodeId, "local:brainmap:x")
    XCTAssertEqual(relocated.edges[0].targetNodeId, "file:y")
  }

  func testAnEdgeRecordCarriesItsCitations() {
    let record = LocalKGEdgeRecord(
      edgeId: "e", sourceNodeId: "a", targetNodeId: "b", label: "l", createdAt: Date(),
      memoryIdsJson: "[\"conversation:c1\",\"m1\"]")

    XCTAssertEqual(record.toKnowledgeGraphEdge().memoryIds, ["conversation:c1", "m1"])
    XCTAssertEqual(
      LocalKGEdgeRecord(edgeId: "e", sourceNodeId: "a", targetNodeId: "b", label: "l", createdAt: Date())
        .toKnowledgeGraphEdge().memoryIds, [])
  }

  // MARK: Waiting for the server

  func testAServerRebuildIsFinishedWhenItsOwnIDReportsAnEnd() {
    let asked = Date()
    let mine = KnowledgeGraphRebuildStatus(
      status: "complete", startedAt: asked.addingTimeInterval(5), finishedAt: asked.addingTimeInterval(60),
      nodesCount: 1, edgesCount: 0, rebuildId: "mine")
    let earlier = KnowledgeGraphRebuildStatus(
      status: "complete", startedAt: asked.addingTimeInterval(-600), finishedAt: asked.addingTimeInterval(60),
      nodesCount: 1, edgesCount: 0, rebuildId: "earlier")
    let running = KnowledgeGraphRebuildStatus(
      status: "running", startedAt: asked.addingTimeInterval(5), finishedAt: nil, nodesCount: nil,
      edgesCount: nil, rebuildId: "mine")

    XCTAssertTrue(mine.finished(since: asked, rebuildID: "mine"))
    XCTAssertFalse(earlier.finished(since: asked, rebuildID: "mine"), "an earlier rebuild ending is not mine ending")
    XCTAssertFalse(running.finished(since: asked, rebuildID: "mine"))
    // A server without ids: the rebuild must have started as well as finished after the request.
    let unlabelledEarlier = KnowledgeGraphRebuildStatus(
      status: "complete", startedAt: asked.addingTimeInterval(-600), finishedAt: asked.addingTimeInterval(60),
      nodesCount: 1, edgesCount: 0)
    let unlabelledMine = KnowledgeGraphRebuildStatus(
      status: "complete", startedAt: asked.addingTimeInterval(5), finishedAt: asked.addingTimeInterval(60),
      nodesCount: 1, edgesCount: 0)
    XCTAssertFalse(unlabelledEarlier.finished(since: asked, rebuildID: "mine"))
    XCTAssertTrue(unlabelledMine.finished(since: asked, rebuildID: "mine"))
    XCTAssertTrue(unlabelledMine.finished(since: asked))
  }

  // MARK: Sources

  func testTheWholeAccountSourcesAreNotOpenable() {
    XCTAssertEqual(MemoryAtlasEvidence.source(for: .people)?.isOpenable, false)
    XCTAssertEqual(MemoryAtlasEvidence.source(for: .goals)?.isOpenable, false)
    XCTAssertTrue(
      MemoryAtlasEvidence.conversation(id: "c", title: "T", overview: "", createdAt: nil).isOpenable)
  }

  func testPeopleAndGoalsBecomeOneSourceEach() {
    XCTAssertEqual(
      BrainMapRebuildSources.people(names: ["Sarah", " Alex ", "", "Sarah"])?.text,
      "People the user knows and talks with: Alex, Sarah.")
    XCTAssertNil(BrainMapRebuildSources.people(names: ["", "  "]))
    XCTAssertEqual(
      BrainMapRebuildSources.goals([
        (title: "Ship v1", description: "Ship v1"), (title: "Run more", description: "Three runs a week"),
        (title: "", description: nil),
      ])?.text,
      "Goals the user is working toward: Ship v1; Run more — Three runs a week.")
  }

  func testCitationIDsMatchWhatTheInspectorResolves() {
    XCTAssertEqual(
      MemoryAtlasEvidence.Citation(BrainMapRebuildSources.conversationPrefix + "c1"), .conversation("c1"))
    XCTAssertEqual(MemoryAtlasEvidence.Citation(BrainMapRebuildSources.peopleID), .people)
    XCTAssertEqual(MemoryAtlasEvidence.Citation(BrainMapRebuildSources.goalsID), .goals)
    XCTAssertEqual(MemoryAtlasEvidence.Citation("mem_1"), .memory("mem_1"))
  }
}
