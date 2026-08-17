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

  func testCanonicalSelfNodeWinsOverAWellConnectedPersonAndAbsorbsSelfAliases() throws {
    let graph = KnowledgeGraphResponse(
      nodes: [
        KnowledgeGraphNode(id: "user", label: "The User", nodeType: .concept),
        KnowledgeGraphNode(id: "self-alias", label: "the user", nodeType: .person),
        KnowledgeGraphNode(id: "chi", label: "Chi", nodeType: .person),
        KnowledgeGraphNode(id: "project", label: "Omi", nodeType: .thing),
      ],
      edges: [
        KnowledgeGraphEdge(id: "self-project", sourceId: "user", targetId: "project", label: "uses"),
        KnowledgeGraphEdge(id: "alias-project", sourceId: "self-alias", targetId: "project", label: "uses"),
        KnowledgeGraphEdge(id: "chi-project", sourceId: "chi", targetId: "project", label: "works_on"),
        KnowledgeGraphEdge(id: "chi-1", sourceId: "chi", targetId: "project", label: "mentions"),
      ])

    let snapshot = MemoryAtlasLayoutEngine.makeSnapshot(graph: graph, userName: "David")

    XCTAssertEqual(snapshot.anchorNodeID, "user")
    XCTAssertEqual(snapshot.nodeByID["user"]?.node.label, "David")
    XCTAssertNil(snapshot.nodeByID["self-alias"], "There must be one self node, not a separate 'the user' group")
    XCTAssertEqual(snapshot.nodeByID["user"]?.normalizedPosition, MemoryAtlasCluster.starCenter)
  }

  func testAccountNameOnNonPersonCannotReplaceTheAccountHolder() throws {
    let graph = KnowledgeGraphResponse(
      nodes: [
        KnowledgeGraphNode(id: "user", label: "The User", nodeType: .concept),
        KnowledgeGraphNode(id: "named-memory", label: "David", nodeType: .concept),
      ],
      edges: []
    )

    let snapshot = MemoryAtlasLayoutEngine.makeSnapshot(graph: graph, userName: "David")

    XCTAssertEqual(snapshot.anchorNodeID, "user")
    XCTAssertEqual(snapshot.nodeByID["user"]?.node.label, "David")
  }

  func testSyntheticAuthenticatedOwnerCentersCatalogOnlyAtlasWithoutEdges() throws {
    let graph = KnowledgeGraphResponse(
      nodes: [],
      edges: [],
      catalogNodes: [KnowledgeGraphNode(id: "memory:one", label: "A memory", nodeType: .concept)]
    )

    let snapshot = MemoryAtlasLayoutEngine.makeSnapshot(graph: graph, userName: "David")

    XCTAssertEqual(snapshot.anchorNodeID, "atlas-owner")
    XCTAssertEqual(snapshot.nodeByID["atlas-owner"]?.node.label, "David")
    XCTAssertEqual(snapshot.nodeByID["atlas-owner"]?.normalizedPosition, MemoryAtlasCluster.starCenter)
    XCTAssertTrue(snapshot.edges.isEmpty)
  }

  func testCatalogNodesEnterAtlasAsNeutralUnconnectedMarks() throws {
    let assertionNodes = [
      KnowledgeGraphNode(id: "david", label: "David", nodeType: .person),
      KnowledgeGraphNode(id: "memory:semantic-entity", label: "Omi", nodeType: .thing),
    ]
    let catalogNode = KnowledgeGraphNode(
      id: "canonical-record",
      label: "A durable memory that has no assertion",
      nodeType: .concept)
    let response = KnowledgeGraphResponse(
      nodes: assertionNodes,
      edges: [KnowledgeGraphEdge(id: "uses", sourceId: "david", targetId: "memory:semantic-entity", label: "uses")],
      catalogNodes: [catalogNode])

    let snapshot = MemoryAtlasLayoutEngine.makeSnapshot(graph: response, userName: "David")

    XCTAssertEqual(response.catalogNodes?.map(\.id), ["canonical-record"])
    XCTAssertEqual(snapshot.nodes.map(\.id), ["david", "memory:semantic-entity", catalogNode.id])
    XCTAssertEqual(snapshot.nodeByID["memory:semantic-entity"]?.isCatalog, false)
    XCTAssertEqual(snapshot.nodeByID[catalogNode.id]?.cluster, nil)
    XCTAssertEqual(snapshot.nodeByID[catalogNode.id]?.degree, 0)
    XCTAssertEqual(snapshot.nodeByID[catalogNode.id]?.isCatalog, true)
    XCTAssertNotEqual(snapshot.nodeByID[catalogNode.id]?.clusterRank, 0)
    XCTAssertEqual(snapshot.edges.count, 1)
  }

  func testCatalogSearchMatchesWinTheirTierWithoutIDPrefixCoupling() {
    let catalogMatch = MemoryAtlasNodePlacement(
      node: KnowledgeGraphNode(id: "canonical-record", label: "Matching memory", nodeType: .concept),
      cluster: nil,
      normalizedPosition: .zero,
      degree: 0,
      clusterRank: 1,
      isCatalog: true)
    let semantic = (0..<10).map { index in
      MemoryAtlasNodePlacement(
        node: KnowledgeGraphNode(id: "entity-\(index)", label: "Matching entity \(index)", nodeType: .concept),
        cluster: .concept,
        normalizedPosition: .zero,
        degree: 1,
        clusterRank: index,
        isCatalog: false)
    }

    let selected = MemoryAtlasRenderPlanner.fairPrefix(
      semantic + [catalogMatch], limit: 4, prioritizeCatalog: true)

    XCTAssertTrue(selected.contains(where: { $0.id == catalogMatch.id }))
    XCTAssertEqual(selected.first?.id, catalogMatch.id)
  }

  func testProjectionCarriesCatalogNodesIntoTheAtlasPresentation() {
    let catalogNode = KnowledgeGraphNode(
      id: "memory:catalog",
      label: "Catalog memory",
      nodeType: .concept)
    let response = KnowledgeGraphResponse(
      nodes: [KnowledgeGraphNode(id: "entity", label: "Entity", nodeType: .concept)],
      edges: [],
      catalogNodes: [catalogNode])

    let projection = MemoryAtlasProjection(graph: response, userName: nil)

    XCTAssertEqual(projection.graph.catalogNodes?.map(\.id), [catalogNode.id])
    XCTAssertEqual(projection.snapshot.nodes.map(\.id), ["entity", catalogNode.id])
    XCTAssertNil(projection.snapshot.nodeByID[catalogNode.id]?.cluster)
  }

  func testCatalogOnlyAtlasIsStableAndDoesNotCreateEdgesOrClusters() {
    let catalog = (0..<600).map {
      KnowledgeGraphNode(id: "memory:\($0)", label: "Canonical memory \($0)", nodeType: .concept)
    }
    let response = KnowledgeGraphResponse(nodes: [], edges: [], catalogNodes: catalog)

    let first = MemoryAtlasLayoutEngine.makeSnapshot(graph: response, userName: "David")
    let second = MemoryAtlasLayoutEngine.makeSnapshot(graph: response, userName: "David")

    XCTAssertEqual(first.nodes.count, catalog.count + 1, "The authenticated owner remains the visual center")
    XCTAssertEqual(first.anchorNodeID, "atlas-owner")
    XCTAssertTrue(first.nodes.allSatisfy { $0.cluster == nil && $0.degree == 0 })
    XCTAssertTrue(first.edges.isEmpty)
    XCTAssertTrue(first.activeClusters.isEmpty)
    XCTAssertEqual(first.nodes.map(\.normalizedPosition), second.nodes.map(\.normalizedPosition))
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
    // A high-density graph uses the expanded circular canvas instead of the
    // former inset square, while remaining in normalized bounds.
    XCTAssertGreaterThanOrEqual(ys.min() ?? 0, 0)
    XCTAssertLessThanOrEqual(ys.max() ?? 1, 1)
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
    let leafPositions = try Set(
      ["leaf1", "leaf2", "leaf3", "leaf4", "leaf5"].map { id -> String in
        let position = try XCTUnwrap(snapshot.nodeByID[id]).normalizedPosition
        return "\(position.x),\(position.y)"
      })
    XCTAssertEqual(leafPositions.count, 5)
  }

  func testDegreeZeroNodeCanFillThePeripheralFieldWithoutObscuringTheOwner() throws {
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
    let david = try XCTUnwrap(snapshot.nodeByID["david"])
    XCTAssertGreaterThan(
      hypot(
        orphan.normalizedPosition.x - david.normalizedPosition.x,
        orphan.normalizedPosition.y - david.normalizedPosition.y),
      0.05,
      "A neutral mark must not obscure the account holder")
    // Isolates fill a circular peripheral field, not a rectangular rim.
    XCTAssertLessThanOrEqual(
      hypot(orphan.normalizedPosition.x - 0.5, orphan.normalizedPosition.y - 0.5),
      0.44 + 0.000_001)
  }

  func testDisconnectedIslandSeatsDoNotStack() {
    let groups = (0..<18).map { ["island-\($0)"] }
    let positions = MemoryAtlasForceLayout.haloPositions(groups: groups, area: CGRect(x: 0, y: 0, width: 1, height: 1))
    let seats = groups.compactMap { positions[$0[0]] }

    XCTAssertEqual(seats.count, groups.count)
    for index in seats.indices {
      for otherIndex in seats.indices where otherIndex > index {
        XCTAssertGreaterThan(
          hypot(seats[index].x - seats[otherIndex].x, seats[index].y - seats[otherIndex].y),
          0.049,
          "Disconnected island seats must not overlap")
      }
    }
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

  // MARK: - The account holder's own connections

  /// Everything is connected to the account holder, so drawing those lines like
  /// any other relationship puts a few hundred straight spokes across every
  /// neighbourhood and the map reads as a star regardless of where its entities
  /// sit. They recede — except when the account holder is what is selected,
  /// where "what am I connected to" is precisely the question being asked.
  func testTheAccountHoldersConnectionsRecedeUntilTheyAreTheSubject() {
    let recede = MemoryAtlasLayoutEngine.anchorConnectionsRecede

    XCTAssertTrue(recede("david", nil), "Nothing selected: the map is being read as a whole")
    XCTAssertTrue(recede("david", "singapore"), "Someone else selected: still not the subject")
    XCTAssertFalse(recede("david", "david"), "Selecting yourself must show your connections")
    XCTAssertFalse(recede(nil, "singapore"), "No account holder, no spokes to hold back")
  }

  // MARK: - Neighbourhoods the map can name

  /// A region is described by an entity actually in it, and by nothing else.
  ///
  /// The alternative — asking a model to title the group — produces "Career" or
  /// "Family": confident, unfalsifiable, and wrong in a way the user has no way
  /// to check. Naming its strongest member states exactly what the algorithm
  /// did, and is wrong visibly or not at all.
  ///
  /// One name rather than three. A place on a map is a landmark you either
  /// recognise or zoom into; a list took longer to read than the dots it sat
  /// over, and truncated into things like "ORACLE ACCESS · CONSULT-ORACLE ·
  /// DAVI…" that named nothing at all.
  func testARegionIsNamedAfterItsMostConnectedMembers() throws {
    let members = ["codex", "github", "omi", "swift", "xcode", "pr", "ci", "linter"]
    var nodes = members.map { KnowledgeGraphNode(id: $0, label: $0.capitalized, nodeType: .thing) }
    nodes.append(KnowledgeGraphNode(id: "david", label: "David", nodeType: .person))
    // Codex and GitHub touch everything in the group; Linter touches one thing.
    var edges: [KnowledgeGraphEdge] = []
    for (index, member) in members.enumerated() where member != "codex" {
      edges.append(
        KnowledgeGraphEdge(id: "c\(index)", sourceId: "codex", targetId: member, label: "uses"))
    }
    for (index, member) in members.enumerated() where !["codex", "github"].contains(member) {
      edges.append(
        KnowledgeGraphEdge(id: "g\(index)", sourceId: "github", targetId: member, label: "hosts"))
    }

    let snapshot = MemoryAtlasLayoutEngine.makeSnapshot(
      graph: KnowledgeGraphResponse(nodes: nodes, edges: edges), userName: "David")
    let region = try XCTUnwrap(snapshot.neighbourhoods.first)

    XCTAssertEqual(region.caption, "Codex", "Got: \(region.caption)")
    XCTAssertFalse(region.caption.contains("David"), "A region must not be named after you")
  }

  /// The extractor does not only mint names. It also mints entities whose
  /// label is a whole sentence — a calendar invite's subject line, a GitHub
  /// issue title with its quotes intact — and on the real account those were
  /// frequently a region's best-connected members. Taken literally, one of them
  /// produced a caption 1,200 points wide that lay across a quarter of the map
  /// and named nothing.
  func testARegionPrefersNamesOverSentencesWhenDescribingItself() {
    let sentence =
      "Calendar event — Immunefi Alpha Night with FailSafe, Sigma Prime, ChainPatrol and Halborn"
    let ranked = [
      placement(label: sentence, degree: 40),
      placement(label: "Singapore", degree: 20),
      placement(label: "TOKEN2049", degree: 18),
      placement(label: "Immunefi", degree: 4),
    ]

    let caption = MemoryAtlasLayoutEngine.caption(from: ranked, count: 3)

    XCTAssertEqual(caption, "Singapore · TOKEN2049 · Immunefi")
    XCTAssertFalse(caption.contains(sentence))
  }

  /// A region can be made entirely of sentences, and it still has to be
  /// nameable — dropping it would silently remove the region rather than
  /// describe it badly.
  func testARegionWithOnlySentencesIsStillNamedShortly() {
    let ranked = (0..<3).map {
      placement(label: "GitHub issue titled “Windows desktop crash \($0)”", degree: 10 - $0)
    }

    let caption = MemoryAtlasLayoutEngine.caption(from: ranked, count: 3)

    XCTAssertEqual(caption.components(separatedBy: " · ").count, 3)
    for part in caption.components(separatedBy: " · ") {
      XCTAssertLessThanOrEqual(part.count, MemoryAtlasLayoutEngine.captionNameCeiling)
      XCTAssertTrue(part.hasSuffix("…"), "A cut sentence must show that it was cut")
    }
  }

  /// A modularity pass on a real account emits a long tail of two- and
  /// three-entity groups. Captioning those buries the handful of regions that
  /// mean something under a field of labels for nothing.
  func testTinyGroupsAreNotDrawnAsRegions() {
    // Twelve unrelated pairs: twelve groups, none of them a place.
    var nodes: [KnowledgeGraphNode] = []
    var edges: [KnowledgeGraphEdge] = []
    for index in 0..<12 {
      nodes.append(KnowledgeGraphNode(id: "a\(index)", label: "A\(index)", nodeType: .concept))
      nodes.append(KnowledgeGraphNode(id: "b\(index)", label: "B\(index)", nodeType: .concept))
      edges.append(
        KnowledgeGraphEdge(id: "e\(index)", sourceId: "a\(index)", targetId: "b\(index)", label: "with"))
    }

    let snapshot = MemoryAtlasLayoutEngine.makeSnapshot(
      graph: KnowledgeGraphResponse(nodes: nodes, edges: edges), userName: nil)

    XCTAssertTrue(
      snapshot.neighbourhoods.isEmpty,
      "Twenty-four entities in pairs have no neighbourhoods, and saying otherwise is noise")
  }

  /// Territories survive zooming in, and give way only to a more specific
  /// question.
  ///
  /// They used to stop at neighbourhood zoom, on the theory that close up the
  /// entities speak for themselves. What that actually did was delete the
  /// island a person had just decided to look at, at the moment they looked at
  /// it — and take its name with it, so there was no longer anything on screen
  /// saying where they were. Only picking one entity, or reading every label at
  /// inspect zoom, replaces the question territories answer.
  func testRegionNamesGiveWayToWhateverTheUserIsActuallyLookingAt() {
    let visible = MemoryAtlasNeighbourhoodLabels.areVisible

    XCTAssertTrue(visible(.overview, false, false))
    XCTAssertTrue(visible(.neighborhood, false, false))
    XCTAssertTrue(visible(.detail, false, false), "Zooming into a place must not delete the place")
    XCTAssertTrue(visible(.focus, false, false))
    XCTAssertFalse(
      visible(.inspect, false, false), "Every entity is named here; a region name is noise")
    XCTAssertFalse(visible(.overview, true, false), "A selection is a more specific question")
  }

  /// The place you went into is still there once you start looking inside it.
  ///
  /// Both of these erased it. Zooming past inspect took the island and its name
  /// with it, and picking any entity did the same — so the two things a person
  /// does immediately after arriving somewhere both removed the only thing on
  /// screen saying where they had arrived. Inside a place the island is the
  /// frame, not a competing answer.
  func testThePlaceYouAreInsideOutlastsLookingAroundInsideIt() {
    let visible = MemoryAtlasNeighbourhoodLabels.areVisible

    XCTAssertTrue(visible(.inspect, false, true), "Zooming right in must not delete the island")
    XCTAssertTrue(
      visible(.overview, true, true), "Selecting an entity on the island must not delete it")
    XCTAssertTrue(visible(.inspect, true, true), "Nor both at once")
  }

  /// Going into a place must not immediately count as having left it.
  ///
  /// The rule for leaving used to be a fixed zoom, which quietly made big
  /// islands unenterable: a region that fills half the map is framed at barely
  /// more than 1×, below the threshold, so the camera arrived and the mode
  /// ended in the same frame. Whether the user has zoomed back out is a
  /// question about where they started, not about a constant.
  func testGoingIntoABigPlaceDoesNotCountAsLeavingIt() throws {
    let departure = MemoryAtlasNeighbourhoodLabels.departureZoom

    // A region filling most of the map: entering barely zooms at all.
    let wide = MemoryAtlasNeighbourhoodLabels.entering(
      center: CGPoint(x: 0.5, y: 0.5), radius: 0.3, viewport: CGSize(width: 900, height: 700),
      zoomRange: 0.6...12)
    XCTAssertLessThan(
      wide.zoom, MemoryAtlasZoomPolicy.neighborhoodZoom,
      "Fixture check: this is the case a fixed threshold got wrong")
    XCTAssertGreaterThan(
      wide.zoom,
      try XCTUnwrap(departure(wide.zoom, MemoryAtlasZoomPolicy.neighborhoodZoom, 0.6)),
      "Arriving somewhere must never already be below the zoom that leaves it")

    // A small region, entered at deep zoom: pulling back a little to see the
    // surroundings is still being there, and pulling back to the whole map is
    // not.
    let tight = MemoryAtlasNeighbourhoodLabels.entering(
      center: CGPoint(x: 0.3, y: 0.6), radius: 0.05, viewport: CGSize(width: 900, height: 700),
      zoomRange: 0.6...12)
    let floor = try XCTUnwrap(
      departure(tight.zoom, MemoryAtlasZoomPolicy.neighborhoodZoom, 0.6))
    XCTAssertGreaterThan(tight.zoom * 0.9, floor, "A small pull-back is not an exit")
    XCTAssertLessThan(CGFloat(1), floor, "Zooming back out to the whole map is")
  }

  /// Escape that clears a selection and homes the camera must not also spend
  /// the neighbourhood layer. The original departure floor treats zoom 1 as
  /// leaving; the overview rebind sits at or below that camera so the island
  /// stays until the next press, while a later pinch-out can still exit.
  func testOverviewResetDoesNotSpendTheNeighbourhoodLayer() throws {
    let minimum = MemoryAtlasZoomPolicy.minimumZoom
    let neighbourhood = MemoryAtlasZoomPolicy.neighborhoodZoom
    let entered = MemoryAtlasNeighbourhoodLabels.entering(
      center: CGPoint(x: 0.3, y: 0.6), radius: 0.05,
      viewport: CGSize(width: 900, height: 700),
      zoomRange: minimum...12)
    let original = try XCTUnwrap(
      MemoryAtlasNeighbourhoodLabels.departureZoom(
        enteredAt: entered.zoom, neighbourhoodZoom: neighbourhood, minimumZoom: minimum))
    XCTAssertLessThan(CGFloat(1), original, "Fixture: the original floor treats overview as leaving")

    let rebound = try XCTUnwrap(
      MemoryAtlasNeighbourhoodLabels.overviewDepartureZoom(
        neighbourhoodZoom: neighbourhood, minimumZoom: minimum))
    XCTAssertGreaterThanOrEqual(
      CGFloat(1), rebound, "Homed camera after clearing a selection must not count as leaving")
    XCTAssertGreaterThan(rebound, minimum, "A later pinch-out can still leave")
  }

  /// A place entered without moving the camera has no zoom-out exit, and the
  /// map must say so rather than set one nobody can reach.
  ///
  /// A region large enough to fill the map is framed at the minimum zoom. The
  /// departure threshold then lands *below* the minimum, so no amount of
  /// zooming out ever crosses it — the exit looks like it exists and does
  /// nothing. Reporting no threshold at all is what leaves Escape and the
  /// caption as the honest ways out.
  func testAPlaceThatFillsTheMapHasNoZoomOutExitToOffer() {
    let departure = MemoryAtlasNeighbourhoodLabels.departureZoom
    let minimum = MemoryAtlasZoomPolicy.minimumZoom

    let wholeMap = MemoryAtlasNeighbourhoodLabels.entering(
      center: CGPoint(x: 0.5, y: 0.5), radius: 0.45, viewport: CGSize(width: 900, height: 700),
      zoomRange: minimum...12)
    XCTAssertEqual(wholeMap.zoom, minimum, "Fixture check: this region is framed at the floor")
    XCTAssertNil(
      departure(wholeMap.zoom, MemoryAtlasZoomPolicy.neighborhoodZoom, minimum),
      "A threshold under the minimum zoom can never be crossed; do not pretend to offer one")

    let ordinary = MemoryAtlasNeighbourhoodLabels.entering(
      center: CGPoint(x: 0.5, y: 0.5), radius: 0.1, viewport: CGSize(width: 900, height: 700),
      zoomRange: minimum...12)
    XCTAssertNotNil(
      departure(ordinary.zoom, MemoryAtlasZoomPolicy.neighborhoodZoom, minimum),
      "An ordinary island still leaves when the user zooms back out")
  }

  /// Escape undoes one thing per press, innermost first, and stops eating the
  /// key once there is nothing of the map's left to undo.
  ///
  /// The layering is the point. One press used to drop the search and the
  /// selection together — two decisions for one keystroke — while the
  /// neighbourhood the user had gone into had no keyboard exit at all. And
  /// because the map consumed every Escape whether or not it used one, the
  /// Brain Map was a page you could only leave with the mouse.
  func testEscapeUndoesOneThingAtATimeFromTheInsideOut() {
    let next = MemoryAtlasDismissal.next

    XCTAssertEqual(
      next(true, true, false, true), .search, "The search field is the innermost thing to leave")
    XCTAssertEqual(
      next(false, true, false, true), .selection,
      "With the search gone, the selection goes before the place it was made in")
    XCTAssertEqual(
      next(false, false, false, true), .neighbourhood,
      "An island is left the same way a node is deselected")
    XCTAssertEqual(
      next(false, false, false, false), .passThrough,
      "A map with nothing to undo must hand the key to the page around it")
  }

  /// A walk five relationships deep is five things the user did, so Escape
  /// undoes them one at a time.
  ///
  /// Clearing the whole trail on one press is the same mistake as clearing the
  /// search and the selection together: it throws away decisions nobody asked
  /// to undo, and it is worse here because the trail is the only record of how
  /// the user got where they are.
  func testEscapeWalksBackAlongTheTrailBeforeDroppingTheSelection() {
    let next = MemoryAtlasDismissal.next

    XCTAssertEqual(
      next(false, true, true, false), .selectionStep,
      "Followed a connection to get here, so Escape goes back one connection")
    XCTAssertEqual(
      next(false, true, false, false), .selection,
      "The first entity on the walk has nothing behind it but the map")
    XCTAssertEqual(
      next(true, true, true, true), .search,
      "The search field still comes first, trail or no trail")
  }

  /// Two region names on top of each other name nothing, and a name for a
  /// region that has been panned off the map names nothing the user can see.
  ///
  /// Regions on a real account mostly overlap near the middle, so a caption
  /// that cannot have its first choice takes another spot on its own territory
  /// rather than going unnamed — but never one that is already spoken for.
  /// A region's outline is a claim about a border, and the map now draws one
  /// around every region — so the shape has to earn it rather than a threshold
  /// deciding after the fact which claims to make.
  ///
  /// Territory is awarded per patch of canvas to whichever neighbourhood is
  /// most present there, and only when it is clearly ahead of the runner-up.
  /// Two consequences are the whole reason for that design, and this is what
  /// checks they hold: no two territories can claim the same ground, and the
  /// ground a territory does claim is mostly its own. The ellipse this replaced
  /// could satisfy neither — two of them overlapped freely, and a sprawling
  /// group's disc was mostly other people's entities.
  func testEveryTerritoryTheMapDrawsIsItsOwnAndNobodyElsesToo() {
    var nodes: [KnowledgeGraphNode] = []
    var edges: [KnowledgeGraphEdge] = []
    // One group that only ever meets itself, and two that are thoroughly mixed
    // through each other.
    for (group, prefix) in [(0, "tight"), (1, "mixedA"), (2, "mixedB")] {
      for index in 0..<10 {
        nodes.append(
          KnowledgeGraphNode(
            id: "\(prefix)\(index)", label: "\(prefix) \(index)", nodeType: .concept))
        if index > 0 {
          edges.append(
            KnowledgeGraphEdge(
              id: "\(prefix)e\(index)", sourceId: "\(prefix)0", targetId: "\(prefix)\(index)",
              label: "related_to"))
        }
      }
      _ = group
    }
    for index in 0..<9 {
      edges.append(
        KnowledgeGraphEdge(
          id: "cross\(index)", sourceId: "mixedA\(index)", targetId: "mixedB\(index)",
          label: "related_to"))
    }

    let snapshot = MemoryAtlasLayoutEngine.makeSnapshot(
      graph: KnowledgeGraphResponse(nodes: nodes, edges: edges), userName: "David")

    XCTAssertFalse(snapshot.neighbourhoods.isEmpty, "The fixture has groups to find")
    for region in snapshot.neighbourhoods {
      XCTAssertFalse(region.coastline.isEmpty, "\(region.caption) is drawn, so it holds ground")
      XCTAssertGreaterThan(
        region.purity, 0.5,
        "\(region.caption) is outlined, so its ground is mostly its own")
    }

    // Sampled on a grid rather than at the entities, because the claim is about
    // the canvas: a point of empty map may belong to at most one territory.
    for step in 0..<(60 * 60) {
      let probe = CGPoint(x: CGFloat(step % 60) / 59, y: CGFloat(step / 60) / 59)
      let owners = snapshot.neighbourhoods
        .filter { memoryAtlasCoastlineContains($0.coastline, probe) }
        .map(\.caption)
      XCTAssertLessThanOrEqual(owners.count, 1, "\(probe) is claimed by \(owners)")
    }
  }

  /// A square of coast around a point, in normalized map coordinates.
  private func territory(at center: CGPoint, half: CGFloat = 0.08) -> [CGPoint] {
    [
      CGPoint(x: center.x - half, y: center.y - half),
      CGPoint(x: center.x + half, y: center.y - half),
      CGPoint(x: center.x + half, y: center.y + half),
      CGPoint(x: center.x - half, y: center.y + half),
    ]
  }

  private func region(_ id: Int, _ caption: String, _ coastline: [[CGPoint]])
    -> MemoryAtlasNeighbourhood
  {
    MemoryAtlasNeighbourhood(
      id: id, memberIDs: ["m"], caption: caption, center: CGPoint(x: 0.5, y: 0.5), radius: 0.1,
      coastline: coastline, purity: 1)
  }

  func testRegionNamesNeverOverlapAndNeverLeaveTheCanvas() {
    let size = CGSize(width: 800, height: 600)
    let project = { (point: CGPoint) in CGPoint(x: point.x * size.width, y: point.y * size.height) }
    let regions =
      (0..<3).map { region($0, "Region \($0)", [territory(at: CGPoint(x: 0.5, y: 0.5))]) }
      + [region(9, "Far away", [territory(at: CGPoint(x: 14, y: 14))])]
    let taken = CGRect(x: 340, y: 380, width: 120, height: 20)

    let placed = MemoryAtlasNeighbourhoodLabels.place(
      MemoryAtlasNeighbourhoodLabels.islands(regions, in: size, project: project),
      captions: Dictionary(lastWriteWins: regions.map { ($0.id, $0.caption) }),
      in: size,
      avoiding: [taken])

    XCTAssertFalse(
      placed.contains { $0.regionID == 9 }, "A region off the canvas has nothing to name")
    for rect in placed.map(\.rect) {
      XCTAssertTrue(CGRect(origin: .zero, size: size).contains(rect))
      XCTAssertFalse(rect.intersects(taken), "An entity's own name is not negotiable")
    }
    for (index, one) in placed.enumerated() {
      for other in placed.dropFirst(index + 1) {
        XCTAssertFalse(one.rect.intersects(other.rect), "\(one.caption) over \(other.caption)")
      }
    }
  }

  /// Eight territories is already more than anyone holds at a glance, and the
  /// budget has to hold whatever the modularity pass emits.
  func testTheMapNamesAtMostAHandfulOfRegions() {
    let size = CGSize(width: 4000, height: 600)
    let many = (0..<40).map { index in
      region(index, "R\(index)", [territory(at: CGPoint(x: 0.02 + 0.024 * CGFloat(index), y: 0.5))])
    }

    let placed = MemoryAtlasNeighbourhoodLabels.place(
      MemoryAtlasNeighbourhoodLabels.islands(
        many, in: size, project: { CGPoint(x: $0.x * size.width, y: $0.y * size.height) }),
      captions: Dictionary(lastWriteWins: many.map { ($0.id, $0.caption) }),
      in: size)

    XCTAssertEqual(placed.count, MemoryAtlasNeighbourhoodLabels.limit)
  }

  /// The map draws exactly the islands it can name, so an island it fails to
  /// name is one it does not draw.
  ///
  /// The failure this replaces was visible on a real account: a group holding
  /// two pieces of ground got one caption, and the other piece was outlined,
  /// filled, and anonymous — a shape with nothing anywhere near it saying what
  /// it was.
  func testAnIslandTheMapCannotNameIsNotAnIslandTheMapDraws() {
    let size = CGSize(width: 900, height: 700)
    let project = { (point: CGPoint) in CGPoint(x: point.x * size.width, y: point.y * size.height) }
    // One region, two separate pieces of ground.
    let split = region(
      3, "Split",
      [territory(at: CGPoint(x: 0.25, y: 0.5)), territory(at: CGPoint(x: 0.75, y: 0.5))])

    let islands = MemoryAtlasNeighbourhoodLabels.islands([split], in: size, project: project)
    XCTAssertEqual(islands.count, 2, "Both pieces are on screen")

    let named = MemoryAtlasNeighbourhoodLabels.place(
      islands, captions: [3: "Split"], in: size)
    XCTAssertEqual(named.count, 2, "So both get named")
    XCTAssertEqual(Set(named.map(\.index)), [0, 1], "One caption each, not one for the pair")

    // And with no caption to give, neither is drawn.
    XCTAssertTrue(MemoryAtlasNeighbourhoodLabels.place(islands, captions: [:], in: size).isEmpty)
  }

  /// Going into a place always leaves you looking at that place, named.
  ///
  /// At overview the map is choosing which territories to show, and skipping
  /// one whose caption will not fit is right. Once the user has picked one it
  /// is not: the island they asked for was dropped because its name collided
  /// with an entity label, leaving them zoomed into a blank canvas.
  func testThePlaceYouWentIntoIsAlwaysDrawnAndAlwaysNamed() {
    let size = CGSize(width: 900, height: 700)
    let project = { (point: CGPoint) in CGPoint(x: point.x * size.width, y: point.y * size.height) }
    let one = region(4, "Somewhere", [territory(at: CGPoint(x: 0.5, y: 0.5), half: 0.05)])
    let islands = MemoryAtlasNeighbourhoodLabels.islands([one], in: size, project: project)
    // Every candidate spot buried under entity names.
    let blanketed = (0..<24).flatMap { row in
      (0..<24).map { column in
        CGRect(x: CGFloat(column) * 40, y: CGFloat(row) * 30, width: 40, height: 30)
      }
    }

    XCTAssertTrue(
      MemoryAtlasNeighbourhoodLabels.place(
        islands, captions: [4: "Somewhere"], in: size, avoiding: blanketed
      ).isEmpty,
      "At overview a name that cannot be placed means the island is not drawn")

    let insisted = MemoryAtlasNeighbourhoodLabels.place(
      islands, captions: [4: "Somewhere"], in: size, avoiding: blanketed, insisting: true)
    XCTAssertEqual(insisted.count, 1, "Inside a place, it is drawn regardless")
    XCTAssertTrue(CGRect(origin: .zero, size: size).contains(insisted[0].rect))
  }

  /// Zooming into an island must not make it nameless.
  ///
  /// Once the camera is inside a territory its true centre is off the canvas,
  /// and a caption anchored there lands outside the viewport and is dropped —
  /// which took the island down with it, so zooming in on a place made the
  /// place disappear.
  func testAnIslandTheCameraIsInsideIsStillNamed() {
    let size = CGSize(width: 900, height: 700)
    // Projected so the island spans far beyond the viewport in every direction.
    let huge = region(1, "Everything", [territory(at: CGPoint(x: 0.5, y: 0.5), half: 0.4)])
    let zoomed = { (point: CGPoint) in
      CGPoint(
        x: (point.x - 0.5) * 8 * size.width + size.width / 2,
        y: (point.y - 0.5) * 8 * size.height + size.height / 2)
    }

    let islands = MemoryAtlasNeighbourhoodLabels.islands([huge], in: size, project: zoomed)
    XCTAssertEqual(islands.count, 1, "The island still overlaps the viewport")

    let named = MemoryAtlasNeighbourhoodLabels.place(islands, captions: [1: "Everything"], in: size)
    XCTAssertEqual(named.count, 1, "So it is still named")
    XCTAssertTrue(CGRect(origin: .zero, size: size).contains(named[0].rect))
  }

  /// Only a few dozen lines fit on the map at overview zoom, and they used to
  /// all be the account holder's.
  ///
  /// The anchor's rank is zero, so every edge touching it led the draw order.
  /// On the real account that meant the entire budget went to "David is
  /// connected to this" — a hundred copies of the one fact the user already
  /// knows — while the map reported 1,377 connections and drew no relationship
  /// between any two other entities. Those are the only ones that can tell them
  /// something they did not already know.
  func testTheDrawnConnectionsAreNotAllYourOwn() throws {
    var nodes = [KnowledgeGraphNode(id: "david", label: "David", nodeType: .person)]
    var edges: [KnowledgeGraphEdge] = []
    for index in 0..<12 {
      nodes.append(KnowledgeGraphNode(id: "e\(index)", label: "E\(index)", nodeType: .thing))
      edges.append(
        KnowledgeGraphEdge(id: "me\(index)", sourceId: "david", targetId: "e\(index)", label: "uses"))
    }
    // Two entities related to each other, and to nothing prominent.
    edges.append(KnowledgeGraphEdge(id: "pair", sourceId: "e0", targetId: "e1", label: "with"))

    let snapshot = MemoryAtlasLayoutEngine.makeSnapshot(
      graph: KnowledgeGraphResponse(nodes: nodes, edges: edges), userName: "David")
    let ordered = snapshot.rankedEdges
    let spokes = ordered.enumerated().filter {
      $0.element.edge.sourceId == "david" || $0.element.edge.targetId == "david"
    }

    XCTAssertNotNil(
      ordered.prefix(MemoryAtlasSnapshot.spokesDrawnOnMerit + 1).first { $0.id == "pair" },
      "A relationship between two other entities is drawn early, not after a hundred spokes")
    // But not *all* of them demoted: the one entity the user knows is connected
    // to everything must not be drawn with no lines at all.
    XCTAssertEqual(
      spokes.prefix(while: { $0.offset < MemoryAtlasSnapshot.spokesDrawnOnMerit + 1 }).count,
      MemoryAtlasSnapshot.spokesDrawnOnMerit,
      "A handful of your strongest connections still compete on merit")
    XCTAssertEqual(
      ordered.suffix(nodes.count - 1 - MemoryAtlasSnapshot.spokesDrawnOnMerit).filter {
        $0.edge.sourceId == "david" || $0.edge.targetId == "david"
      }.count,
      12 - MemoryAtlasSnapshot.spokesDrawnOnMerit,
      "The rest come last, however prominent their other end is")
  }

  /// Entering a region has to actually arrive somewhere: close enough that its
  /// entities are named, framed so you can still see where it ends. A camera
  /// that lands on the whole map again has taken the user back where they were.
  func testEnteringARegionFramesItRatherThanTheWholeMap() {
    let viewport = CGSize(width: 1200, height: 650)
    let range = MemoryAtlasZoomPolicy.minimumZoom...20

    let tight = MemoryAtlasNeighbourhoodLabels.entering(
      center: CGPoint(x: 0.3, y: 0.4), radius: 0.05, viewport: viewport, zoomRange: range)
    let sprawling = MemoryAtlasNeighbourhoodLabels.entering(
      center: CGPoint(x: 0.5, y: 0.5), radius: 0.4, viewport: viewport, zoomRange: range)

    XCTAssertGreaterThan(tight.zoom, 1, "A small region has to be zoomed into to be read")
    XCTAssertGreaterThan(tight.zoom, sprawling.zoom, "A tighter region needs more magnification")
    XCTAssertEqual(sprawling.pan.width, 0, accuracy: 1e-9, "A centred region needs no pan")

    // The region's centre must land in the middle of the viewport, which is the
    // same projection the canvas draws with — one scale for both axes, taken
    // from the shorter side, so a wide window adds margin rather than stretch.
    let span = MemoryAtlasLayoutEngine.projectionSpan(of: viewport)
    let projected = (0.3 - 0.5) * span * tight.zoom + viewport.width / 2 + tight.pan.width
    XCTAssertEqual(projected, viewport.width / 2, accuracy: 1e-6)
  }

  /// A region wider than the map cannot be zoomed *out* to fit — the camera has
  /// a floor, and asking for less than it must not invert the gesture.
  func testEnteringAHugeRegionStopsAtTheZoomFloor() {
    let camera = MemoryAtlasNeighbourhoodLabels.entering(
      center: CGPoint(x: 0.5, y: 0.5), radius: 3,
      viewport: CGSize(width: 1200, height: 650),
      zoomRange: MemoryAtlasZoomPolicy.minimumZoom...20)

    XCTAssertEqual(camera.zoom, MemoryAtlasZoomPolicy.minimumZoom)
  }

  /// The header used to count the server's response while the timeline counted
  /// the drawn map, so a real account read "1,097 entities · 1,544 connections"
  /// directly above "1,096 entities · 1,377 connections" — the same map,
  /// described twice, disagreeing.
  func testTheHeaderCountsTheMapThatIsActuallyDrawn() {
    let graph = KnowledgeGraphResponse(
      nodes: [
        KnowledgeGraphNode(id: "david", label: "David", nodeType: .person),
        KnowledgeGraphNode(id: "user", label: "User", nodeType: .person),
        KnowledgeGraphNode(id: "omi", label: "Omi", nodeType: .thing),
      ],
      edges: [
        KnowledgeGraphEdge(id: "a", sourceId: "david", targetId: "omi", label: "works_on"),
        // The same relationship, emitted twice under two verbs.
        KnowledgeGraphEdge(id: "b", sourceId: "omi", targetId: "david", label: "with"),
        // An edge naming an entity the response never sent.
        KnowledgeGraphEdge(id: "c", sourceId: "omi", targetId: "ghost", label: "uses"),
      ]
    )

    let snapshot = MemoryAtlasLayoutEngine.makeSnapshot(graph: graph, userName: "David")

    XCTAssertEqual(
      MemoryAtlasLayoutEngine.countLabel(
        entities: snapshot.nodes.count, connections: snapshot.edges.count),
      "2 entities · 1 connection",
      "Three nodes and three edges arrived; two entities and one connection are drawn")

    XCTAssertEqual(
      MemoryAtlasLayoutEngine.countLabel(entities: 2, memories: 1_093, connections: 1),
      "2 entities · 1093 memories · 1 connection")
  }

  private func placement(label: String, degree: Int) -> MemoryAtlasNodePlacement {
    MemoryAtlasNodePlacement(
      node: KnowledgeGraphNode(id: label, label: label, nodeType: .thing),
      cluster: .thing,
      normalizedPosition: .zero,
      degree: degree,
      clusterRank: 0,
      isCatalog: false
    )
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
    // readable than none — so this asserts that the great majority of the
    // atlas is named on the actual square drawing surface, not that collision
    // handling became perfect. A wide window must use that same square
    // projection rather than pretending its extra horizontal margin creates
    // space for labels.
    XCTAssertGreaterThanOrEqual(plan.labelNodeIDs.count, 22)
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
