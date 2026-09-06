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

    XCTAssertEqual(assembled.nodes.map(\.id), ["brainmap:sarah", "brainmap:omi", "brainmap:tokyo"])
    let sarah = assembled.nodes[0]
    XCTAssertEqual(sarah.label, "Sarah", "the first spelling seen names the node")
    XCTAssertEqual(sarah.aliases, ["Sara"])
    XCTAssertEqual(sarah.memoryIds, ["conversation:a", "conversation:b"])
    XCTAssertEqual(
      assembled.edges.map { ($0.sourceId, $0.targetId, $0.label) }.map { "\($0.0)->\($0.1):\($0.2)" },
      ["brainmap:sarah->brainmap:omi:joined", "brainmap:sarah->brainmap:tokyo:moved to"])
    XCTAssertTrue(assembled.edges.allSatisfy { $0.id.hasPrefix(BrainMapLocalGraphAssembly.nodeIDPrefix) })
    XCTAssertEqual(assembled.edges[0].memoryIds, ["conversation:a"], "an edge cites what both ends cite")
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

  // MARK: Sources

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
