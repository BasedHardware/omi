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
    let anchor = try XCTUnwrap(first.nodeByID["david"]?.normalizedPosition)
    XCTAssertEqual(Double(anchor.x), 0.5, accuracy: 1e-9, "You are the centre of your own map")
    XCTAssertEqual(Double(anchor.y), 0.5, accuracy: 1e-9)
  }

  /// Type still decides a node's colour and which constellation it counts
  /// toward. It no longer decides where the node goes — relatedness does — so
  /// the caption follows the entities instead of marking a fixed petal.
  func testNodeTypesStillGroupEntitiesButNoLongerFixTheirPositions() throws {
    let snapshot = MemoryAtlasLayoutEngine.makeSnapshot(graph: fiveTypeGraph(), userName: "David")

    XCTAssertEqual(snapshot.nodeByID["casey"]?.cluster, .person)
    XCTAssertEqual(snapshot.nodeByID["openai"]?.cluster, .organization)
    XCTAssertEqual(snapshot.nodeByID["singapore"]?.cluster, .place)
    XCTAssertEqual(snapshot.nodeByID["python"]?.cluster, .thing)
    XCTAssertEqual(snapshot.nodeByID["strategy"]?.cluster, .concept)
    XCTAssertEqual(snapshot.activeClusters, [.person, .organization, .place, .thing, .concept])

    for cluster in snapshot.activeClusters {
      let members = snapshot.nodes.filter { $0.cluster == cluster }
      XCTAssertFalse(members.isEmpty)
      let mean = CGPoint(
        x: members.map(\.normalizedPosition.x).reduce(0, +) / CGFloat(members.count),
        y: members.map(\.normalizedPosition.y).reduce(0, +) / CGFloat(members.count))
      let caption = snapshot.center(for: cluster)
      XCTAssertEqual(Double(caption.x), Double(mean.x), accuracy: 1e-6)
      XCTAssertEqual(Double(caption.y), Double(mean.y), accuracy: 1e-6)
    }

    // A caption that still sat exactly on its old fixed petal would mean the
    // constellation had not moved with its content.
    let fixedPetals = MemoryAtlasCluster.centers(for: snapshot.activeClusters)
    let moved = snapshot.activeClusters.contains { cluster in
      guard let petal = fixedPetals[cluster] else { return false }
      let caption = snapshot.center(for: cluster)
      return hypot(caption.x - petal.x, caption.y - petal.y) > 0.01
    }
    XCTAssertTrue(moved, "Constellation captions must follow their entities, not a fixed ring")
  }

  /// `MemoryAtlasCluster.centers` survives as the weak type *field* — where a
  /// node drifts when nothing it is related to pulls harder — rather than as
  /// the position it is assigned.
  func testSingleActiveTypeFieldPullsTowardTheCentreInsteadOfTheRing() {
    let centers = MemoryAtlasCluster.centers(for: [.concept])

    XCTAssertEqual(centers.count, 1)
    XCTAssertEqual(centers[.concept], MemoryAtlasCluster.starCenter)
  }

  func testTwoOrMoreActiveTypeFieldsStillFormTheRing() {
    let centers = MemoryAtlasCluster.centers(for: [.organization, .thing])

    XCTAssertEqual(centers[.organization], CGPoint(x: 0.5, y: 0.25))
    XCTAssertEqual(centers[.thing], CGPoint(x: 0.5, y: 0.75))
  }

  func testSingleTypeAtlasActuallySpreadsAcrossTheCanvas() throws {
    let nodes = (0..<40).map {
      KnowledgeGraphNode(id: "c\($0)", label: "Concept \($0)", nodeType: .concept)
    }
    // Chained so every node but the two chain ends has two distinct
    // neighbors and stays on the phyllotaxis spiral this test exercises.
    // (An edgeless graph now makes every node an isolate, which the
    // leaf/isolate fix deliberately moves into the margin gutter instead —
    // see the isolate placement tests below.)
    let edges = (0..<39).map {
      KnowledgeGraphEdge(id: "e\($0)", sourceId: "c\($0)", targetId: "c\($0 + 1)", label: "related_to")
    }
    let snapshot = MemoryAtlasLayoutEngine.makeSnapshot(
      graph: KnowledgeGraphResponse(nodes: nodes, edges: edges),
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

  func testOnlyTypesWithEntitiesGetAConstellation() {
    let snapshot = MemoryAtlasLayoutEngine.makeSnapshot(graph: sampleGraph(), userName: "David")

    XCTAssertEqual(snapshot.activeClusters, [.organization, .thing])
    // Captions are wherever those entities settled, so the only thing that can
    // be asserted about them without restating the layout is that they are on
    // the canvas near their own kind.
    for cluster in snapshot.activeClusters {
      let caption = snapshot.center(for: cluster)
      XCTAssertTrue((0...1).contains(caption.x) && (0...1).contains(caption.y))
    }
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

  // MARK: - Leaf and isolate placement (Fix 2)

  func testDegreeOneNodeIsPlacedCloserToItsSingleNeighborThanToItsTypeClusterCenter() throws {
    let graph = KnowledgeGraphResponse(
      nodes: [
        KnowledgeGraphNode(id: "david", label: "David", nodeType: .person),
        KnowledgeGraphNode(id: "server", label: "Stably Server", nodeType: .organization),
        KnowledgeGraphNode(id: "leaf1", label: "Onboarding doc", nodeType: .concept),
        KnowledgeGraphNode(id: "leaf2", label: "Runbook", nodeType: .concept),
        KnowledgeGraphNode(id: "leaf3", label: "Postmortem", nodeType: .concept),
        KnowledgeGraphNode(id: "leaf4", label: "Design doc", nodeType: .concept),
        KnowledgeGraphNode(id: "leaf5", label: "Style guide", nodeType: .concept),
      ],
      edges: [
        KnowledgeGraphEdge(id: "david-server", sourceId: "david", targetId: "server", label: "works_at"),
        KnowledgeGraphEdge(id: "e1", sourceId: "server", targetId: "leaf1", label: "produced"),
        KnowledgeGraphEdge(id: "e2", sourceId: "server", targetId: "leaf2", label: "produced"),
        KnowledgeGraphEdge(id: "e3", sourceId: "server", targetId: "leaf3", label: "produced"),
        KnowledgeGraphEdge(id: "e4", sourceId: "server", targetId: "leaf4", label: "produced"),
        KnowledgeGraphEdge(id: "e5", sourceId: "server", targetId: "leaf5", label: "produced"),
      ]
    )

    let snapshot = MemoryAtlasLayoutEngine.makeSnapshot(graph: graph, userName: "David")
    let server = try XCTUnwrap(snapshot.nodeByID["server"])
    let david = try XCTUnwrap(snapshot.nodeByID["david"])
    XCTAssertEqual(server.degree, 6, "the anchor plus five leaves")

    func distance(_ a: CGPoint, _ b: CGPoint) -> CGFloat { hypot(a.x - b.x, a.y - b.y) }

    // Compared against the other placed entity rather than against the concept
    // constellation's centre: that centre is now the mean of these very leaves,
    // so measuring against it would be measuring against themselves.
    for leafID in ["leaf1", "leaf2", "leaf3", "leaf4", "leaf5"] {
      let leaf = try XCTUnwrap(snapshot.nodeByID[leafID])
      XCTAssertEqual(leaf.degree, 1)
      XCTAssertLessThan(
        distance(leaf.normalizedPosition, server.normalizedPosition),
        distance(leaf.normalizedPosition, david.normalizedPosition),
        "\(leafID) should read as a burr on its hub, not a peer of the anchor"
      )
      XCTAssertLessThan(
        distance(leaf.normalizedPosition, server.normalizedPosition), 0.1,
        "\(leafID) must sit against its hub, not merely nearer to it"
      )
    }
    // Fanned deterministically, not stacked on one point.
    let leafPositions = Set(
      ["leaf1", "leaf2", "leaf3", "leaf4", "leaf5"].map { id -> String in
        let position = snapshot.nodeByID[id]!.normalizedPosition
        return "\(position.x),\(position.y)"
      })
    XCTAssertEqual(leafPositions.count, 5)
  }

  func testDegreeZeroNodeIsNotPlacedInATypeSpiral() throws {
    let graph = KnowledgeGraphResponse(
      nodes: [
        KnowledgeGraphNode(id: "david", label: "David", nodeType: .person),
        KnowledgeGraphNode(id: "server", label: "Stably Server", nodeType: .organization),
        KnowledgeGraphNode(id: "orphan", label: "Untouched note", nodeType: .concept),
      ],
      edges: [
        KnowledgeGraphEdge(id: "david-server", sourceId: "david", targetId: "server", label: "works_at")
      ]
    )

    let snapshot = MemoryAtlasLayoutEngine.makeSnapshot(graph: graph, userName: "David")
    let orphan = try XCTUnwrap(snapshot.nodeByID["orphan"])

    XCTAssertEqual(orphan.degree, 0)
    // An entity with no relationships was positioned by nothing, so it belongs
    // outside the region the relaxed map occupies rather than among entities
    // whose positions do mean something.
    XCTAssertFalse(
      MemoryAtlasLayoutEngine.layoutArea.contains(orphan.normalizedPosition),
      "An unconnected entity must not sit inside the structure")
    // Still inside the existing clamp bounds.
    XCTAssertGreaterThanOrEqual(orphan.normalizedPosition.x, 0.04)
    XCTAssertLessThanOrEqual(orphan.normalizedPosition.x, 0.96)
    XCTAssertLessThanOrEqual(orphan.normalizedPosition.y, 0.92)
  }

  func testLeafAndIsolatePlacementIsDeterministicAcrossRepeatedSnapshots() {
    let graph = KnowledgeGraphResponse(
      nodes: [
        KnowledgeGraphNode(id: "david", label: "David", nodeType: .person),
        KnowledgeGraphNode(id: "server", label: "Server", nodeType: .organization),
        KnowledgeGraphNode(id: "leaf", label: "Doc", nodeType: .concept),
        KnowledgeGraphNode(id: "orphan", label: "Orphan", nodeType: .thing),
      ],
      edges: [
        KnowledgeGraphEdge(id: "david-server", sourceId: "david", targetId: "server", label: "works_at"),
        KnowledgeGraphEdge(id: "server-leaf", sourceId: "server", targetId: "leaf", label: "produced"),
      ]
    )

    let first = MemoryAtlasLayoutEngine.makeSnapshot(graph: graph, userName: "David")
    let second = MemoryAtlasLayoutEngine.makeSnapshot(graph: graph, userName: "David")

    XCTAssertEqual(first.nodes.map(\.normalizedPosition), second.nodes.map(\.normalizedPosition))
    XCTAssertEqual(first.nodeByID["leaf"]?.normalizedPosition, second.nodeByID["leaf"]?.normalizedPosition)
    XCTAssertEqual(first.nodeByID["orphan"]?.normalizedPosition, second.nodeByID["orphan"]?.normalizedPosition)
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
    // Chained so these stay spiral-placed hub nodes rather than isolates —
    // an edgeless graph is now deliberately parked in the margin gutter by
    // the leaf/isolate fix, which is a much denser packing than this
    // collision-budget regression was written to exercise.
    let edges = (0..<25).map {
      KnowledgeGraphEdge(id: "e\($0)", sourceId: "c\($0)", targetId: "c\($0 + 1)", label: "related_to")
    }
    let snapshot = MemoryAtlasLayoutEngine.makeSnapshot(
      graph: KnowledgeGraphResponse(nodes: nodes, edges: edges),
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
    // The flip-above affordance used to be load-bearing here: the old layout
    // placed marks close enough that names collided below them, and flipping
    // was the only way the last few were admitted. Marks in a small atlas are
    // now spaced for legibility before the planner ever sees them, so this
    // fixture no longer collides and no longer needs the flip. It is still an
    // invariant that anything flipped is also labelled.
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
