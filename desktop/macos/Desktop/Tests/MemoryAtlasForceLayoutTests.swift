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
    let links = Layout.coOccurrenceLinks(
      memoryIDsByNodeID: [
        "sang": ["m1", "m2", "m3"],
        "kory": ["m1", "m2", "m3"],
        "stranger": ["m9"],
      ], excluding: nil)

    let pair = links.first { $0.a == "kory" && $0.b == "sang" }
    XCTAssertNotNil(pair, "Entities sharing three memories are related whether or not a verb exists")
    XCTAssertNil(links.first { $0.a == "stranger" || $0.b == "stranger" })
  }

  /// A calendar invite naming eight attendees is not eight strong friendships.
  /// Each shared memory contributes 1/(k-1), so a pair that only ever meets in
  /// crowds stays weaker than a pair that meets alone.
  func testGroupMembershipIsWeightedDownAgainstOneToOneCoOccurrence() throws {
    let crowd = Layout.coOccurrenceLinks(
      memoryIDsByNodeID: [
        "a": ["group"], "b": ["group"], "c": ["group"], "d": ["group"], "e": ["group"],
      ], excluding: nil)
    let couple = Layout.coOccurrenceLinks(
      memoryIDsByNodeID: ["a": ["solo"], "b": ["solo"]], excluding: nil)

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

    XCTAssertTrue(Layout.coOccurrenceLinks(memoryIDsByNodeID: wall, excluding: nil).isEmpty)
  }

  /// An entity can cite the same memory twice. Counted naively, the duplicate
  /// inflates the participant count past the noise cap and the memory is
  /// discarded, taking every relationship it implied with it — a whole cluster
  /// vanishing because one node listed one memory twice.
  func testAnEntityCitingTheSameMemoryTwiceDoesNotDiscardThatMemory() {
    var citations: [String: [String]] = [:]
    for index in 0..<Layout.maximumEntitiesPerMemory { citations["e\(index)"] = ["shared"] }
    citations["e0"] = ["shared", "shared"]

    let links = Layout.coOccurrenceLinks(memoryIDsByNodeID: citations, excluding: nil)

    XCTAssertFalse(links.isEmpty, "A duplicated citation must not push the memory past the cap")
    XCTAssertNil(links.first { $0.a == $0.b }, "An entity is not related to itself")
  }

  /// The account holder is not the only superhub. An account has a handful of
  /// entities — the project, the tool, the repository — in hundreds of memories,
  /// and sharing a memory with one of those is true of nearly everything, so it
  /// separates nothing. That is the same argument that excludes the account
  /// holder from this projection, and it applies here for the same reason.
  func testSharingAMemoryWithSomethingUbiquitousIsWeakEvidence() throws {
    var citations: [String: [String]] = [:]
    let everyMemory = (0..<40).map { "m\($0)" }
    citations["omi"] = everyMemory
    // Two entities that appear rarely, and only ever together.
    citations["oauth"] = ["m0"]
    citations["exfiltration"] = ["m0"]
    // A third that is just as rare, but only ever seen alongside the ubiquitous
    // one — the same raw co-occurrence count, far less to conclude from.
    citations["bystander"] = ["m1"]
    for index in 2..<40 { citations["filler\(index)"] = [everyMemory[index]] }

    let links = Layout.coOccurrenceLinks(memoryIDsByNodeID: citations, excluding: nil)

    let specific = try XCTUnwrap(links.first { $0.a == "exfiltration" && $0.b == "oauth" })
    let withHub = try XCTUnwrap(links.first { $0.a == "bystander" && $0.b == "omi" })
    XCTAssertGreaterThan(
      specific.weight, withHub.weight,
      "Two rare entities meeting is worth more than one of them meeting what is in everything")
  }

  /// Not a filter, for the same reason the account holder's edges are damped
  /// rather than dropped: an entity whose only relationships are to a ubiquitous
  /// one still has those relationships, and deleting them would strand it in the
  /// halo as if it were connected to nothing.
  func testAUbiquitousEntityKeepsItsRelationships() {
    var citations: [String: [String]] = ["omi": (0..<30).map { "m\($0)" }]
    for index in 0..<30 { citations["thing\(index)"] = ["m\(index)"] }

    let links = Layout.coOccurrenceLinks(memoryIDsByNodeID: citations, excluding: nil)

    XCTAssertFalse(
      links.filter { $0.a == "omi" || $0.b == "omi" }.isEmpty,
      "Discounted is not deleted")
    XCTAssertTrue(
      links.allSatisfy { $0.weight > 0 }, "A discount must not zero a real relationship")
  }

  // MARK: - The account holder is not a peer

  /// The account holder appears in nearly every memory, so co-occurring with
  /// them is true of almost every entity and separates none of them. Left in
  /// the projection they become every entity's strongest partner, which is
  /// exactly the "everything is related to me" hairball the layout exists to
  /// avoid.
  func testTheAnchorEarnsNoCoOccurrence() {
    let links = Layout.coOccurrenceLinks(
      memoryIDsByNodeID: [
        "me": ["m1", "m2", "m3"],
        "sang": ["m1", "m2"],
        "kory": ["m1", "m3"],
      ], excluding: "me")

    XCTAssertNil(
      links.first { $0.a == "me" || $0.b == "me" },
      "Being in the same memory as the account holder says nothing about an entity")
    XCTAssertNotNil(links.first { $0.a == "kory" && $0.b == "sang" })
  }

  /// The second half of the damage, and the less obvious one: as a participant
  /// the account holder inflates every memory's headcount, so the 1/(k-1) share
  /// that real relationships earn from it is diluted by their presence.
  func testDroppingTheAnchorStrengthensEveryoneElsesRelationships() throws {
    let citations = ["me": ["dinner"], "sang": ["dinner"], "kory": ["dinner"]]

    let asPeer = Layout.coOccurrenceLinks(memoryIDsByNodeID: citations, excluding: nil)
    let asObserver = Layout.coOccurrenceLinks(memoryIDsByNodeID: citations, excluding: "me")

    let diluted = try XCTUnwrap(asPeer.first { $0.a == "kory" && $0.b == "sang" }).weight
    let whole = try XCTUnwrap(asObserver.first { $0.a == "kory" && $0.b == "sang" }).weight
    XCTAssertGreaterThan(whole, diluted, "Two people at dinner are not a three-way crowd")
  }

  /// The edges the extractor drew to the account holder are real assertions, so
  /// they survive — but loosened. At full strength a few hundred of them aim at
  /// one pinned point, and the map collapses onto it.
  func testRelationshipsToTheAnchorAreLoosenedNotDropped() throws {
    let links = [
      Link(a: "me", b: "omi", weight: 4),
      Link(a: "omi", b: "github", weight: 4),
    ]

    let tethered = Layout.tetherToAnchor(links, anchorID: "me")

    let toAnchor = try XCTUnwrap(tethered.first { $0.a == "me" || $0.b == "me" })
    let elsewhere = try XCTUnwrap(tethered.first { $0.a == "github" || $0.b == "github" })
    XCTAssertEqual(toAnchor.weight, 4 * Layout.anchorTetherStrength, accuracy: 1e-12)
    XCTAssertGreaterThan(toAnchor.weight, 0, "A tether, not a deletion")
    XCTAssertEqual(elsewhere.weight, 4, accuracy: 1e-12, "Only the anchor's own links are damped")
  }

  /// The property all of that exists for, measured the only way it can be.
  ///
  /// Whether related things end up together is statistical, not a property any
  /// handful of nodes can demonstrate: a couple of dense groups stay separate
  /// under any weighting, so a small fixture passes whatever the layout does.
  /// This builds an account-shaped graph instead — a thousand entities in
  /// planted communities, memories that are mostly about one community at a
  /// time, an extractor that draws an edge for only some of what it sees, and
  /// an account holder present in most memories — and asks the question the map
  /// is actually for: *of the ten entities drawn nearest to this one, how many
  /// belong with it?*
  ///
  /// Chance is 1 in 44. Treating the account holder as an ordinary peer scores
  /// 0.59; excluding them from co-occurrence and loosening their drawn edges
  /// scores 0.76. The floor below is slack enough to survive ordinary tuning
  /// and tight enough to catch the exclusion being lost, which measures 0.66.
  ///
  /// It does *not* pin the tether — undamping it scores 0.72, still above the
  /// floor. That is deliberate: the floor guards the map staying legible, and
  /// tightening it to 0.75 to catch one constant would make every future
  /// tuning change look like a regression. `anchorTetherStrength` is pinned
  /// exactly by `testRelationshipsToTheAnchorAreLoosenedNotDropped` instead.
  func testRelatedEntitiesAreDrawnTogetherOnAnAccountShapedGraph() throws {
    let graph = PlantedCommunityGraph(nodeCount: 1096, communities: 44, memories: 1044)

    let result = Layout.layout(
      nodeIDs: graph.nodeIDs,
      links: Layout.merge(graph.explicitLinks + graph.coOccurrenceLinks),
      anchorID: graph.anchorID,
      typeTargets: graph.typeTargets,
      area: area)

    let precision = graph.communityPrecision(of: result)
    XCTAssertGreaterThan(
      precision, 0.70,
      "Neighbourhoods stopped meaning anything (chance is \(1.0 / 44.0))")
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
    // A two-entity island with no path to the rest of the map is parked at the
    // edge with the isolates. Relaxed in the middle it would only be pushed
    // outward anyway, and on a real account dozens of these end up defining the
    // canvas extent and squashing the structure worth looking at.
    XCTAssertEqual(result.roles["pairA"], .isolate)
    XCTAssertEqual(result.roles["pairB"], .isolate)
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
  ///
  /// This is also the guard on neighbourhood cohesion not eating the map. An
  /// earlier version pulled every node toward its neighbourhood's centre point
  /// rather than containing it within the neighbourhood's radius, which
  /// squeezed a small map onto a single point — the fit then blew that point
  /// back up to fill the canvas and the separation pass spread the remains on
  /// an even grid, producing a confident-looking map with every distance
  /// destroyed. This test is what caught it.
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

  // MARK: - Neighbourhoods

  /// Nobody tells the map how many neighbourhoods an account has, and nothing
  /// good happens if it guesses: two projects that share one person are two
  /// projects, and a fixed target of *k* groups would either split one of them
  /// or fuse both.
  func testNeighbourhoodsAreFoundWithoutBeingToldHowMany() throws {
    let left = (0..<6).map { "left\($0)" }
    let right = (0..<6).map { "right\($0)" }
    var links: [Link] = []
    for group in [left, right] {
      for i in 0..<group.count {
        for j in (i + 1)..<group.count { links.append(Link(a: group[i], b: group[j], weight: 5)) }
      }
    }
    // The one person who works on both, which is what makes this a graph and
    // not two graphs.
    links.append(Link(a: "left0", b: "right0", weight: 1))

    let found = Layout.detectCommunities(coreIDs: left + right, neighbors: adjacency(of: links))

    XCTAssertEqual(Set(found.values).count, 2, "Two projects joined by one person are two projects")
    XCTAssertEqual(Set(left.map { found[$0] }).count, 1)
    XCTAssertEqual(Set(right.map { found[$0] }).count, 1)
    XCTAssertNotEqual(found["left1"], found["right1"])
  }

  /// Neighbourhoods move nodes, so an unstable grouping is an unstable map. The
  /// server does not promise an edge order, and Swift seeds string hashing per
  /// process, so anything read from a dictionary's iteration order would drift
  /// between launches on an unchanged account.
  func testNeighbourhoodsDoNotDependOnTheOrderRelationshipsArriveIn() {
    let ids = (0..<14).map { "n\($0)" }
    var links: [Link] = []
    for i in 0..<ids.count {
      for j in (i + 1)..<ids.count where (i / 7) == (j / 7) {
        links.append(Link(a: ids[i], b: ids[j], weight: 3))
      }
    }
    links.append(Link(a: "n0", b: "n13", weight: 1))

    let forwards = Layout.detectCommunities(coreIDs: ids, neighbors: adjacency(of: links))
    let backwards = Layout.detectCommunities(
      coreIDs: ids, neighbors: adjacency(of: links.reversed()))

    XCTAssertEqual(forwards, backwards)
  }

  /// The layout finds neighbourhoods in order to draw them apart; the caller
  /// needs them in order to *name* them. Reporting them is what lets the map
  /// say where you are, so it has to survive the passes that run afterwards.
  func testTheLayoutReportsTheNeighbourhoodsItFound() throws {
    let left = (0..<6).map { "left\($0)" }
    let right = (0..<6).map { "right\($0)" }
    var links: [Link] = []
    for group in [left, right] {
      for i in 0..<group.count {
        for j in (i + 1)..<group.count { links.append(Link(a: group[i], b: group[j], weight: 5)) }
      }
    }
    links.append(Link(a: "left0", b: "right0", weight: 1))

    let result = Layout.layout(
      nodeIDs: left + right, links: links, anchorID: nil, typeTargets: [:], area: area)

    XCTAssertEqual(Set(left.map { result.communities[$0] }).count, 1)
    XCTAssertEqual(Set(right.map { result.communities[$0] }).count, 1)
    XCTAssertNotEqual(result.communities["left1"], result.communities["right1"])
  }

  /// An entity related to nothing is in no neighbourhood, and the map must not
  /// invent one for it — that is the same claim the outer halo exists to avoid
  /// making about where it sits.
  func testEntitiesWithNoRelationshipsJoinNoNeighbourhood() throws {
    let result = Layout.layout(
      nodeIDs: ["a", "b", "c", "alone"],
      links: [Link(a: "a", b: "b", weight: 4), Link(a: "b", b: "c", weight: 4)],
      anchorID: nil,
      typeTargets: [:],
      area: area)

    XCTAssertNil(result.communities["alone"])
    XCTAssertNotNil(result.communities["b"])
  }

  /// The account holder joins no neighbourhood, for the same reason they earn
  /// no co-occurrence: they are in everything. A neighbourhood is described by
  /// its strongest members, and letting them in would name every region on the
  /// map after the person reading it.
  func testTheAccountHolderJoinsNoNeighbourhood() throws {
    var links: [Link] = []
    let members = (0..<8).map { "n\($0)" }
    for i in 0..<members.count {
      for j in (i + 1)..<members.count { links.append(Link(a: members[i], b: members[j], weight: 3)) }
    }
    for member in members { links.append(Link(a: "me", b: member, weight: 9)) }

    let result = Layout.layout(
      nodeIDs: members + ["me"], links: links, anchorID: "me", typeTargets: [:], area: area)

    XCTAssertEqual(result.roles["me"], .core, "They are still on the map")
    XCTAssertNil(result.communities["me"], "They are just not part of any one region of it")
  }

  /// A leaf is pinned beside its parent rather than relaxed, so it has no
  /// grouping of its own. Leaving it ungrouped would drop a hub's entire burr
  /// out of the region its hub defines — on a real account, most of the region.
  func testALeafBelongsWhereItsParentBelongs() throws {
    var links: [Link] = []
    let members = (0..<6).map { "n\($0)" }
    for i in 0..<members.count {
      for j in (i + 1)..<members.count { links.append(Link(a: members[i], b: members[j], weight: 3)) }
    }
    links.append(Link(a: "n0", b: "leaf", weight: 2))

    let result = Layout.layout(
      nodeIDs: members + ["leaf"], links: links, anchorID: nil, typeTargets: [:], area: area)

    XCTAssertEqual(result.roles["leaf"], .leaf(parentID: "n0"))
    XCTAssertEqual(result.communities["leaf"], result.communities["n0"])
  }

  /// Evenly spaced on a fixed radius, a hub's leaves drew a flawless arc of
  /// dots — a shape no data produces, which read as a rendering fault on the
  /// real account rather than as a hub with thirty single-relationship
  /// entities hanging off it.
  func testAHubsLeavesDoNotDrawAPerfectArc() throws {
    let leaves = (0..<24).map { "leaf\($0)" }
    let result = Layout.layout(
      nodeIDs: ["hub", "other"] + leaves,
      links: [Link(a: "hub", b: "other", weight: 5)]
        + leaves.map { Link(a: "hub", b: $0, weight: 2) },
      anchorID: nil,
      typeTargets: [:],
      area: area)

    let hub = try XCTUnwrap(result.positions["hub"])
    let radii = try leaves.map { try distance(XCTUnwrap(result.positions[$0]), hub) }

    // What made it look drawn was not the spread of radii — the old fan already
    // used two rings — but that every leaf sat on one of them exactly. Counting
    // distinct distances is what separates "an arc" from "a scatter": the old
    // fan produced 2 for these 24 leaves.
    let distinct = Set(radii.map { (($0 / max(radii.max() ?? 1, 1e-9)) * 200).rounded() }).count

    XCTAssertGreaterThan(
      distinct, leaves.count / 2,
      "Leaves sharing a handful of exact radii trace circles, which is what read as a rendering fault")
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

  func testLeavesSitBesideTheirParentAndIsolatesLeaveTheAnchorLegible() throws {
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
    XCTAssertGreaterThan(
      distance(lonely, CGPoint(x: area.midX, y: area.midY)),
      Double(min(area.width, area.height)) * 0.1,
      "An unconnected entity must not obscure the map's anchor")
  }

  /// Unconnected entities fill a circular peripheral field, not a rectangular
  /// border or hollow ring around the semantic core.
  func testUnconnectedEntitiesFillCircularPeripheralField() throws {
    var links: [Link] = []
    let spine = (0..<14).map { "spine\($0)" }
    for index in 0..<(spine.count - 1) {
      links.append(Link(a: spine[index], b: spine[index + 1], weight: 4))
    }
    let lonely = (0..<600).map { "lonely\($0)" }

    let result = Layout.layout(
      nodeIDs: spine + lonely, links: links, anchorID: nil, typeTargets: [:], area: area)

    let placed = lonely.compactMap { result.positions[$0] }
    XCTAssertEqual(placed.count, lonely.count)

    let radii = placed.map { hypot($0.x - area.midX, $0.y - area.midY) }
    let inner = min(area.width, area.height) * 0.5
    XCTAssertGreaterThan(radii.min() ?? 0, inner * 0.35, "The catalog must leave a recognizable semantic core")
    XCTAssertLessThan(radii.max() ?? 1, inner * 1.3, "Catalog volume must not inflate the viewport")
    XCTAssertGreaterThan(
      (radii.max() ?? 0) - (radii.min() ?? 0), inner * 0.25,
      "Loose memories should fill the peripheral field, not form a hollow ring")
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

  /// Whether a neighbourhood is a *place* rather than a smear, which is a
  /// different question from whether the layout recovered it — and, like that
  /// one, statistical. A pair of dense groups drift apart under any weighting,
  /// so a small fixture demonstrates nothing here either; it takes an
  /// account-shaped graph, where dozens of groups compete for the same canvas
  /// and the ones that share members pile up on each other.
  ///
  /// Measured as the share of entities inside a group's own patch that belong to
  /// some other group. Holding each group together is not enough to fix this on
  /// its own — two groups both sit at their ideal radius while covering the same
  /// ground — and with nothing but per-entity repulsion between them the fixture
  /// scores 0.385. Pushing overlapping groups apart scores 0.267.
  ///
  /// The ceiling is set between the two rather than at the measured value, so
  /// ordinary tuning does not read as a regression while losing the force
  /// entirely still does.
  func testNeighbourhoodsAreDrawnAsPlacesRatherThanOnTopOfEachOther() throws {
    let graph = PlantedCommunityGraph(nodeCount: 1096, communities: 44, memories: 1044)

    let result = Layout.layout(
      nodeIDs: graph.nodeIDs,
      links: Layout.merge(graph.explicitLinks + graph.coOccurrenceLinks),
      anchorID: graph.anchorID,
      typeTargets: graph.typeTargets,
      area: area)

    XCTAssertLessThan(
      graph.neighbourhoodIntrusion(of: result), 0.33,
      "Neighbourhoods drawn through one another are not somewhere the user can go")
  }

  /// Nearly everything in an account keeps some relationship to the account
  /// holder, so the middle of the map — the first place anyone looks — is where
  /// the crowd presses hardest and reads worst. They are pinned there and push
  /// back with one entity's worth of repulsion against hundreds of entities'
  /// worth of pull, so the room around them has to be granted rather than
  /// competed for.
  ///
  /// Measured at account size, because the crowding is proportional to how many
  /// entities keep a tether and the force is scaled to match: on this fixture
  /// the twenty entities nearest the account holder sit 5.76 typical gaps away
  /// when they push back as an ordinary node, and 6.85 when weighted to the map
  /// they sit in the middle of. A forty-entity fixture shows nothing either way,
  /// which is how the scaling came to be written that way.
  func testTheAccountHolderIsGivenRoomToBeSeenIn() throws {
    let graph = PlantedCommunityGraph(nodeCount: 1096, communities: 44, memories: 1044)

    let result = Layout.layout(
      nodeIDs: graph.nodeIDs,
      links: Layout.merge(graph.explicitLinks + graph.coOccurrenceLinks),
      anchorID: graph.anchorID,
      typeTargets: graph.typeTargets,
      area: area)

    XCTAssertGreaterThan(
      graph.anchorClearing(of: result), 6.2,
      "The account holder needs more room than the crowd tethered to them will leave")
  }

  func testAGraphWithNoRelationshipsAtAllDrawsNoFakeConstellation() {
    let result = Layout.layout(
      nodeIDs: ["a", "b", "c"], links: [], anchorID: nil, typeTargets: [:], area: area)

    XCTAssertEqual(result.roles.values.filter { $0 == .isolate }.count, 3)
  }

  // MARK: - Helpers

  /// The neighbour lists `layout` builds internally, so a detection test can be
  /// written against a link set like every other test here.
  private func adjacency(of links: [Link]) -> [String: [(id: String, weight: Double)]] {
    var neighbors: [String: [(id: String, weight: Double)]] = [:]
    for link in links {
      neighbors[link.a, default: []].append((link.b, link.weight))
      neighbors[link.b, default: []].append((link.a, link.weight))
    }
    return neighbors
  }

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
