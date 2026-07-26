import CoreGraphics
import XCTest

@testable import Omi_Computer

/// The atlas used to place nodes with `f(type, salienceRank, hash(id))` and
/// never read a single edge, so proximity on the map meant "same type and
/// similar importance" — never "related". These tests hold the new contract:
/// distance means relatedness, and type is only a nudge.
final class MemoryAtlasForceLayoutTests: XCTestCase {
  private typealias Layout = MemoryAtlasForceLayout
  private typealias Link = MemoryAtlasForceLayout.Link

  private let area = CGRect(x: 0.1, y: 0.14, width: 0.8, height: 0.72)

  // MARK: - Deriving relatedness

  /// Node payloads already carry the memories they came from, which is a
  /// complete entity↔memory incidence structure the client only ever used to
  /// populate the evidence list.
  func testCoOccurrenceFindsRelatednessTheExtractorNeverDrewAnEdgeFor() {
    let links = Layout.coOccurrenceLinks(memoryIDsByNodeID: [
      "sang": ["m1", "m2", "m3"],
      "kory": ["m1", "m2", "m3"],
      "stranger": ["m9"],
    ])

    let pair = links.first { $0.a == "kory" && $0.b == "sang" }
    XCTAssertNotNil(pair, "Entities sharing three memories are related whether or not a verb exists")
    XCTAssertNil(links.first { $0.a == "stranger" || $0.b == "stranger" })
  }

  /// A calendar invite naming eight attendees is not eight strong friendships.
  /// Each shared memory contributes 1/(k-1), so a pair that only ever meets in
  /// crowds stays weaker than a pair that meets alone.
  func testGroupMembershipIsWeightedDownAgainstOneToOneCoOccurrence() throws {
    let crowd = Layout.coOccurrenceLinks(memoryIDsByNodeID: [
      "a": ["group"], "b": ["group"], "c": ["group"], "d": ["group"], "e": ["group"],
    ])
    let couple = Layout.coOccurrenceLinks(memoryIDsByNodeID: ["a": ["solo"], "b": ["solo"]])

    let crowdWeight = try XCTUnwrap(crowd.first { $0.a == "a" && $0.b == "b" }).weight
    let coupleWeight = try XCTUnwrap(couple.first { $0.a == "a" && $0.b == "b" }).weight
    XCTAssertLessThan(crowdWeight, coupleWeight)
  }

  func testMemoriesNamingTooManyEntitiesAreSkippedRatherThanDownweighted() {
    // Extraction noise: k² spurious pairs from one junk memory would otherwise
    // outweigh every real relationship on the map.
    let wall = (0..<(Layout.maximumEntitiesPerMemory + 5)).reduce(into: [String: [String]]()) {
      $0["e\($1)"] = ["noise"]
    }

    XCTAssertTrue(Layout.coOccurrenceLinks(memoryIDsByNodeID: wall).isEmpty)
  }

  /// An entity can cite the same memory twice — the anchor does, whenever a
  /// generic "Me" node is folded into it and brings its memories along. Counted
  /// naively, the duplicate inflates the participant count past the noise cap
  /// and the memory is discarded, taking every relationship it implied with it.
  func testAnEntityCitingTheSameMemoryTwiceDoesNotDiscardThatMemory() {
    var citations: [String: [String]] = [:]
    for index in 0..<Layout.maximumEntitiesPerMemory { citations["e\(index)"] = ["shared"] }
    citations["e0"] = ["shared", "shared"]

    let links = Layout.coOccurrenceLinks(memoryIDsByNodeID: citations)

    XCTAssertFalse(links.isEmpty, "A duplicated citation must not push the memory past the cap")
    XCTAssertNil(links.first { $0.a == $0.b }, "An entity is not related to itself")
  }

  /// Two marks landing on exactly the same point is the one case the separation
  /// pass most obviously exists for, and the easiest to get wrong: a nudge
  /// equal to the minimum reads as "already far enough apart".
  func testExactlyCoincidentMarksAreSeparated() throws {
    var positions = [
      "a": CGPoint(x: 0.5, y: 0.5),
      "b": CGPoint(x: 0.5, y: 0.5),
    ]

    Layout.separateCrowdedMarks(&positions, coreIDs: ["a", "b"], anchorID: nil, area: area)

    let a = try XCTUnwrap(positions["a"])
    let b = try XCTUnwrap(positions["b"])
    XCTAssertGreaterThan(distance(a, b), 0.01, "Stacked marks hide each other entirely")
  }

  /// Sparsification keeps each node's strongest partners, but a small entity
  /// whose single relationship is with a busy hub must not be orphaned just
  /// because the hub has better options.
  func testSparsificationKeepsALinkThatIsSomeNodesOnlyRelationship() {
    var links: [Link] = (1...12).map { Link(a: "hub", b: "big\($0)", weight: 10) }
    links.append(Link(a: "hub", b: "tiny", weight: 0.1))

    let kept = Layout.strongestPerNode(links, limit: 4)

    XCTAssertTrue(kept.contains { $0.a == "hub" && $0.b == "tiny" })
  }

  func testMergeSumsDuplicatePairsRegardlessOfEndpointOrder() {
    let merged = Layout.merge([
      Link(a: "x", b: "y", weight: 1),
      Link(a: "y", b: "x", weight: 2),
      Link(a: "z", b: "z", weight: 9),
    ])

    XCTAssertEqual(merged.count, 1, "A self-link is not a relationship")
    XCTAssertEqual(merged[0].weight, 3)
  }

  // MARK: - Classification

  func testNodesAreClassifiedByWhatTheirPositionCouldPossiblyMean() {
    let links = [
      Link(a: "hub", b: "leaf", weight: 1),
      Link(a: "hub", b: "other", weight: 1),
      Link(a: "pairA", b: "pairB", weight: 1),
    ]
    let result = Layout.layout(
      nodeIDs: ["hub", "leaf", "other", "pairA", "pairB", "alone"],
      links: links, anchorID: nil, typeTargets: [:], area: area)

    XCTAssertEqual(result.roles["leaf"], .leaf(parentID: "hub"))
    XCTAssertEqual(result.roles["alone"], .isolate, "No relationships means no position worth asserting")
    XCTAssertEqual(result.roles["hub"], .core)
    // Two nodes that only know each other have nothing to hang off of.
    XCTAssertEqual(result.roles["pairA"], .core)
    XCTAssertEqual(result.roles["pairB"], .core)
  }

  func testTheAnchorIsNeverDemotedToALeaf() {
    let result = Layout.layout(
      nodeIDs: ["me", "hub", "other"],
      links: [Link(a: "me", b: "hub", weight: 1), Link(a: "hub", b: "other", weight: 1)],
      anchorID: "me", typeTargets: [:], area: area)

    XCTAssertEqual(result.roles["me"], .core)
  }

  // MARK: - The contract

  /// The whole point. Two communities joined by a single bridge must come out
  /// as two neighbourhoods, not interleaved.
  func testRelatedEntitiesEndUpTogetherAndUnrelatedOnesDoNot() {
    let alpha = (1...5).map { "a\($0)" }
    let beta = (1...5).map { "b\($0)" }
    var links: [Link] = []
    for group in [alpha, beta] {
      for i in 0..<group.count {
        for j in (i + 1)..<group.count {
          links.append(Link(a: group[i], b: group[j], weight: 1))
        }
      }
    }
    links.append(Link(a: "a1", b: "b1", weight: 1))

    let result = Layout.layout(
      nodeIDs: alpha + beta, links: links, anchorID: nil, typeTargets: [:], area: area)

    let within = meanDistance(within: alpha, result) + meanDistance(within: beta, result)
    let across = meanDistance(between: alpha, and: beta, result)
    XCTAssertLessThan(
      within / 2, across,
      "Communities must be closer to themselves than to each other")
  }

  /// Type is a tint and a nudge, never a partition. A person whose only
  /// relationships are with one project has to be free to sit inside that
  /// project's neighbourhood instead of being filed under People.
  func testStrongRelationshipsOverrideTheTypeField() throws {
    let concepts = (1...6).map { "c\($0)" }
    var links: [Link] = []
    for i in 0..<concepts.count {
      for j in (i + 1)..<concepts.count {
        links.append(Link(a: concepts[i], b: concepts[j], weight: 4))
      }
    }
    // One person, related only to the concept cluster, but pulled by the type
    // field toward the opposite corner of the canvas.
    for concept in concepts { links.append(Link(a: "person", b: concept, weight: 4)) }

    let peoplePetal = CGPoint(x: 0.9, y: 0.9)
    var targets: [String: CGPoint] = ["person": peoplePetal]
    for concept in concepts { targets[concept] = CGPoint(x: 0.15, y: 0.15) }

    let result = Layout.layout(
      nodeIDs: concepts + ["person"], links: links, anchorID: nil,
      typeTargets: targets, area: area)

    let person = try XCTUnwrap(result.positions["person"])
    let clusterCentroid = centroid(of: concepts, result)
    let toCluster = distance(person, clusterCentroid)
    let toPetal = distance(person, peoplePetal)
    XCTAssertLessThan(
      toCluster, toPetal,
      "The type field must not overrule the structure it is decorating")
  }

  // MARK: - Determinism

  /// Swift seeds string hashing per process, so a layout that walks a
  /// dictionary lays out differently on every launch. Shuffling the input
  /// catches that where calling twice in one process cannot.
  func testLayoutIsIndependentOfInputOrder() throws {
    let ids = (1...14).map { "n\($0)" }
    var links: [Link] = []
    for i in 0..<ids.count - 1 {
      links.append(Link(a: ids[i], b: ids[i + 1], weight: Double(i % 3 + 1)))
    }
    links.append(Link(a: ids[0], b: ids[7], weight: 2))

    let forward = Layout.layout(
      nodeIDs: ids, links: links, anchorID: "n1", typeTargets: [:], area: area)
    let reversed = Layout.layout(
      nodeIDs: ids.reversed(), links: links.reversed(), anchorID: "n1",
      typeTargets: [:], area: area)

    // Exact equality, not a tolerance. Spring forces are summed in link order
    // and floating-point addition is not associative, so anything short of
    // bit-identical means the order still reaches the coordinates — a drift
    // too small to see in one step compounds over ninety.
    for id in ids {
      let a = try XCTUnwrap(forward.positions[id])
      let b = try XCTUnwrap(reversed.positions[id])
      XCTAssertEqual(a.x, b.x, "\(id) x drifted with input order")
      XCTAssertEqual(a.y, b.y, "\(id) y drifted with input order")
    }
  }

  // MARK: - Geometry the canvas depends on

  func testAnchorHoldsTheCentreOfItsOwnMap() {
    let ids = ["me"] + (1...9).map { "n\($0)" }
    let links = (1...9).map { Link(a: "me", b: "n\($0)", weight: 1) }

    let result = Layout.layout(
      nodeIDs: ids, links: links, anchorID: "me", typeTargets: [:], area: area)

    XCTAssertEqual(result.positions["me"]?.x ?? 0, area.midX, accuracy: 1e-9)
    XCTAssertEqual(result.positions["me"]?.y ?? 0, area.midY, accuracy: 1e-9)
  }

  func testLeavesSitBesideTheirParentAndIsolatesSitOutsideTheMap() throws {
    var links: [Link] = [Link(a: "hub", b: "spoke", weight: 1)]
    for index in 1...6 { links.append(Link(a: "hub", b: "leaf\(index)", weight: 1)) }
    links.append(Link(a: "spoke", b: "other", weight: 1))
    let ids = ["hub", "spoke", "other", "lonely"] + (1...6).map { "leaf\($0)" }

    let result = Layout.layout(
      nodeIDs: ids, links: links, anchorID: nil, typeTargets: [:], area: area)

    let hub = try XCTUnwrap(result.positions["hub"])
    for index in 1...6 {
      let leaf = try XCTUnwrap(result.positions["leaf\(index)"])
      XCTAssertLessThan(
        distance(leaf, hub), Double(min(area.width, area.height)) * 0.09,
        "A leaf's only spatial information is its parent")
    }

    let lonely = try XCTUnwrap(result.positions["lonely"])
    XCTAssertFalse(
      area.insetBy(dx: area.width * 0.1, dy: area.height * 0.1).contains(lonely),
      "An unconnected entity must not sit in the middle implying structure")
  }

  func testEveryNodeLandsOnTheCanvas() throws {
    let ids = (1...60).map { "n\($0)" }
    let links = (1..<60).map { Link(a: "n\($0)", b: "n\($0 % 7 + 1)", weight: 1) }

    let result = Layout.layout(
      nodeIDs: ids, links: links, anchorID: "n1", typeTargets: [:], area: area)

    XCTAssertEqual(result.positions.count, ids.count)
    for id in ids {
      let point = try XCTUnwrap(result.positions[id])
      XCTAssertTrue(
        (0...1).contains(point.x) && (0...1).contains(point.y),
        "\(id) escaped the canvas at \(point)")
    }

    // Bounds alone would be satisfied by returning the centre for every node,
    // so this also demands the map actually occupy the canvas and keep its
    // entities apart.
    let xs = ids.compactMap { result.positions[$0]?.x }
    let ys = ids.compactMap { result.positions[$0]?.y }
    XCTAssertGreaterThan((xs.max() ?? 0) - (xs.min() ?? 0), 0.35)
    XCTAssertGreaterThan((ys.max() ?? 0) - (ys.min() ?? 0), 0.25)
    let distinct = Set(ids.compactMap { result.positions[$0].map { "\($0.x)|\($0.y)" } })
    XCTAssertEqual(distinct.count, ids.count, "No two entities may share a position")
  }

  /// A hub with nothing but single-relationship entities hanging off it has no
  /// structure to relax: the hub is the only core node, and every spoke is
  /// pinned beside it. The simulation must not be the thing that decides this.
  func testAPureStarNeedsNoSimulationAtAll() {
    let ids = (1...20).map { "n\($0)" }
    let links = (2...20).map { Link(a: "n1", b: "n\($0)", weight: 1) }

    let result = Layout.layout(
      nodeIDs: ids, links: links, anchorID: "n1", typeTargets: [:], area: area)

    XCTAssertEqual(result.roles["n1"], .core)
    XCTAssertEqual(
      result.roles.values.filter { if case .leaf = $0 { return true } else { return false } }.count,
      19)
  }

  func testAGraphWithNoRelationshipsAtAllDrawsNoFakeConstellation() {
    let result = Layout.layout(
      nodeIDs: ["a", "b", "c"], links: [], anchorID: nil, typeTargets: [:], area: area)

    XCTAssertEqual(result.roles.values.filter { $0 == .isolate }.count, 3)
  }

  // MARK: - Helpers

  private func distance(_ a: CGPoint, _ b: CGPoint) -> Double {
    Double(hypot(a.x - b.x, a.y - b.y))
  }

  private func centroid(of ids: [String], _ result: Layout.Result) -> CGPoint {
    let points = ids.compactMap { result.positions[$0] }
    guard !points.isEmpty else { return .zero }
    return CGPoint(
      x: points.map(\.x).reduce(0, +) / CGFloat(points.count),
      y: points.map(\.y).reduce(0, +) / CGFloat(points.count))
  }

  private func meanDistance(within ids: [String], _ result: Layout.Result) -> Double {
    var total = 0.0
    var count = 0
    for i in 0..<ids.count {
      for j in (i + 1)..<ids.count {
        guard let a = result.positions[ids[i]], let b = result.positions[ids[j]] else { continue }
        total += distance(a, b)
        count += 1
      }
    }
    return count == 0 ? 0 : total / Double(count)
  }

  private func meanDistance(
    between lhs: [String], and rhs: [String], _ result: Layout.Result
  ) -> Double {
    var total = 0.0
    var count = 0
    for left in lhs {
      for right in rhs {
        guard let a = result.positions[left], let b = result.positions[right] else { continue }
        total += distance(a, b)
        count += 1
      }
    }
    return count == 0 ? 0 : total / Double(count)
  }
}
