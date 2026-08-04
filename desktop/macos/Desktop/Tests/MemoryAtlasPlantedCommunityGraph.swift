import CoreGraphics
import Foundation

@testable import Omi_Computer

/// A synthetic graph shaped like a real account, for asking whether the layout
/// recovers structure that is known to be there.
///
/// Three properties make it worth building rather than reusing a random graph:
///
/// - **Communities are planted.** A memory graph is not uniformly random; it is
///   a project and its people, a trip and its places. Without planted groups
///   there is no ground truth, and "did related things end up together" has no
///   answer. (An earlier version of this fixture *was* random, and dutifully
///   reported that the layout recovered almost nothing — because there was
///   nothing to recover.)
/// - **The extractor is lossy.** It draws an edge for only about half of what a
///   memory implies, which is why co-occurrence carries most of the signal.
/// - **There is an account holder.** They participate in most memories, so
///   every entity co-occurs with them and with little else in common. That is
///   the hub that flattens the map if it is treated as an ordinary peer.
///
/// Deterministic: a fixed seed and an inlined generator, so the same graph is
/// built on every machine and the measured score is comparable run to run.
struct PlantedCommunityGraph {
  /// Inlined rather than using `SystemRandomNumberGenerator` so the fixture is
  /// reproducible, and rather than `seed`-ing a stdlib generator because none
  /// of them promise a stable sequence across Swift versions.
  private struct LinearCongruential {
    var state: UInt64
    mutating func next() -> UInt64 {
      state = state &* 6_364_136_223_846_793_005 &+ 1_442_695_040_888_963_407
      return state
    }
    mutating func int(_ bound: Int) -> Int { Int(next() % UInt64(max(bound, 1))) }
    mutating func unit() -> Double { Double(next() % 1_000_000) / 1_000_000 }
  }

  /// How much of the account holder's life is on the map: the share of memories
  /// they appear in. High by construction — it is their account.
  private static let anchorMemoryShare = 0.82

  let anchorID = "n0"
  let nodeIDs: [String]
  let typeTargets: [String: CGPoint]
  let explicitLinks: [MemoryAtlasForceLayout.Link]
  let coOccurrenceLinks: [MemoryAtlasForceLayout.Link]

  private let communityOf: [String: Int]
  private let communities: Int

  init(nodeCount: Int, communities: Int, memories: Int) {
    var rng = LinearCongruential(state: 42)
    let ids = (0..<nodeCount).map { "n\($0)" }
    var communityOf: [String: Int] = [:]
    for (index, id) in ids.enumerated() { communityOf[id] = index % communities }

    var membersOf: [Int: [String]] = [:]
    for id in ids where id != anchorID {
      guard let group = communityOf[id] else { continue }
      membersOf[group, default: []].append(id)
    }

    var memoryIDsByNodeID: [String: [String]] = [:]
    var drawn: [(sourceID: String, targetID: String, memoryCount: Int)] = []
    for index in 0..<memories {
      // `default: []` cannot fire — every community index has members — but the
      // draw must still happen exactly once per lookup either way, or the whole
      // fixture shifts and the measured scores stop being comparable.
      var pool = membersOf[rng.int(communities), default: []]
      // A minority of memories span two communities, which is what stops the
      // planted structure from being trivially separable.
      if rng.unit() < 0.12 { pool += membersOf[rng.int(communities), default: []] }

      guard !pool.isEmpty else { continue }
      var present: [String] = []
      for _ in 0..<(2 + rng.int(4)) { present.append(pool[rng.int(pool.count)]) }
      if rng.unit() < Self.anchorMemoryShare { present.append(anchorID) }
      for id in Set(present) { memoryIDsByNodeID[id, default: []].append("m\(index)") }

      if present.count >= 2, rng.unit() < 0.55 {
        let a = present[rng.int(present.count)]
        let b = present[rng.int(present.count)]
        if a != b { drawn.append((a, b, rng.int(4))) }
      }
    }

    // Type is uncorrelated with community, as it is in real data: knowing
    // something is a Place tells you nothing about which project it belongs to.
    let petals = [
      CGPoint(x: 0.5, y: 0.25), CGPoint(x: 0.64, y: 0.42), CGPoint(x: 0.59, y: 0.70),
      CGPoint(x: 0.41, y: 0.70), CGPoint(x: 0.36, y: 0.42),
    ]
    var typeTargets: [String: CGPoint] = [:]
    for (index, id) in ids.enumerated() { typeTargets[id] = petals[(index * 7) % petals.count] }

    self.nodeIDs = ids
    self.communities = communities
    self.communityOf = communityOf
    self.typeTargets = typeTargets
    self.explicitLinks = MemoryAtlasForceLayout.explicitLinks(edges: drawn)
    self.coOccurrenceLinks = MemoryAtlasForceLayout.coOccurrenceLinks(
      memoryIDsByNodeID: memoryIDsByNodeID, excluding: anchorID)
  }

  /// Of the entities drawn inside a community's own patch of canvas, the share
  /// belonging to a *different* community.
  ///
  /// A different question from `communityPrecision`, and the map needs both. A
  /// group can be perfectly recovered — every member's nearest neighbours its
  /// own — while still being drawn on top of two other groups, because
  /// precision only ever looks at the ten entities closest to a subject and
  /// never asks what else is sharing the space. That is the difference between
  /// structure the layout found and structure a person can see.
  ///
  /// Read against the neighbourhoods the layout reports rather than the planted
  /// ones, because those are what the map names and draws. Measured against the
  /// planted communities it would mostly be reporting how far detection strays
  /// from the plant, which `communityPrecision` already covers.
  ///
  /// The patch is the one the UI draws: the centroid, and the radius covering
  /// four fifths of the members.
  func neighbourhoodIntrusion(of result: MemoryAtlasForceLayout.Result) -> Double {
    let drawn = result.communities
    var membersOf: [Int: [String]] = [:]
    for id in nodeIDs where id != anchorID {
      guard result.roles[id] == .core, let group = drawn[id] else { continue }
      membersOf[group, default: []].append(id)
    }
    let placed = nodeIDs.compactMap { id -> (id: String, point: CGPoint)? in
      guard result.roles[id] == .core, let point = result.positions[id] else { return nil }
      return (id, point)
    }

    var foreign = 0
    var inside = 0
    for (group, members) in membersOf.sorted(by: { $0.key < $1.key }) where members.count >= 6 {
      let points = members.compactMap { result.positions[$0] }
      guard points.count >= 6 else { continue }
      let centerX = points.map { Double($0.x) }.reduce(0, +) / Double(points.count)
      let centerY = points.map { Double($0.y) }.reduce(0, +) / Double(points.count)
      let radii = points.map { hypot(Double($0.x) - centerX, Double($0.y) - centerY) }.sorted()
      let radius = radii[min(Int(Double(radii.count) * 0.8), radii.count - 1)]
      guard radius > 1e-9 else { continue }

      for entry in placed
      where hypot(Double(entry.point.x) - centerX, Double(entry.point.y) - centerY) <= radius {
        inside += 1
        if drawn[entry.id] != group { foreign += 1 }
      }
    }
    return inside == 0 ? 0 : Double(foreign) / Double(inside)
  }

  /// How much room the account holder has around them: the median gap between
  /// them and the twenty entities drawn nearest, in units of the gap a typical
  /// entity keeps from its own nearest neighbour.
  ///
  /// Stated as a ratio because the layout picks its own scale, and measured at
  /// account size because that is the only place the question means anything —
  /// the crowding exists in proportion to how many entities keep a tether, so a
  /// fixture with forty of them has nothing to show.
  func anchorClearing(of result: MemoryAtlasForceLayout.Result) -> Double {
    guard let anchor = result.positions[anchorID] else { return 0 }
    let placed = nodeIDs.filter { $0 != anchorID && result.roles[$0] == .core }
      .compactMap { result.positions[$0] }
    guard placed.count > 40 else { return 0 }

    let toAnchor =
      placed
      .map { hypot(Double($0.x - anchor.x), Double($0.y - anchor.y)) }
      .sorted().prefix(20)

    // Sampled rather than exhaustive: the median is stable long before the
    // thousandth point, and every pair would be a million distances.
    var nearest: [Double] = []
    for (index, point) in placed.enumerated() where index % 7 == 0 {
      var best = Double.infinity
      for other in placed where other != point {
        best = min(best, hypot(Double(point.x - other.x), Double(point.y - other.y)))
      }
      if best.isFinite { nearest.append(best) }
    }
    nearest.sort()
    guard !nearest.isEmpty else { return 0 }
    let typical = nearest[nearest.count / 2]
    return typical > 1e-9 ? Array(toAnchor)[toAnchor.count / 2] / typical : 0
  }

  /// Of the ten entities drawn nearest to a subject, the share that belong to
  /// its community, averaged over a sample of subjects.
  ///
  /// Deliberately a ranking measure rather than a distance: the layout is free
  /// to rotate, scale and fold, and any metric that reads raw coordinates would
  /// be measuring the fit rather than the structure.
  func communityPrecision(of result: MemoryAtlasForceLayout.Result, sample: Int = 250) -> Double {
    let placed = nodeIDs.compactMap { id in result.positions[id].map { (id: id, point: $0) } }
    let subjects = nodeIDs.filter { result.roles[$0] == .core && $0 != anchorID }.prefix(sample)

    var total = 0.0
    for subject in subjects {
      guard let point = result.positions[subject] else { continue }
      let nearest =
        placed
        .filter { $0.id != subject }
        .sorted {
          hypot($0.point.x - point.x, $0.point.y - point.y)
            < hypot($1.point.x - point.x, $1.point.y - point.y)
        }
        .prefix(10)
      total +=
        Double(nearest.filter { communityOf[$0.id] == communityOf[subject] }.count)
        / Double(nearest.count)
    }
    return subjects.isEmpty ? 0 : total / Double(subjects.count)
  }
}
