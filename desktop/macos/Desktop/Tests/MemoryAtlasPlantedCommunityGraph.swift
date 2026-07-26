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
    for id in ids where id != anchorID { membersOf[communityOf[id]!, default: []].append(id) }

    var memoryIDsByNodeID: [String: [String]] = [:]
    var drawn: [(sourceID: String, targetID: String, memoryCount: Int)] = []
    for index in 0..<memories {
      var pool = membersOf[rng.int(communities)]!
      // A minority of memories span two communities, which is what stops the
      // planted structure from being trivially separable.
      if rng.unit() < 0.12 { pool += membersOf[rng.int(communities)]! }

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
