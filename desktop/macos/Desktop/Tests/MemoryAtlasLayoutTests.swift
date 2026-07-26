import XCTest

@testable import Omi_Computer

final class MemoryAtlasLayoutTests: XCTestCase {
  func testLayoutAnchorsNamedPersonAndProducesStablePositions() throws {
    let graph = sampleGraph()

    let first = MemoryAtlasLayoutEngine.makeSnapshot(graph: graph, userName: "David")
    let second = MemoryAtlasLayoutEngine.makeSnapshot(graph: graph, userName: "David")

    XCTAssertEqual(first.anchorNodeID, "david")
    XCTAssertEqual(first.nodes.map(\.id), second.nodes.map(\.id))
    XCTAssertEqual(
      first.nodes.map(\.normalizedPosition),
      second.nodes.map(\.normalizedPosition)
    )
    XCTAssertEqual(first.nodeByID["david"]?.normalizedPosition, MemoryAtlasCluster.starCenter)
  }

  func testNodeTypesDriveStarAtlasConstellations() throws {
    let snapshot = MemoryAtlasLayoutEngine.makeSnapshot(graph: fiveTypeGraph(), userName: "David")

    XCTAssertEqual(snapshot.nodeByID["casey"]?.cluster, .person)
    XCTAssertEqual(snapshot.nodeByID["openai"]?.cluster, .organization)
    XCTAssertEqual(snapshot.nodeByID["singapore"]?.cluster, .place)
    XCTAssertEqual(snapshot.nodeByID["python"]?.cluster, .thing)
    XCTAssertEqual(snapshot.nodeByID["strategy"]?.cluster, .concept)
    XCTAssertEqual(snapshot.activeClusters, [.person, .organization, .place, .thing, .concept])

    let centers = snapshot.activeClusters.map(snapshot.center(for:))
    XCTAssertEqual(centers[0], CGPoint(x: 0.5, y: 0.25))
    XCTAssertEqual(centers[1].x, 0.642_658, accuracy: 0.000_001)
    XCTAssertEqual(centers[1].y, 0.422_746, accuracy: 0.000_001)
    XCTAssertEqual(centers[2].x, 0.588_168, accuracy: 0.000_001)
    XCTAssertEqual(centers[2].y, 0.702_254, accuracy: 0.000_001)
    XCTAssertEqual(centers[3].x, 0.411_832, accuracy: 0.000_001)
    XCTAssertEqual(centers[3].y, 0.702_254, accuracy: 0.000_001)
    XCTAssertEqual(centers[4].x, 0.357_342, accuracy: 0.000_001)
    XCTAssertEqual(centers[4].y, 0.422_746, accuracy: 0.000_001)
    XCTAssertTrue(
      centers.allSatisfy { center in
        abs(hypot((center.x - 0.5) / 0.15, (center.y - 0.5) / 0.25) - 1) < 0.000_001
      })
  }

  func testSingleActiveTypeTakesTheStarCenterInsteadOfTheRing() {
    // Regression: a one-type atlas placed its only constellation at the top of
    // the ring (0.5, 0.25), stranding every node in the upper-middle of the
    // canvas with the rest of the viewport empty.
    let centers = MemoryAtlasCluster.centers(for: [.concept])

    XCTAssertEqual(centers.count, 1)
    XCTAssertEqual(centers[.concept], MemoryAtlasCluster.starCenter)
  }

  func testTwoOrMoreActiveTypesStillFormTheRing() {
    let centers = MemoryAtlasCluster.centers(for: [.organization, .thing])

    XCTAssertEqual(centers[.organization], CGPoint(x: 0.5, y: 0.25))
    XCTAssertEqual(centers[.thing], CGPoint(x: 0.5, y: 0.75))
  }

  func testSparseAtlasesExpandOrbitsAndDenseOnesKeepTunedDensity() {
    // The ring is what fills the canvas when several types are active. With
    // one or two, the orbits have to do that work instead.
    XCTAssertGreaterThan(
      MemoryAtlasLayoutEngine.orbitSpreadScale(activeClusterCount: 1),
      MemoryAtlasLayoutEngine.orbitSpreadScale(activeClusterCount: 2)
    )
    XCTAssertGreaterThan(
      MemoryAtlasLayoutEngine.orbitSpreadScale(activeClusterCount: 2),
      MemoryAtlasLayoutEngine.orbitSpreadScale(activeClusterCount: 3)
    )
    // Three or more keeps the density the viewport budgets and the performance
    // harness were measured against — do not let this drift.
    for count in 3...5 {
      XCTAssertEqual(MemoryAtlasLayoutEngine.orbitSpreadScale(activeClusterCount: count), 1)
    }
  }

  func testSingleTypeAtlasActuallySpreadsAcrossTheCanvas() throws {
    let nodes = (0..<40).map {
      KnowledgeGraphNode(id: "c\($0)", label: "Concept \($0)", nodeType: .concept)
    }
    let snapshot = MemoryAtlasLayoutEngine.makeSnapshot(
      graph: KnowledgeGraphResponse(nodes: nodes, edges: []),
      userName: "David"
    )

    XCTAssertEqual(snapshot.activeClusters, [.concept])

    let ys = snapshot.nodes.map(\.normalizedPosition.y)
    let xs = snapshot.nodes.map(\.normalizedPosition.x)
    let verticalSpread = (ys.max() ?? 0) - (ys.min() ?? 0)
    let horizontalSpread = (xs.max() ?? 0) - (xs.min() ?? 0)

    // Before the fix this atlas occupied roughly the top third of the canvas.
    XCTAssertGreaterThan(verticalSpread, 0.5)
    XCTAssertGreaterThan(horizontalSpread, 0.25)
    // Still inside the clamped drawing area.
    XCTAssertGreaterThanOrEqual(ys.min() ?? 0, 0.08)
    XCTAssertLessThanOrEqual(ys.max() ?? 1, 0.92)
  }

  func testEmptyTypesRedistributeAroundTheStar() {
    let snapshot = MemoryAtlasLayoutEngine.makeSnapshot(graph: sampleGraph(), userName: "David")

    XCTAssertEqual(snapshot.activeClusters, [.organization, .thing])
    XCTAssertEqual(snapshot.center(for: .organization), CGPoint(x: 0.5, y: 0.25))
    XCTAssertEqual(snapshot.center(for: .thing), CGPoint(x: 0.5, y: 0.75))
  }

  func testEveryRenderedEdgeHasPlacedEndpoints() {
    let snapshot = MemoryAtlasLayoutEngine.makeSnapshot(graph: sampleGraph(), userName: "David")

    XCTAssertEqual(snapshot.edges.count, 3)
    XCTAssertTrue(
      snapshot.edges.allSatisfy { edge in
        snapshot.nodes.contains { $0.normalizedPosition == edge.source }
          && snapshot.nodes.contains { $0.normalizedPosition == edge.target }
      })
  }

  func testLayoutCoalescesDuplicateServerIdentifiersWithoutTrapping() {
    let graph = KnowledgeGraphResponse(
      nodes: [
        KnowledgeGraphNode(id: "david", label: "David stale", nodeType: .person),
        KnowledgeGraphNode(id: "omi", label: "Omi", nodeType: .thing),
        KnowledgeGraphNode(id: "david", label: "David current", nodeType: .person),
      ],
      edges: [
        KnowledgeGraphEdge(id: "relationship", sourceId: "david", targetId: "missing", label: "uses"),
        KnowledgeGraphEdge(id: "relationship", sourceId: "david", targetId: "omi", label: "works_on"),
      ]
    )

    let snapshot = MemoryAtlasLayoutEngine.makeSnapshot(graph: graph, userName: "David current")

    XCTAssertEqual(snapshot.nodes.count, 2)
    XCTAssertEqual(snapshot.nodeByID["david"]?.node.label, "David current")
    XCTAssertEqual(snapshot.edges.count, 1)
    XCTAssertEqual(snapshot.edges.first?.edge.targetId, "omi")
  }

  func testPresentationModeKeepsLegacyGraphUntilCanonicalLifecycleIsExposed() {
    XCTAssertEqual(
      MemoryGraphPresentationMode.resolve(canonicalLifecycleExposed: false),
      .legacyBrainMap
    )
    XCTAssertEqual(
      MemoryGraphPresentationMode.resolve(canonicalLifecycleExposed: true),
      .canonicalAtlas
    )
    XCTAssertEqual(
      MemoryGraphPresentationMode.resolve(
        canonicalLifecycleExposed: false,
        forceCanonicalAtlasForLocalQA: true
      ),
      .canonicalAtlas
    )
  }
  func testCollapsesSelfSynonymNodeIntoSingleAnchor() {
    let graph = KnowledgeGraphResponse(
      nodes: [
        KnowledgeGraphNode(id: "david", label: "David", nodeType: .person),
        KnowledgeGraphNode(id: "user", label: "User", nodeType: .person),
        KnowledgeGraphNode(id: "omi", label: "Omi", nodeType: .thing),
        KnowledgeGraphNode(id: "openai", label: "OpenAI", nodeType: .organization),
      ],
      edges: [
        KnowledgeGraphEdge(id: "uses", sourceId: "user", targetId: "omi", label: "uses"),
        KnowledgeGraphEdge(id: "with", sourceId: "david", targetId: "openai", label: "works_with"),
      ]
    )

    let snapshot = MemoryAtlasLayoutEngine.makeSnapshot(graph: graph, userName: "David")

    // Exactly one "you": the generic self node is folded away entirely.
    XCTAssertEqual(snapshot.anchorNodeID, "david")
    XCTAssertNil(snapshot.nodeByID["user"])
    // Its relationship is rerouted onto the anchor, not dropped.
    XCTAssertEqual(snapshot.neighborIDsByNodeID["david"], ["omi", "openai"])
    XCTAssertTrue(snapshot.edges.allSatisfy { $0.edge.sourceId != "user" && $0.edge.targetId != "user" })
  }

  func testCollapseDropsRelationshipsThatBecomeSelfLoops() {
    let graph = KnowledgeGraphResponse(
      nodes: [
        KnowledgeGraphNode(id: "david", label: "David", nodeType: .person),
        KnowledgeGraphNode(id: "me", label: "Me", nodeType: .person),
        KnowledgeGraphNode(id: "omi", label: "Omi", nodeType: .thing),
      ],
      edges: [
        // A relationship between the two self nodes collapses to David→David.
        KnowledgeGraphEdge(id: "self", sourceId: "david", targetId: "me", label: "is"),
        KnowledgeGraphEdge(id: "uses", sourceId: "me", targetId: "omi", label: "uses"),
      ]
    )

    let snapshot = MemoryAtlasLayoutEngine.makeSnapshot(graph: graph, userName: "David")

    XCTAssertNil(snapshot.nodeByID["me"])
    XCTAssertEqual(snapshot.edges.map(\.edge.id), ["uses"])
    XCTAssertEqual(snapshot.neighborIDsByNodeID["david"], ["omi"])
  }

  // MARK: - Parallel edge merging (Fix 1)

  func testParallelEdgesBetweenTheSamePairCollapseToOnePlacementWithWeightAndUnionedMemories() throws {
    // Real example from a user's graph: the concept "Weekly Product Training
    // Session" listed both "sang@stably.io — includes" and "— with" as two
    // separate connections that are really one relationship described twice.
    let graph = KnowledgeGraphResponse(
      nodes: [
        KnowledgeGraphNode(id: "david", label: "David", nodeType: .person),
        KnowledgeGraphNode(id: "session", label: "Weekly Product Training Session", nodeType: .concept),
        KnowledgeGraphNode(id: "sang", label: "sang@stably.io", nodeType: .person),
      ],
      edges: [
        KnowledgeGraphEdge(id: "david-session", sourceId: "david", targetId: "session", label: "works_on"),
        KnowledgeGraphEdge(
          id: "includes", sourceId: "session", targetId: "sang", label: "includes", memoryIds: ["m1"]),
        KnowledgeGraphEdge(id: "with", sourceId: "session", targetId: "sang", label: "with", memoryIds: ["m2"]),
      ]
    )

    let snapshot = MemoryAtlasLayoutEngine.makeSnapshot(graph: graph, userName: "David")

    let merged = try XCTUnwrap(snapshot.edgesByNodeID["session"]?.first { $0.edge.targetId == "sang" })
    XCTAssertEqual(snapshot.edgesByNodeID["session"]?.count, 2, "one merged row for david, one for sang")
    XCTAssertEqual(merged.weight, 2)
    XCTAssertEqual(Set(merged.edge.memoryIds), ["m1", "m2"], "the union of both edges' citations, not just one")
    XCTAssertEqual(snapshot.neighborIDsByNodeID["session"], ["david", "sang"])
  }

  func testParallelEdgesWithDistinctVerbsAreNotLostByTheMerge() throws {
    let graph = KnowledgeGraphResponse(
      nodes: [
        KnowledgeGraphNode(id: "session", label: "Weekly Product Training Session", nodeType: .concept),
        KnowledgeGraphNode(id: "sang", label: "sang@stably.io", nodeType: .person),
      ],
      edges: [
        KnowledgeGraphEdge(id: "includes", sourceId: "session", targetId: "sang", label: "includes"),
        KnowledgeGraphEdge(id: "with", sourceId: "session", targetId: "sang", label: "with"),
        // A duplicate verb (different casing) must not appear twice.
        KnowledgeGraphEdge(id: "includes-again", sourceId: "session", targetId: "sang", label: "Includes"),
      ]
    )

    let snapshot = MemoryAtlasLayoutEngine.makeSnapshot(graph: graph, userName: "David")
    let merged = try XCTUnwrap(snapshot.edges.first)

    XCTAssertEqual(merged.weight, 3)
    XCTAssertEqual(merged.relationshipLabels, ["includes", "with"], "case-insensitive duplicate verb is dropped")
    XCTAssertEqual(
      MemoryAtlasLayoutEngine.combinedRelationshipDisplayName(merged.relationshipLabels),
      "includes & with"
    )
  }

  func testParallelEdgeMergeIsDeterministicAcrossRepeatedSnapshots() {
    let graph = KnowledgeGraphResponse(
      nodes: [
        KnowledgeGraphNode(id: "session", label: "Session", nodeType: .concept),
        KnowledgeGraphNode(id: "sang", label: "Sang", nodeType: .person),
      ],
      edges: [
        KnowledgeGraphEdge(id: "includes", sourceId: "session", targetId: "sang", label: "includes"),
        KnowledgeGraphEdge(id: "with", sourceId: "sang", targetId: "session", label: "with"),
      ]
    )

    let first = MemoryAtlasLayoutEngine.makeSnapshot(graph: graph, userName: "David")
    let second = MemoryAtlasLayoutEngine.makeSnapshot(graph: graph, userName: "David")

    XCTAssertEqual(first.edges.map(\.id), second.edges.map(\.id))
    XCTAssertEqual(first.edges.map(\.relationshipLabels), second.edges.map(\.relationshipLabels))
    XCTAssertEqual(first.edges.map(\.weight), second.edges.map(\.weight))
    XCTAssertEqual(first.nodes.map(\.normalizedPosition), second.nodes.map(\.normalizedPosition))
  }

  func testTimelineSpansCreatedAtRangeAndCountsEveryEntity() {
    let base = Date(timeIntervalSince1970: 1_700_000_000)
    let graph = KnowledgeGraphResponse(
      nodes: [
        KnowledgeGraphNode(id: "david", label: "David", nodeType: .person, createdAt: base),
        KnowledgeGraphNode(id: "omi", label: "Omi", nodeType: .thing, createdAt: base.addingTimeInterval(86_400)),
        KnowledgeGraphNode(
          id: "openai", label: "OpenAI", nodeType: .organization, createdAt: base.addingTimeInterval(2 * 86_400)),
      ],
      edges: []
    )

    let snapshot = MemoryAtlasLayoutEngine.makeSnapshot(graph: graph, userName: "David")
    let timeline = try? XCTUnwrap(snapshot.timeline)

    XCTAssertEqual(timeline?.start, base)
    XCTAssertEqual(timeline?.end, base.addingTimeInterval(2 * 86_400))
    XCTAssertEqual(timeline?.buckets.reduce(0, +), snapshot.nodes.count)
  }

  func testTimelineSpreadsAZeroRangeImportWithoutInventingDates() throws {
    let stamp = Date(timeIntervalSince1970: 1_700_000_000)
    let graph = KnowledgeGraphResponse(
      nodes: [
        KnowledgeGraphNode(id: "david", label: "David", nodeType: .person, createdAt: stamp),
        KnowledgeGraphNode(id: "omi", label: "Omi", nodeType: .thing, createdAt: stamp),
      ],
      edges: []
    )

    let snapshot = MemoryAtlasLayoutEngine.makeSnapshot(graph: graph, userName: "David")
    let timeline = try XCTUnwrap(snapshot.timeline)

    XCTAssertFalse(timeline.hasChronologicalRange)
    XCTAssertEqual(timeline.buckets.reduce(0, +), snapshot.nodes.count)
    XCTAssertEqual(timeline.date(atFraction: 0.25), stamp)
    XCTAssertEqual(timeline.date(atFraction: 0.75), stamp)
    XCTAssertEqual(timeline.entries.map(\.playbackFraction), [0, 1])
  }

  func testDensityAwareTimelineExpandsImportedClusterButKeepsDateOrder() throws {
    let base = Date(timeIntervalSince1970: 1_700_000_000)
    let imported = (0..<24).map { index in
      KnowledgeGraphNode(
        id: String(format: "import-%02d", index),
        label: String(format: "Imported %02d", index),
        nodeType: .concept,
        createdAt: base.addingTimeInterval(86_400)
      )
    }
    let graph = KnowledgeGraphResponse(
      nodes: [
        KnowledgeGraphNode(id: "david", label: "David", nodeType: .person, createdAt: base),
        KnowledgeGraphNode(
          id: "later", label: "Later", nodeType: .organization,
          createdAt: base.addingTimeInterval(30 * 86_400)
        ),
      ] + imported,
      edges: []
    )

    let snapshot = MemoryAtlasLayoutEngine.makeSnapshot(graph: graph, userName: "David")
    let timeline = try XCTUnwrap(snapshot.timeline)
    let importedEntries = timeline.entries.filter { $0.nodeID.hasPrefix("import-") }
    let firstImportedEntry = try XCTUnwrap(importedEntries.first)
    let lastImportedEntry = try XCTUnwrap(importedEntries.last)

    XCTAssertEqual(importedEntries.map(\.createdAt), Array(repeating: base.addingTimeInterval(86_400), count: 24))
    XCTAssertGreaterThan(
      lastImportedEntry.playbackFraction - firstImportedEntry.playbackFraction,
      0.5,
      "a dense import should have room to grow during replay"
    )
    XCTAssertEqual(timeline.buckets.reduce(0, +), snapshot.nodes.count)
    XCTAssertLessThan(
      timeline.buckets.max() ?? Int.max, 8, "the histogram should not collapse the import into one burst")

    let plan = MemoryAtlasRenderPlanner.makePlan(
      snapshot: snapshot,
      viewportSize: CGSize(width: 900, height: 640),
      zoom: 1,
      pan: .zero,
      compact: false,
      selectedNodeID: nil,
      matchingNodeIDs: nil,
      timeline: timeline,
      timeCursor: 0.45
    )
    XCTAssertGreaterThan(plan.visibleNodes.count, 2)
    XCTAssertLessThan(plan.visibleNodes.count, snapshot.nodes.count)
  }

  func testTimelineIsNilForOneEntity() {
    let snapshot = MemoryAtlasLayoutEngine.makeSnapshot(
      graph: KnowledgeGraphResponse(
        nodes: [KnowledgeGraphNode(id: "david", label: "David", nodeType: .person)],
        edges: []
      ),
      userName: "David"
    )

    XCTAssertNil(snapshot.timeline)
  }

  func testDensityReplayNeverShowsAnEdgeBeforeBothEndpointsAreBorn() throws {
    let base = Date(timeIntervalSince1970: 1_700_000_000)
    let graph = KnowledgeGraphResponse(
      nodes: [
        KnowledgeGraphNode(id: "david", label: "David", nodeType: .person, createdAt: base),
        KnowledgeGraphNode(
          id: "future", label: "Future project", nodeType: .concept,
          createdAt: base.addingTimeInterval(86_400)
        ),
      ],
      edges: [
        KnowledgeGraphEdge(
          id: "future-edge", sourceId: "david", targetId: "future", label: "works_on", createdAt: base
        )
      ]
    )
    let snapshot = MemoryAtlasLayoutEngine.makeSnapshot(graph: graph, userName: "David")
    let timeline = try XCTUnwrap(snapshot.timeline)

    let earlyPlan = MemoryAtlasRenderPlanner.makePlan(
      snapshot: snapshot,
      viewportSize: CGSize(width: 800, height: 600),
      zoom: 1,
      pan: .zero,
      compact: false,
      selectedNodeID: nil,
      matchingNodeIDs: nil,
      timeline: timeline,
      timeCursor: 0
    )
    XCTAssertEqual(Set(earlyPlan.visibleNodes.map(\.id)), ["david"])
    XCTAssertTrue(earlyPlan.visibleEdges.isEmpty)

    let completePlan = MemoryAtlasRenderPlanner.makePlan(
      snapshot: snapshot,
      viewportSize: CGSize(width: 800, height: 600),
      zoom: 1,
      pan: .zero,
      compact: false,
      selectedNodeID: nil,
      matchingNodeIDs: nil,
      timeline: timeline,
      timeCursor: 1
    )
    XCTAssertEqual(Set(completePlan.visibleEdges.map(\.id)), ["future-edge"])
  }

  func testDensityReplayUsesStableIDOrderForEqualTimestamps() throws {
    let stamp = Date(timeIntervalSince1970: 1_700_000_000)
    let entities = [
      KnowledgeGraphNode(id: "zebra", label: "Zebra", nodeType: .thing, createdAt: stamp),
      KnowledgeGraphNode(id: "david", label: "David", nodeType: .person, createdAt: stamp),
      KnowledgeGraphNode(id: "alpha", label: "Alpha", nodeType: .concept, createdAt: stamp),
    ]
    let first = try XCTUnwrap(
      MemoryAtlasLayoutEngine.makeSnapshot(
        graph: KnowledgeGraphResponse(nodes: entities, edges: []), userName: "David"
      ).timeline
    )
    let second = try XCTUnwrap(
      MemoryAtlasLayoutEngine.makeSnapshot(
        graph: KnowledgeGraphResponse(nodes: Array(entities.reversed()), edges: []), userName: "David"
      ).timeline
    )

    XCTAssertEqual(first.entries.map(\.nodeID), ["alpha", "david", "zebra"])
    XCTAssertEqual(first.entries, second.entries)
  }

  func testAsOfCursorHidesEntitiesBornAfterTheCursorButKeepsAnchor() {
    let base = Date(timeIntervalSince1970: 1_700_000_000)
    let graph = KnowledgeGraphResponse(
      nodes: [
        KnowledgeGraphNode(
          id: "david", label: "David", nodeType: .person, createdAt: base.addingTimeInterval(3 * 86_400)),
        KnowledgeGraphNode(id: "early", label: "Early", nodeType: .concept, createdAt: base),
        KnowledgeGraphNode(
          id: "late", label: "Late", nodeType: .concept, createdAt: base.addingTimeInterval(2 * 86_400)),
      ],
      edges: []
    )

    let snapshot = MemoryAtlasLayoutEngine.makeSnapshot(graph: graph, userName: "David")
    let plan = MemoryAtlasRenderPlanner.makePlan(
      snapshot: snapshot,
      viewportSize: CGSize(width: 800, height: 600),
      zoom: 1,
      pan: .zero,
      compact: false,
      selectedNodeID: nil,
      matchingNodeIDs: nil,
      asOf: base.addingTimeInterval(86_400)
    )

    let ids = Set(plan.visibleNodes.map(\.id))
    XCTAssertTrue(ids.contains("early"), "entity born before the cursor is visible")
    XCTAssertFalse(ids.contains("late"), "entity born after the cursor is hidden")
    // The anchor is exempt from time filtering — "you" are always present, even
    // though David's own createdAt is after this cursor.
    XCTAssertTrue(ids.contains("david"), "anchor is always visible regardless of time cursor")
  }

  private func sampleGraph() -> KnowledgeGraphResponse {
    KnowledgeGraphResponse(
      nodes: [
        KnowledgeGraphNode(id: "david", label: "David", nodeType: .person),
        KnowledgeGraphNode(id: "omi", label: "Omi", nodeType: .thing),
        KnowledgeGraphNode(id: "openai", label: "OpenAI", nodeType: .organization),
        KnowledgeGraphNode(id: "python", label: "Python", nodeType: .thing),
      ],
      edges: [
        KnowledgeGraphEdge(id: "work", sourceId: "david", targetId: "omi", label: "works_on"),
        KnowledgeGraphEdge(id: "with", sourceId: "david", targetId: "openai", label: "works_with"),
        KnowledgeGraphEdge(id: "uses", sourceId: "david", targetId: "python", label: "uses"),
      ]
    )
  }

  func testSmallAtlasNamesEveryEntityAtOverviewZoom() {
    // Regression: the label budgets are tuned for thousands of entities. A
    // 26-entity atlas inherited "3 per cluster, 12 total" and rendered as a
    // handful of unnamed dots on an empty canvas.
    let nodes = (0..<26).map {
      KnowledgeGraphNode(id: "c\($0)", label: "Concept \($0)", nodeType: .concept)
    }
    let snapshot = MemoryAtlasLayoutEngine.makeSnapshot(
      graph: KnowledgeGraphResponse(nodes: nodes, edges: []),
      userName: "David"
    )
    let plan = MemoryAtlasRenderPlanner.makePlan(
      snapshot: snapshot,
      viewportSize: CGSize(width: 1_200, height: 800),
      zoom: 1,
      pan: .zero,
      compact: false,
      selectedNodeID: nil,
      matchingNodeIDs: nil
    )

    XCTAssertEqual(plan.detailLevel, .overview)
    // Raising the budget alone left collision admission as the new binding
    // constraint: on the real 26-entity account 10 entities still rendered as
    // anonymous dots. A name that collides below its mark now flips above
    // instead of being dropped. Two near-coincident marks can still lose one
    // name — with the dots overlapping, a second name there would be less
    // readable than none — so this asserts the anonymous tail is gone, not
    // that collision handling became perfect.
    XCTAssertGreaterThanOrEqual(plan.labelNodeIDs.count, 24)
    XCTAssertFalse(
      plan.labelAboveNodeIDs.isEmpty,
      "This layout collides below the mark, so the flip is what admits the last names")
    XCTAssertTrue(plan.labelAboveNodeIDs.isSubset(of: plan.labelNodeIDs))
  }

  func testDenseAtlasStillDropsCollidingNamesInsteadOfFlippingThem() {
    // The flip is a sparse-atlas affordance. Thousands of names never fit
    // either way, so a dense atlas must keep dropping them — otherwise the
    // label overlay grows unbounded at overview zoom.
    let nodes = (0..<400).map {
      KnowledgeGraphNode(id: "c\($0)", label: "Concept \($0)", nodeType: .concept)
    }
    let snapshot = MemoryAtlasLayoutEngine.makeSnapshot(
      graph: KnowledgeGraphResponse(nodes: nodes, edges: []),
      userName: "David"
    )
    let plan = MemoryAtlasRenderPlanner.makePlan(
      snapshot: snapshot,
      viewportSize: CGSize(width: 1_200, height: 800),
      zoom: 1,
      pan: .zero,
      compact: false,
      selectedNodeID: nil,
      matchingNodeIDs: nil
    )

    XCTAssertTrue(plan.labelAboveNodeIDs.isEmpty)
    XCTAssertLessThan(plan.labelNodeIDs.count, nodes.count)
  }

  func testSmallAtlasDrawsALargerMarkThanADenseOne() {
    let small = MemoryAtlasNodeVisualPolicy.radius(
      clusterRank: 3, zoom: 1, compact: false,
      isFullyLabelled: false, isInspect: false, isFocus: false, isSmallAtlas: true
    )
    let dense = MemoryAtlasNodeVisualPolicy.radius(
      clusterRank: 3, zoom: 1, compact: false,
      isFullyLabelled: false, isInspect: false, isFocus: false, isSmallAtlas: false
    )

    XCTAssertGreaterThan(small, dense)
    // The compact inline card must keep its own tuned scale.
    XCTAssertEqual(
      MemoryAtlasNodeVisualPolicy.radius(
        clusterRank: 3, zoom: 1, compact: true,
        isFullyLabelled: false, isInspect: false, isFocus: false, isSmallAtlas: true
      ),
      MemoryAtlasNodeVisualPolicy.radius(
        clusterRank: 3, zoom: 1, compact: true,
        isFullyLabelled: false, isInspect: false, isFocus: false, isSmallAtlas: false
      )
    )
  }

  /// STATIC CHECKER, not behavioral coverage: the timeline footer regressed by
  /// growing a flexible child, and SwiftUI gives no seam to measure a rendered
  /// subview's height from a unit test. A bare `Spacer()` inside the footer's
  /// VStack expands vertically and takes the height away from the atlas canvas
  /// — that is exactly how the bar came to fill roughly 40% of the window.
  func testStaticCheckerTimelineFooterHasNoVerticallyExpandingChild() throws {
    let source = try atlasSource()

    guard let start = source.range(of: "private var timelineBar: some View {"),
      let end = source.range(of: "private var timelineTrack: some View {")
    else {
      return XCTFail("Could not locate the timelineBar declaration")
    }
    let body = String(source[start.upperBound..<end.lowerBound])

    XCTAssertFalse(
      body.contains("Spacer()"),
      """
      A bare Spacer() in the timeline footer expands to fill and steals canvas \
      from the atlas. Use Spacer(minLength:) inside a horizontal row instead.
      """
    )
    XCTAssertTrue(
      body.contains("Spacer(minLength:"),
      "The header row should still push its trailing controls to the edge."
    )
  }

  private func atlasSource() throws -> String {
    let testsDirectory = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    let packageDirectory = testsDirectory.deletingLastPathComponent()
    let sourceURL =
      packageDirectory
      .appendingPathComponent("Sources")
      .appendingPathComponent("MainWindow")
      .appendingPathComponent("Pages")
      .appendingPathComponent("MemoryGraph")
      .appendingPathComponent("CanonicalMemoryAtlasView.swift")
    // omi-test-quality: source-inspection -- static contract: a SwiftUI subview's rendered height is not observable from a unit test, so the footer's no-flexible-child rule is asserted on source; the layout behavior itself is covered by the placement tests above.
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }

  private func fiveTypeGraph() -> KnowledgeGraphResponse {
    KnowledgeGraphResponse(
      nodes: [
        KnowledgeGraphNode(id: "david", label: "David", nodeType: .person),
        KnowledgeGraphNode(id: "casey", label: "Casey", nodeType: .person),
        KnowledgeGraphNode(id: "openai", label: "OpenAI", nodeType: .organization),
        KnowledgeGraphNode(id: "singapore", label: "Singapore", nodeType: .place),
        KnowledgeGraphNode(id: "python", label: "Python", nodeType: .thing),
        KnowledgeGraphNode(id: "strategy", label: "Strategy", nodeType: .concept),
      ],
      edges: [
        KnowledgeGraphEdge(id: "works-on", sourceId: "david", targetId: "singapore", label: "works_on"),
        KnowledgeGraphEdge(id: "works-with", sourceId: "david", targetId: "casey", label: "works_with"),
        KnowledgeGraphEdge(id: "uses", sourceId: "david", targetId: "python", label: "uses"),
      ]
    )
  }
}
